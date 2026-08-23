"""
ide_sync.py — IDE 工作流指令生成快取與檔案追蹤器
"""

import json
from pathlib import Path
from typing import List, Set


class IDECacheTracker:
    """IDE 工作流指令生成快取與檔案追蹤器"""

    CACHE_FILE = Path(".yscb_cache/ide_workflow_manifest.json")

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.cache_path = self.project_root / self.CACHE_FILE

    def get_tracked_files(self) -> Set[Path]:
        """取得上一次生成之檔案清單 (絕對路徑)"""
        if not self.cache_path.exists():
            return set()
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return {(self.project_root / rel_path).resolve() for rel_path in data.get("files", [])}
        except Exception:
            return set()

    def clean_orphans(self, current_files: List[Path]) -> List[Path]:
        """
        比對前次紀錄，安全刪除本次不再產出的孤兒指令檔案。

        :param current_files: 本次成功生成之檔案清單 (絕對路徑)
        :return: 已被刪除的檔案清單
        """
        tracked = self.get_tracked_files()
        current_set = {f.resolve() for f in current_files}
        orphans = tracked - current_set
        deleted: List[Path] = []

        for orphan in orphans:
            if orphan.exists() and orphan.is_file():
                try:
                    orphan.unlink()
                    deleted.append(orphan)
                except OSError:
                    pass

        return deleted

    def save_manifest(self, current_files: List[Path]) -> None:
        """更新快取紀錄清單"""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        rel_files = []
        for f in current_files:
            try:
                rel = str(f.resolve().relative_to(self.project_root)).replace("\\", "/")
                rel_files.append(rel)
            except ValueError:
                rel_files.append(str(f).replace("\\", "/"))
        self.cache_path.write_text(
            json.dumps({"files": sorted(rel_files)}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
