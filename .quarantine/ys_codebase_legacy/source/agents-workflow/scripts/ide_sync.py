import json
import shutil
from pathlib import Path
from typing import List, Set

try:
    from yscb_core import ProjectContext
except ImportError:
    try:
        from context import ProjectContext
    except ImportError:
        ProjectContext = None


class IDECacheTracker:
    """IDE 工作流指令生成快取與檔案追蹤器 (每個 IDE Adapter 各自獨立的 manifest 快取)"""

    # [DEPRECATED] 舊版單一全域 manifest (多 adapter 並存時會相互誤刪，保留僅供讀取遷移)
    CACHE_FILE = Path(".yscb_cache/ide_workflow_manifest.json")

    def __init__(self, project_root: Path, adapter: str = "antigravity"):
        self.project_root = Path(project_root).resolve()
        self.adapter = adapter

        if ProjectContext:
            try:
                self.module_cache_dir = ProjectContext.get_module_cache_dir("agents-workflow", start_dir=self.project_root)
            except Exception:
                self.module_cache_dir = self.project_root / ".yscb_cache" / "modules" / "agents-workflow"
        else:
            self.module_cache_dir = self.project_root / ".yscb_cache" / "modules" / "agents-workflow"

        self.cache_path = self.module_cache_dir / f"ide_manifest_{adapter}.json"
        self.legacy_adapter_cache = self.project_root / ".yscb_cache" / f"ide_manifest_{adapter}.json"
        self.legacy_cache_path = self.project_root / self.CACHE_FILE

        self._migrate_legacy_cache()

    def _migrate_legacy_cache(self) -> None:
        """平滑自動遷移舊版快取至模組專屬命名空間"""
        if not self.cache_path.exists() and self.legacy_adapter_cache.exists() and self.legacy_adapter_cache != self.cache_path:
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(self.legacy_adapter_cache), str(self.cache_path))
            except Exception:
                pass

    def get_tracked_files(self) -> Set[Path]:
        """取得上一次生成之檔案清單 (絕對路徑)；新版 manifest 不存在時回讀舊版全域 manifest 以平滑遷移"""
        source = self.cache_path if self.cache_path.exists() else self.legacy_cache_path
        if not source.exists():
            return set()
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
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
            json.dumps({"adapter": self.adapter, "files": sorted(rel_files)}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        # 遷移完成後清除舊版全域 manifest，避免後續 adapter 誤讀
        if self.legacy_cache_path.exists() and self.legacy_cache_path != self.cache_path:
            try:
                self.legacy_cache_path.unlink()
            except OSError:
                pass
        if self.legacy_adapter_cache.exists() and self.legacy_adapter_cache != self.cache_path:
            try:
                self.legacy_adapter_cache.unlink()
            except OSError:
                pass
