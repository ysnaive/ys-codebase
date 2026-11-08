"""
Workflow Initializer for agents-workflow.
Provides probe, confirmation, directory creation, and atomic configuration binding.
"""
import os
import sys
from types import MappingProxyType
from typing import Dict, List, Any, Mapping, Optional, Tuple

try:
    from core import uri
    from core.log import log
except ImportError:
    uri = None
    log = None


def _log_init(*args: Any, **kwargs: Any) -> None:
    if log is not None:
        file_arg = kwargs.get("file")
        stream = "stderr" if file_arg is sys.stderr else "stdout"
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        text = sep.join(str(a) for a in args)
        log(text, stream=stream, end=end)


class WorkflowInitializer:
    """
    負責 agents-workflow 的一鍵初始化 (--init-default)、路徑探測、目錄建立與組態原子持久化。
    """

    DEFAULT_RECOMMENDED_PATHS: Mapping[str, str] = MappingProxyType({
        "plans": "project://plans",
        "archived": "project://plans/archived",
        "docs": "project://docs",
        "roadmap": "workflow.plans://roadmap",
    })

    def __init__(self, host_dir: Optional[str] = None):
        self.host_dir = host_dir

    @staticmethod
    def check_project_protocol() -> Tuple[bool, str]:
        """
        前置驗證依賴之 project:// 協議是否已正確定義 (core.project_root)。
        回傳 (is_valid, error_or_path)。
        """
        if uri is None:
            return True, ""
        try:
            proj_path = uri.resolve("project://", interactive=False)
            if proj_path and not str(proj_path).strip().startswith("!"):
                return True, str(proj_path)
            return False, "project_root is not configured or is !undefined"
        except Exception as e:
            return False, str(e)

    def _resolve_physical_path(
        self,
        raw_path: str,
        target_paths: Optional[Dict[str, str]] = None,
    ) -> str:
        """安全嘗試將語意 URI 或相對路徑解析為實體絕對路徑。"""
        if not raw_path or str(raw_path).strip().startswith("!"):
            return ""

        raw_str = str(raw_path).strip()
        if raw_str.startswith("workflow.plans://") and target_paths and "plans" in target_paths:
            sub_rel = raw_str[len("workflow.plans://"):].lstrip("/\\")
            plans_target = target_paths.get("plans", "")
            if plans_target and not str(plans_target).strip().startswith("workflow.plans://"):
                plans_phys = self._resolve_physical_path(plans_target)
                if plans_phys:
                    return os.path.normpath(os.path.join(plans_phys, sub_rel.replace("/", os.sep))) if sub_rel else plans_phys

        if uri and "://" in raw_str:
            try:
                resolved = uri.resolve(raw_str, interactive=False)
                if resolved and not str(resolved).strip().startswith("!"):
                    return str(resolved)
            except Exception:
                pass

            if raw_str.startswith("workflow.plans://"):
                sub_rel = raw_str[len("workflow.plans://"):].lstrip("/\\")
                fallback_plans = (target_paths or {}).get("plans") or self.DEFAULT_RECOMMENDED_PATHS.get("plans", "project://plans")
                if fallback_plans and not str(fallback_plans).strip().startswith("workflow.plans://"):
                    plans_phys = self._resolve_physical_path(fallback_plans)
                    if plans_phys:
                        return os.path.normpath(os.path.join(plans_phys, sub_rel.replace("/", os.sep))) if sub_rel else plans_phys
            return ""

        if self.host_dir and not os.path.isabs(raw_str):
            return os.path.abspath(os.path.join(self.host_dir, raw_str))
        return os.path.abspath(raw_str)

    def sync_gitignore(self, host_dir: Optional[str] = None) -> Dict[str, Any]:
        """委託 ReleasePublisher 同步更新 .gitignore 受託管區塊。"""
        from agents_workflow.publisher import ReleasePublisher

        eff_host = host_dir or self.host_dir
        pub = ReleasePublisher(host_dir=eff_host)
        return pub.sync_gitignore(proj_root=eff_host)

    def probe_paths(self, target_paths: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        探測目標路徑的實體狀態與存在性。
        """
        results = []
        for key, val in target_paths.items():
            real_p = self._resolve_physical_path(val, target_paths=target_paths)
            exists = bool(real_p and os.path.exists(real_p))
            results.append({
                "key": key,
                "uri_or_path": val,
                "real_path": real_p,
                "exists": exists,
            })
        return results

    @staticmethod
    def _write_project_config(bound_paths: Dict[str, str]) -> bool:
        """原子增量寫入 config/agents-workflow/config.project.json。"""
        try:
            from core import config
            for k, v in bound_paths.items():
                config.set("agents-workflow", f"paths.{k}", v, local=False)
            return True
        except Exception:
            return False

    @staticmethod
    def _print_undefined_project_error() -> None:
        """輸出 project:// 協議未定義之錯誤引導訊息。"""
        _log_init("\n" + "=" * 75, file=sys.stderr)
        _log_init("[agents-workflow:init] [!] 錯誤：依賴協議 'project://' 尚未定義！", file=sys.stderr)
        _log_init("=" * 75, file=sys.stderr)
        _log_init("agents-workflow 依賴專案根目錄協議 'project://' 來定位 plans 與 docs 目錄。", file=sys.stderr)
        _log_init("當前 core.project_root 未配置或為 !undefined。\n", file=sys.stderr)
        _log_init("[*] 建議解決步驟：", file=sys.stderr)
        _log_init("  1. 請先執行以下指令設定專案根目錄 (例如指定當前目錄或專案路徑)：", file=sys.stderr)
        _log_init("     python yscb.py config set core project_root .\n", file=sys.stderr)
        _log_init("  2. 或於終端執行協議解析以進行及時熱更新補齊：", file=sys.stderr)
        _log_init("     python yscb.py uri resolve project://\n", file=sys.stderr)
        _log_init("  3. 設定完成後，請重新執行 agents-workflow 一鍵初始化。", file=sys.stderr)
        _log_init("=" * 75 + "\n", file=sys.stderr)

    @staticmethod
    def _prompt_init_confirmation(auto_confirm: bool, interactive: bool) -> bool:
        """處理初始化前之互動確認或非互動環境防呆攔截（非 auto_confirm 一律拒絕並提示使用 -y / --yes）。"""
        if auto_confirm:
            return True
        if interactive:
            _log_init("[agents-workflow] 互動提示已停用（無阻塞模式），請附加 -y / --yes 參數確認，操作已取消。")
            return False
        _log_init("[agents-workflow] 非互動模式需要 -y / --yes 參數確認，操作已取消。")
        return False

    def run_init_default(
        self,
        paths_override: Optional[Dict[str, str]] = None,
        auto_confirm: bool = False,
        interactive: bool = True,
    ) -> Dict[str, Any]:
        """
        執行 --init-default 完整流程。
        """
        is_project_defined, _ = self.check_project_protocol()
        if not is_project_defined:
            self._print_undefined_project_error()
            return {
                "success": False,
                "cancelled": False,
                "error": "project:// protocol is undefined",
                "created_dirs": [],
                "bound_paths": {},
            }

        target_paths = dict(self.DEFAULT_RECOMMENDED_PATHS)
        if paths_override:
            for k, v in paths_override.items():
                if k in target_paths and v:
                    target_paths[k] = str(v).strip()

        probed = self.probe_paths(target_paths)

        _log_init("\n[agents-workflow] 將初始化以下 Workflow URI 協議與目錄結構:")
        _log_init("-" * 75)
        _log_init(f"{'KEY':<12} {'TARGET URI / PATH':<45} {'STATUS'}")
        _log_init("-" * 75)

        existing_warnings = []
        to_create = []

        for item in probed:
            status_str = "[已存在] (自動綁定)" if item["exists"] else "[即將建立]"
            _log_init(f"{item['key']:<12} {item['uri_or_path']:<45} {status_str}")
            if item["exists"]:
                existing_warnings.append(item)
            else:
                to_create.append(item)
        _log_init("-" * 75)

        if existing_warnings:
            _log_init("\n[提示] 以下目錄已存在於檔案系統中，將自動綁定在該路徑：")
            for w in existing_warnings:
                _log_init(f"  • {w['key']}: {w['real_path']}")

        if not self._prompt_init_confirmation(auto_confirm=auto_confirm, interactive=interactive):
            return {
                "success": True,
                "cancelled": True,
                "created_dirs": [],
                "bound_paths": {},
            }

        created_dirs = []
        for item in to_create:
            r_path = item["real_path"]
            if r_path:
                try:
                    os.makedirs(r_path, exist_ok=True)
                    created_dirs.append(r_path)
                except Exception as e:
                    _log_init(f"[agents-workflow] Warning: Failed to create directory '{r_path}': {e}", file=sys.stderr)

        bound_paths = {item["key"]: item["uri_or_path"] for item in probed}
        write_ok = self._write_project_config(bound_paths)

        if write_ok:
            _log_init("\n[agents-workflow] 一鍵初始化成功！")
            _log_init(f"  • 建立目錄數量: {len(created_dirs)}")
            _log_init(f"  • 綁定協議數量: {len(bound_paths)}")
            for k, v in bound_paths.items():
                _log_init(f"    - workflow.{k}:// -> {v}")
        else:
            _log_init("\n[agents-workflow] Warning: Directory created, but failed to update config.project.json.", file=sys.stderr)

        return {
            "success": write_ok,
            "cancelled": False,
            "created_dirs": created_dirs,
            "bound_paths": bound_paths,
        }
