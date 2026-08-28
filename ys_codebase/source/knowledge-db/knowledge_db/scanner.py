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
import tempfile
from typing import Any, Dict, List, Optional, Set

from .exceptions import FingerprintCorruptedError
from .schema import SpaceConfig
from .space import SpaceManager

logger = logging.getLogger("knowledge-db.scanner")


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
