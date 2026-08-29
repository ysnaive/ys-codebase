"""
knowledge-db 雙階增量指紋比對引擎 (FingerprintScanner) 與原子持久化
"""

from dataclasses import dataclass, field
import fnmatch
import hashlib
import json
import logging
import os
from pathlib import Path
import struct
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .exceptions import FingerprintCorruptedError
from .schema import SpaceConfig
from .space import SpaceManager

logger = logging.getLogger("knowledge-db.scanner")


@dataclass
class ScanDiffDetail:
    """JIT 變更嗅探之差量明細"""

    added: Set[str] = field(default_factory=set)  # canonical paths
    modified: Set[str] = field(default_factory=set)  # canonical paths
    deleted: Set[str] = field(default_factory=set)  # canonical paths

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    @property
    def dirty_files(self) -> Set[str]:
        return self.added | self.modified | self.deleted


class BinarySnapshotManager:
    """
    原生二進位快照管理器 (Magic: YFP1)。
    提供微秒級 (< 0.1ms) 反序列化與極致緊湊磁碟儲存，作為 JIT 變更嗅探之高速快取清冊。
    """

    MAGIC: bytes = b"YFP1"
    VERSION: int = 1
    HEADER_STRUCT = "<4sHId"  # magic(4B), version(2B), total_files(4B), timestamp(8B) = 18B -> 20B padded
    ENTRY_STRUCT = "<HQd"    # path_len(2B), size(8B), mtime(8B) = 18B

    @classmethod
    def save(
        cls,
        snapshot_path: Union[str, Path],
        files_map: Dict[str, Tuple[float, int]],
        timestamp: Optional[float] = None,
    ) -> None:
        """
        原子寫入二進位快照至磁碟。
        :param snapshot_path: 目標檔案路徑 (.meta.bin)
        :param files_map: {正規化檔案路徑: (mtime, size)}
        :param timestamp: 建置時間戳 (預設 time.time())
        """
        target_path = Path(snapshot_path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        ts = timestamp if timestamp is not None else time.time()
        total_files = len(files_map)

        header = struct.pack(cls.HEADER_STRUCT, cls.MAGIC, cls.VERSION, total_files, ts)
        buffer = bytearray(header)

        for path_str, (mtime, size) in files_map.items():
            path_bytes = path_str.encode("utf-8")
            path_len = len(path_bytes)
            entry = struct.pack(cls.ENTRY_STRUCT, path_len, int(size), float(mtime))
            buffer.extend(entry)
            buffer.extend(path_bytes)

        temp_fd, temp_path = tempfile.mkstemp(dir=str(target_path.parent), prefix="meta_tmp_", suffix=".bin")
        try:
            with os.fdopen(temp_fd, "wb") as f:
                f.write(buffer)
            os.replace(temp_path, str(target_path))
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise e

    @classmethod
    def load(cls, snapshot_path: Union[str, Path]) -> Optional[Dict[str, Tuple[float, int]]]:
        """
        載入二進位快照檔案，若不存在或損毀回傳 None。
        :return: {正規化檔案路徑: (mtime, size)}
        """
        target_path = Path(snapshot_path)
        if not target_path.exists():
            return None

        try:
            with open(target_path, "rb") as f:
                data = f.read()

            header_size = struct.calcsize(cls.HEADER_STRUCT)
            if len(data) < header_size:
                return None

            magic, version, total_files, _ = struct.unpack_from(cls.HEADER_STRUCT, data, 0)
            if magic != cls.MAGIC or version != cls.VERSION:
                return None

            files_map: Dict[str, Tuple[float, int]] = {}
            offset = header_size
            entry_size = struct.calcsize(cls.ENTRY_STRUCT)

            for _ in range(total_files):
                if offset + entry_size > len(data):
                    return None
                path_len, size, mtime = struct.unpack_from(cls.ENTRY_STRUCT, data, offset)
                offset += entry_size
                if offset + path_len > len(data):
                    return None
                path_str = data[offset : offset + path_len].decode("utf-8")
                offset += path_len
                files_map[path_str] = (mtime, size)

            return files_map
        except Exception as e:
            logger.warning(f"Failed loading binary snapshot '{snapshot_path}': {e}")
            return None



@dataclass(frozen=True)
class FileFingerprint:
    relpath: str
    source_root: str
    mtime: float
    size: int
    sha1: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relpath": self.relpath,
            "source_root": self.source_root,
            "mtime": self.mtime,
            "size": self.size,
            "sha1": self.sha1,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileFingerprint":
        if not isinstance(data, dict):
            raise FingerprintCorruptedError("Fingerprint record must be a dict.")
        required = ["relpath", "source_root", "mtime", "size", "sha1"]
        for k in required:
            if k not in data:
                raise FingerprintCorruptedError(f"Fingerprint missing required key '{k}'.")
        return cls(
            relpath=str(data["relpath"]),
            source_root=str(data["source_root"]),
            mtime=float(data["mtime"]),
            size=int(data["size"]),
            sha1=str(data["sha1"]),
        )


@dataclass
class ScanDiffResult:
    space_name: str
    added: List[FileFingerprint] = field(default_factory=list)
    modified: List[FileFingerprint] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    unchanged: List[FileFingerprint] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)


class FingerprintScanner:
    """
    雙階增量指紋比對掃描器：
    Stage 1: mtime + size 輕量初篩 (零 I/O、零 SHA1 計算)
    Stage 2: SHA1 內容校驗 (變更比對、touch 判定、增修刪差異計算)
    """

    def __init__(self, space_manager: SpaceManager):
        self.space_manager = space_manager

    def load_fingerprints(self, space_name: str) -> Dict[str, FileFingerprint]:
        """
        載入指定空間之指紋快取檔案 (fingerprints.json)。
        若檔案不存在回傳空字典；若損毀則發出 Warning 並自癒重置為空字典 (EC-03)。
        """
        storage_dir = self.space_manager.get_space_storage_dir(space_name)
        fp_file = storage_dir / "fingerprints.json"

        if not fp_file.exists():
            return {}

        try:
            with open(fp_file, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise FingerprintCorruptedError("fingerprints.json top-level must be a dictionary.")

            fingerprints: Dict[str, FileFingerprint] = {}
            for relpath, fp_raw in data.items():
                if isinstance(fp_raw, dict):
                    fingerprints[relpath] = FileFingerprint.from_dict(fp_raw)
            return fingerprints
        except Exception as e:
            logger.warning(
                f"Fingerprint cache for space '{space_name}' corrupted ({e}), self-healing with clean rebuild."
            )
            return {}

    def save_fingerprints(self, space_name: str, fingerprints: Dict[str, FileFingerprint]) -> None:
        """
        以原子寫入方式 (tempfile + os.replace) 持久化指紋快取至 storage://knowledge-db/spaces/<space>/fingerprints.json。
        """
        storage_dir = self.space_manager.get_space_storage_dir(space_name)
        storage_dir.mkdir(parents=True, exist_ok=True)
        target_file = storage_dir / "fingerprints.json"

        serialized = {k: v.to_dict() for k, v in fingerprints.items()}

        # 在同目錄建立暫存檔以確保原子 replace 跨檔案系統安全
        temp_fd, temp_path = tempfile.mkstemp(dir=str(storage_dir), prefix="fp_tmp_", suffix=".json")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(serialized, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, str(target_file))
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise e

    @staticmethod
    def _compute_sha1(file_path: Path) -> str:
        """分塊讀取檔案計算 SHA-1 雜湊 (64KB chunks)"""
        hasher = hashlib.sha1()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _is_excluded(relpath: str, exclude_patterns: List[str]) -> bool:
        """檢查相對路徑是否匹配任一 exclude glob 模式"""
        norm_rel = relpath.replace("\\", "/")
        for pat in exclude_patterns:
            norm_pat = pat.replace("\\", "/")
            if fnmatch.fnmatch(norm_rel, norm_pat) or fnmatch.fnmatch(f"/{norm_rel}", norm_pat):
                return True
            # 也支援對檔名直接比對
            filename = os.path.basename(norm_rel)
            if fnmatch.fnmatch(filename, norm_pat):
                return True
        return False

    def scan_space(self, space_config: SpaceConfig, force: bool = False) -> ScanDiffResult:
        """
        對單一空間執行雙階增量指紋比對。
        """
        space_name = space_config.name
        old_fps = self.load_fingerprints(space_name)
        new_fps: Dict[str, FileFingerprint] = {}
        diff = ScanDiffResult(space_name=space_name)

        source_roots = self.space_manager.resolve_space_include(space_name)
        visited_relpaths: Set[str] = set()

        for source_root in source_roots:
            if source_root.is_file():
                # 單一檔案來源
                files_to_check = [source_root]
                base_dir = source_root.parent
            else:
                # 目錄來源
                files_to_check = []
                base_dir = source_root
                for root_dir, dirs, files in os.walk(str(source_root)):
                    # 排除目錄檢查
                    rel_dir = os.path.relpath(root_dir, str(base_dir)).replace("\\", "/")
                    if rel_dir != "." and self._is_excluded(rel_dir + "/", space_config.exclude):
                        dirs.clear()
                        continue

                    for file in files:
                        files_to_check.append(Path(root_dir) / file)

            for file_path in files_to_check:
                try:
                    relpath = os.path.relpath(str(file_path), str(base_dir)).replace("\\", "/")
                except ValueError:
                    relpath = file_path.name

                if relpath in visited_relpaths:
                    continue

                # 檢查 exclude
                if self._is_excluded(relpath, space_config.exclude):
                    continue

                # 檢查 file_patterns (EC-01: 未定義預設 include all)
                if not space_config.is_file_included(file_path.name):
                    continue

                visited_relpaths.add(relpath)

                try:
                    stat_res = file_path.stat()
                except (OSError, PermissionError) as e:
                    logger.warning(f"Failed to stat file '{file_path}' in space '{space_name}': {e}")
                    continue

                mtime = stat_res.st_mtime
                size = stat_res.st_size
                old_fp = old_fps.get(relpath)

                if not force and old_fp is not None:
                    # Stage 1: 初篩比對 mtime 與 size
                    if old_fp.mtime == mtime and old_fp.size == size:
                        diff.unchanged.append(old_fp)
                        new_fps[relpath] = old_fp
                        continue

                    # Stage 2: 深入比對 SHA1 雜湊
                    try:
                        sha1 = self._compute_sha1(file_path)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Failed reading file content '{file_path}': {e}")
                        continue

                    if sha1 == old_fp.sha1:
                        # 內容未變，僅更新快取中的 mtime/size (EC-04)
                        updated_fp = FileFingerprint(
                            relpath=relpath,
                            source_root=str(base_dir),
                            mtime=mtime,
                            size=size,
                            sha1=sha1,
                        )
                        diff.unchanged.append(updated_fp)
                        new_fps[relpath] = updated_fp
                    else:
                        # 內容確實修改
                        mod_fp = FileFingerprint(
                            relpath=relpath,
                            source_root=str(base_dir),
                            mtime=mtime,
                            size=size,
                            sha1=sha1,
                        )
                        diff.modified.append(mod_fp)
                        new_fps[relpath] = mod_fp
                else:
                    # 全新檔案或 force 掃描
                    try:
                        sha1 = self._compute_sha1(file_path)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Failed reading new file '{file_path}': {e}")
                        continue

                    new_fp = FileFingerprint(
                        relpath=relpath,
                        source_root=str(base_dir),
                        mtime=mtime,
                        size=size,
                        sha1=sha1,
                    )
                    if old_fp is None:
                        diff.added.append(new_fp)
                    else:
                        diff.modified.append(new_fp)
                    new_fps[relpath] = new_fp

        # 檢驗刪除檔案
        for old_relpath in old_fps:
            if old_relpath not in visited_relpaths:
                diff.deleted.append(old_relpath)

        # 原子持久化新指紋庫
        self.save_fingerprints(space_name, new_fps)

        return diff

    def scan_all_spaces(
        self, spaces: Optional[List[SpaceConfig]] = None, force: bool = False
    ) -> Dict[str, ScanDiffResult]:
        """
        對所有空間之聯集 (Union Scope) 執行增量掃描，回傳 {space_name: ScanDiffResult}。
        """
        target_spaces = spaces if spaces is not None else self.space_manager.get_union_spaces()
        results: Dict[str, ScanDiffResult] = {}
        for sp in target_spaces:
            results[sp.name] = self.scan_space(sp, force=force)
        return results

    def _scan_entries_fast(
        self,
        base_dir: Path,
        current_dir: Path,
        sp: SpaceConfig,
        files_to_check: List[Tuple[Path, str, os.stat_result]],
    ) -> None:
        """使用 os.scandir 遞迴走訪目錄，直接自 DirEntry.stat() 提取資訊，減少系統呼叫。"""
        try:
            with os.scandir(str(current_dir)) as it:
                for entry in it:
                    try:
                        entry_path = Path(entry.path)
                        rel_path = os.path.relpath(str(entry_path), str(base_dir)).replace("\\", "/")
                        if entry.is_dir(follow_symlinks=False):
                            if self._is_excluded(rel_path + "/", sp.exclude):
                                continue
                            self._scan_entries_fast(base_dir, entry_path, sp, files_to_check)
                        elif entry.is_file(follow_symlinks=False):
                            if self._is_excluded(rel_path, sp.exclude):
                                continue
                            if not sp.is_file_included(entry.name):
                                continue
                            stat_res = entry.stat()
                            files_to_check.append((entry_path, rel_path, stat_res))
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Failed scanning entry '{entry.path}': {e}")
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed opening directory '{current_dir}': {e}")

    def _collect_full_files_map(
        self, spaces: List[SpaceConfig]
    ) -> Dict[str, Tuple[float, int]]:
        """全量走訪並收集空間檔案之 (mtime, size) 清冊。"""
        files_map: Dict[str, Tuple[float, int]] = {}
        visited: Set[str] = set()
        for sp in spaces:
            for s_root in self.space_manager.resolve_space_include(sp.name):
                if s_root.is_file():
                    try:
                        if not self._is_excluded(s_root.name, sp.exclude) and sp.is_file_included(s_root.name):
                            c_key = str(s_root.resolve()).replace("\\", "/")
                            if c_key not in visited:
                                visited.add(c_key)
                                st = s_root.stat()
                                files_map[c_key] = (st.st_mtime, st.st_size)
                    except (OSError, PermissionError):
                        pass
                else:
                    files_to_check: List[Tuple[Path, str, os.stat_result]] = []
                    self._scan_entries_fast(s_root, s_root, sp, files_to_check)
                    for f_path, _, st in files_to_check:
                        c_key = str(f_path.resolve()).replace("\\", "/")
                        if c_key not in visited:
                            visited.add(c_key)
                            files_map[c_key] = (st.st_mtime, st.st_size)
        return files_map

    def check_invalidation(
        self,
        spaces: Optional[List[SpaceConfig]] = None,
        snapshot_path: Optional[Union[str, Path]] = None,
    ) -> Tuple[bool, int, str, Dict[str, Tuple[float, int]], ScanDiffDetail]:
        """
        對全專案空間聯集 (Union Scope) 執行極速 JIT 變更嗅探 (基於 stat: mtime & size)。
        保證 100% 完整走訪所有目標檔案，絕不提早中斷。

        :param spaces: 空間清單 (預設為 get_union_spaces())
        :param snapshot_path: 快照檔案路徑 (預設為 storage_dir/indices/unified.meta.bin)
        :return: (is_dirty, scanned_file_count, reason, full_current_files_map, diff_detail)
        """
        target_spaces = spaces if spaces is not None else self.space_manager.get_union_spaces()
        if snapshot_path is None:
            snapshot_path = self.space_manager.storage_dir / "indices" / "unified.meta.bin"

        cached_map = BinarySnapshotManager.load(snapshot_path)
        diff = ScanDiffDetail()

        if cached_map is None:
            current_files = self._collect_full_files_map(target_spaces)
            diff.added = set(current_files.keys())
            return True, len(current_files), "Snapshot missing or corrupted", current_files, diff

        current_files: Dict[str, Tuple[float, int]] = {}
        visited_keys: Set[str] = set()

        for sp in target_spaces:
            space_name = sp.name
            source_roots = self.space_manager.resolve_space_include(space_name)

            for source_root in source_roots:
                if source_root.is_file():
                    try:
                        if not self._is_excluded(source_root.name, sp.exclude) and sp.is_file_included(source_root.name):
                            canonical_key = str(source_root.resolve()).replace("\\", "/")
                            if canonical_key not in visited_keys:
                                visited_keys.add(canonical_key)
                                stat_res = source_root.stat()
                                mtime = stat_res.st_mtime
                                size = stat_res.st_size
                                current_files[canonical_key] = (mtime, size)

                                cached_entry = cached_map.get(canonical_key)
                                if cached_entry is None:
                                    diff.added.add(canonical_key)
                                else:
                                    cached_mtime, cached_size = cached_entry
                                    if cached_mtime != mtime or cached_size != size:
                                        diff.modified.add(canonical_key)
                    except (OSError, PermissionError) as e:
                        logger.warning(f"Failed to stat file '{source_root}': {e}")
                else:
                    base_dir = source_root
                    files_to_check: List[Tuple[Path, str, os.stat_result]] = []
                    self._scan_entries_fast(base_dir, source_root, sp, files_to_check)

                    for file_path, relpath, stat_res in files_to_check:
                        canonical_key = str(file_path.resolve()).replace("\\", "/")
                        if canonical_key in visited_keys:
                            continue
                        visited_keys.add(canonical_key)

                        mtime = stat_res.st_mtime
                        size = stat_res.st_size
                        current_files[canonical_key] = (mtime, size)

                        cached_entry = cached_map.get(canonical_key)
                        if cached_entry is None:
                            diff.added.add(canonical_key)
                        else:
                            cached_mtime, cached_size = cached_entry
                            if cached_mtime != mtime or cached_size != size:
                                diff.modified.add(canonical_key)

        # 檢測刪除檔案：在 cached_map 中但不在 current_files 中的檔案
        for cached_key in cached_map.keys():
            if cached_key not in current_files:
                diff.deleted.add(cached_key)

        is_dirty = diff.has_changes
        if not is_dirty:
            return False, len(current_files), "Clean", current_files, diff

        reasons = []
        if diff.added:
            reasons.append(f"{len(diff.added)} added")
        if diff.modified:
            reasons.append(f"{len(diff.modified)} modified")
        if diff.deleted:
            reasons.append(f"{len(diff.deleted)} deleted")
        reason_str = ", ".join(reasons)

        return True, len(current_files), f"Detected changes: {reason_str}", current_files, diff


