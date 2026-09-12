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

        try:
            from core.vfs import write_bytes
            write_bytes(target_path, buffer, atomic=True)
        except Exception:
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
    sha1: str = ""

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
        return cls(
            relpath=str(data.get("relpath", "")),
            source_root=str(data.get("source_root", "")),
            mtime=float(data.get("mtime", 0.0)),
            size=int(data.get("size", 0)),
            sha1=str(data.get("sha1", "")),
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
    原生物理級二進位增量快照掃描器 (SSOT: unified.meta.bin)。
    全面收斂至 BinarySnapshotManager，提供微秒級比對與原子持久化，徹底廢除 JSON 指紋檔。
    """

    def __init__(self, space_manager: SpaceManager):
        self.space_manager = space_manager

    def _file_belongs_to_space(self, canonical_path: str, sp: SpaceConfig) -> bool:
        """檢查給定正規化絕對路徑是否屬於指定的 SpaceConfig"""
        norm_path = canonical_path.replace("\\", "/")
        source_roots = self.space_manager.resolve_space_include(sp.name)
        for s_root in source_roots:
            if s_root.is_file():
                if norm_path == str(s_root.resolve()).replace("\\", "/"):
                    return not self._is_excluded(s_root.name, sp.exclude) and sp.is_file_included(s_root.name)
            else:
                norm_root = str(s_root.resolve()).replace("\\", "/")
                if not norm_root.endswith("/"):
                    norm_root += "/"
                if norm_path.startswith(norm_root):
                    rel = norm_path[len(norm_root):]
                    filename = os.path.basename(rel)
                    if not self._is_excluded(rel, sp.exclude) and sp.is_file_included(filename):
                        return True
        return False

    def _relpath_for_space(self, canonical_path: str, sp: SpaceConfig) -> str:
        """取得給定正規化絕對路徑在指定 SpaceConfig 下的相對路徑"""
        norm_path = canonical_path.replace("\\", "/")
        source_roots = self.space_manager.resolve_space_include(sp.name)
        for s_root in source_roots:
            if s_root.is_file():
                if norm_path == str(s_root.resolve()).replace("\\", "/"):
                    return s_root.name
            else:
                norm_root = str(s_root.resolve()).replace("\\", "/")
                if not norm_root.endswith("/"):
                    norm_root += "/"
                if norm_path.startswith(norm_root):
                    return norm_path[len(norm_root):]
        return os.path.basename(norm_path)

    def load_fingerprints(self, space_name: str) -> Dict[str, FileFingerprint]:
        """
        [相容性介面] 自 unified.meta.bin 二進位快照反查指定空間之檔案指紋清單。
        若快照不存在則回傳空字典。
        """
        snapshot_path = self.space_manager.storage_dir / "indices" / "unified.meta.bin"
        cached_map = BinarySnapshotManager.load(snapshot_path)
        if not cached_map:
            return {}

        sp = self.space_manager.get_space(space_name)
        res: Dict[str, FileFingerprint] = {}
        for canon_path, (mtime, size) in cached_map.items():
            if self._file_belongs_to_space(canon_path, sp):
                rel = self._relpath_for_space(canon_path, sp)
                res[rel] = FileFingerprint(
                    relpath=rel,
                    source_root="",
                    mtime=mtime,
                    size=size,
                )
        return res

    def save_fingerprints(self, space_name: str, fingerprints: Dict[str, FileFingerprint]) -> None:
        """[Deprecated] 空實作；已徹底廢除 fingerprints.json，改由 unified.meta.bin 唯一託管。"""
        pass

    @staticmethod
    def _is_excluded(relpath: str, exclude_patterns: List[str]) -> bool:
        """檢查相對路徑是否匹配任一 exclude glob 模式"""
        norm_rel = relpath.replace("\\", "/")
        for pat in exclude_patterns:
            norm_pat = pat.replace("\\", "/")
            if fnmatch.fnmatch(norm_rel, norm_pat) or fnmatch.fnmatch(f"/{norm_rel}", norm_pat):
                return True
            filename = os.path.basename(norm_rel)
            if fnmatch.fnmatch(filename, norm_pat):
                return True
        return False

    def scan_space(self, space_config: SpaceConfig, force: bool = False) -> ScanDiffResult:
        """
        對單一空間執行增量快照比對 (SSOT: unified.meta.bin)。
        """
        space_name = space_config.name
        snapshot_path = self.space_manager.storage_dir / "indices" / "unified.meta.bin"
        cached_map = BinarySnapshotManager.load(snapshot_path)
        if cached_map is None or force:
            cached_map = {}

        diff = ScanDiffResult(space_name=space_name)
        source_roots = self.space_manager.resolve_space_include(space_name)
        current_space_files: Dict[str, Tuple[float, int]] = {}

        for source_root in source_roots:
            if source_root.is_file():
                files_to_check = [source_root]
                base_dir = source_root.parent
            else:
                files_to_check = []
                base_dir = source_root
                for root_dir, dirs, files in os.walk(str(source_root)):
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

                if self._is_excluded(relpath, space_config.exclude):
                    continue
                if not space_config.is_file_included(file_path.name):
                    continue

                canonical_key = str(file_path.resolve()).replace("\\", "/")
                if canonical_key in current_space_files:
                    continue

                try:
                    stat_res = file_path.stat()
                except (OSError, PermissionError) as e:
                    logger.warning(f"Failed to stat file '{file_path}' in space '{space_name}': {e}")
                    continue

                mtime = stat_res.st_mtime
                size = stat_res.st_size
                current_space_files[canonical_key] = (mtime, size)

                fp = FileFingerprint(
                    relpath=relpath,
                    source_root=str(base_dir),
                    mtime=mtime,
                    size=size,
                )

                if not force and canonical_key in cached_map:
                    cached_mtime, cached_size = cached_map[canonical_key]
                    if cached_mtime == mtime and cached_size == size:
                        diff.unchanged.append(fp)
                    else:
                        diff.modified.append(fp)
                else:
                    diff.added.append(fp)

        # 檢驗刪除檔案：cached_map 中屬於該空間但目前磁碟已不存在者
        for cached_key in list(cached_map.keys()):
            if self._file_belongs_to_space(cached_key, space_config):
                if cached_key not in current_space_files:
                    del_rel = self._relpath_for_space(cached_key, space_config)
                    diff.deleted.append(del_rel)

        # 原子持久化至二進位快照 (更新當前空間的檔案映射，移除已刪除者)
        updated_map = dict(cached_map)
        for del_rel in diff.deleted:
            for k in list(updated_map.keys()):
                if self._file_belongs_to_space(k, space_config) and self._relpath_for_space(k, space_config) == del_rel:
                    updated_map.pop(k, None)
        updated_map.update(current_space_files)
        BinarySnapshotManager.save(snapshot_path, updated_map)

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


