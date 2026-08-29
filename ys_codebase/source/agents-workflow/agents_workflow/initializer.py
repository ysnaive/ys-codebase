"""
Workflow Initializer for agents-workflow.
Provides probe, confirmation, directory creation, and atomic configuration binding.
"""
import os
import sys
import json
from typing import Dict, List, Any, Optional

try:
    from core import uri
except ImportError:
    uri = None


class WorkflowInitializer:
    """
    負責 agents-workflow 的一鍵初始化 (--init-default)、路徑探測、目錄建立與組態原子持久化。
    """

    DEFAULT_RECOMMENDED_PATHS: Dict[str, str] = {
        "plans": "project://plans",
        "archived": "project://plans/archived",
        "docs": "project://docs",
        "roadmap": "workflow.plans://roadmap"
    }

    def __init__(self, host_dir: Optional[str] = None):
        self.host_dir = host_dir
        # 定位模組根目錄
        self.module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _resolve_physical_path(self, raw_path: str) -> str:
        """安全嘗試將語意 URI 或相對路徑解析為實體絕對路徑。"""
        if not raw_path or raw_path == "!undefined":
            return ""

        if uri and "://" in raw_path:
            try:
                return uri.resolve(raw_path, interactive=False)
            except Exception:
                pass

        # 若包含 project:// 但無法透過 uri.resolve 解析 (例未配置 project_root)
        if raw_path.startswith("project://"):
            sub = raw_path[len("project://"):].lstrip("/\\")
            # 優先嘗試當前工作目錄
            cwd = os.getcwd()
            return os.path.abspath(os.path.join(cwd, sub))

        # 一般相對/絕對路徑
        return os.path.abspath(raw_path)

    def probe_paths(self, target_paths: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        探測目標路徑的實體狀態與存在性。
        """
        results = []
        for key, val in target_paths.items():
            real_p = self._resolve_physical_path(val)
            exists = bool(real_p and os.path.exists(real_p))
            results.append({
                "key": key,
                "uri_or_path": val,
                "real_path": real_p,
                "exists": exists
            })
        return results

    def _write_project_config(self, bound_paths: Dict[str, str]) -> bool:
        """原子增量寫入 config/agents-workflow/config.project.json。"""
        try:
            from core import config
            for k, v in bound_paths.items():
                config.set("agents-workflow", f"paths.{k}", v, local=False)
            return True
        except Exception:
            return False



    def run_init_default(
        self,
        paths_override: Optional[Dict[str, str]] = None,
        auto_confirm: bool = False,
        interactive: bool = True
    ) -> Dict[str, Any]:
        """
        執行 --init-default 完整流程。
        """
        # 合併推薦路徑與使用者覆蓋參數
        target_paths = dict(self.DEFAULT_RECOMMENDED_PATHS)
        if paths_override:
            for k, v in paths_override.items():
                if k in target_paths and v:
                    target_paths[k] = str(v).strip()

        probed = self.probe_paths(target_paths)

        # 呈遞清單與提醒
        print("\n[agents-workflow] 將初始化以下 Workflow URI 協議與目錄結構:")
        print("-" * 75)
        print(f"{'KEY':<12} {'TARGET URI / PATH':<45} {'STATUS'}")
        print("-" * 75)

        existing_warnings = []
        to_create = []

        for item in probed:
            status_str = "[已存在] (自動綁定)" if item["exists"] else "[即將建立]"
            print(f"{item['key']:<12} {item['uri_or_path']:<45} {status_str}")
            if item["exists"]:
                existing_warnings.append(item)
            else:
                to_create.append(item)
        print("-" * 75)

        if existing_warnings:
            print("\n[提示] 以下目錄已存在於檔案系統中，將自動綁定在該路徑：")
            for w in existing_warnings:
                print(f"  • {w['key']}: {w['real_path']}")

        # 互動確認
        if not auto_confirm:
            if interactive:
                try:
                    choice = input("\n確認要建立上述資料夾並寫入設定檔嗎? [-y / -n]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    choice = "n"
                if choice not in ("y", "yes", "-y"):
                    print("[agents-workflow] 操作已由使用者取消。")
                    return {
                        "success": True,
                        "cancelled": True,
                        "created_dirs": [],
                        "bound_paths": {}
                    }
            else:
                # 非互動環境且未帶 -y / --yes，安全取消防止非預期變更
                print("[agents-workflow] 非互動模式需要 -y / --yes 參數確認，操作已取消。")
                return {
                    "success": True,
                    "cancelled": True,
                    "created_dirs": [],
                    "bound_paths": {}
                }

        # 建立目錄
        created_dirs = []
        for item in to_create:
            r_path = item["real_path"]
            if r_path:
                try:
                    os.makedirs(r_path, exist_ok=True)
                    created_dirs.append(r_path)
                except Exception as e:
                    print(f"[agents-workflow] Warning: Failed to create directory '{r_path}': {e}", file=sys.stderr)

        # 寫入設定檔
        bound_paths = {item["key"]: item["uri_or_path"] for item in probed}
        write_ok = self._write_project_config(bound_paths)

        if write_ok:
            print(f"\n[agents-workflow] 一鍵初始化成功！")
            print(f"  • 建立目錄數量: {len(created_dirs)}")
            print(f"  • 綁定協議數量: {len(bound_paths)}")
            for k, v in bound_paths.items():
                print(f"    - workflow.{k}:// -> {v}")
        else:
            print(f"\n[agents-workflow] Warning: Directory created, but failed to update config.project.json.", file=sys.stderr)

        return {
            "success": write_ok,
            "cancelled": False,
            "created_dirs": created_dirs,
            "bound_paths": bound_paths
        }
