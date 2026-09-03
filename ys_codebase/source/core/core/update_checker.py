"""
YS-Codebase Update Checker with 12-Hour Throttling & Non-Blocking Tips.
100% Python Standard Library, Zero External Dependencies.
"""
from typing import Dict, Any, List, Optional
import os
import sys
import json
import time
import urllib.request
from core import uri
from core import semver

DEFAULT_CACHE_URI: str = "cache://core/update_check.json"
DEFAULT_THROTTLE_SECONDS: int = 43200  # 12 小時
DEFAULT_TIMEOUT_SECONDS: float = 2.0


class UpdateChecker:
    """
    安裝來源 12 小時週期版本探測與升級提示管理器。
    """
    def __init__(
        self,
        cache_uri: str = DEFAULT_CACHE_URI,
        throttle_seconds: int = DEFAULT_THROTTLE_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        config_path: Optional[str] = None
    ):
        self.cache_uri = cache_uri
        self.throttle_seconds = throttle_seconds
        self.timeout_seconds = timeout_seconds
        self.config_path = config_path

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path and os.path.isfile(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        try:
            cfg_p = uri.resolve("project://yscb.config.json", interactive=False)
            if os.path.isfile(cfg_p):
                with open(cfg_p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _load_cache(self) -> Dict[str, Any]:
        if uri.exists(self.cache_uri):
            try:
                data = uri.read_json(self.cache_uri)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {"last_checked_at": 0.0, "updates": {}}

    def _save_cache(self, data: Dict[str, Any]) -> None:
        try:
            uri.makedirs("cache://core", exist_ok=True)
            uri.write_json(self.cache_uri, data)
        except Exception:
            pass

    def check_updates(self, force: bool = False) -> Dict[str, Any]:
        """
        檢查各已安裝模組是否有新版本可用。
        在 12 小時節流時間內直接返回快取；超過 12 小時或 force=True 時發起輕量探測。
        所有網路例外靜默兜底，不拋出中斷例外。
        """
        if os.environ.get("YSCB_NO_UPDATE_CHECK") == "1":
            return {}

        now = time.time()
        cached = self._load_cache()
        last_checked = cached.get("last_checked_at", 0.0)

        if not force and (now - last_checked < self.throttle_seconds):
            return cached.get("updates", {})

        cfg = self._load_config()
        installed_modules = cfg.get("installed_modules", {})
        default_provider = cfg.get("default_provider", "")

        updates: Dict[str, Any] = {}

        if isinstance(installed_modules, dict):
            for mod_name, mod_info in installed_modules.items():
                if isinstance(mod_info, dict):
                    cur_ver = mod_info.get("version", "")
                    provider_url = mod_info.get("provider") or default_provider
                else:
                    cur_ver = str(mod_info)
                    provider_url = default_provider

                if not cur_ver or cur_ver == "build" or cur_ver.endswith(".build"):
                    continue

                latest_ver = self._fetch_latest_version(mod_name, provider_url)
                if latest_ver:
                    try:
                        if semver.compare_semver(latest_ver, cur_ver) > 0:
                            updates[mod_name] = {
                                "current_version": cur_ver,
                                "latest_version": latest_ver,
                                "has_update": True,
                                "provider": provider_url
                            }
                    except Exception:
                        pass

        new_cache_data = {
            "last_checked_at": now,
            "updates": updates
        }
        self._save_cache(new_cache_data)
        return updates

    def _fetch_latest_version(self, module_name: str, provider_url: str) -> Optional[str]:
        if not provider_url:
            return None

        # 1. 本地目錄探測 (路徑不以 http/https 開頭)
        if not provider_url.startswith(("http://", "https://")):
            # 解算本機路徑
            resolved_p = provider_url
            if not os.path.isabs(resolved_p):
                try:
                    proj_root = uri.resolve("project://", interactive=False)
                    resolved_p = os.path.normpath(os.path.join(proj_root, provider_url))
                except Exception:
                    resolved_p = os.path.abspath(provider_url)

            cand_paths = [
                os.path.join(resolved_p, module_name, "index.json"),
                os.path.join(resolved_p, "release", module_name, "index.json"),
                os.path.join(resolved_p, "build", module_name, "index.json"),
            ]
            for cp in cand_paths:
                if os.path.isfile(cp):
                    try:
                        with open(cp, "r", encoding="utf-8") as f:
                            idx = json.load(f)
                        if isinstance(idx, dict) and "versions" in idx and isinstance(idx["versions"], list):
                            return semver.find_best_version(idx["versions"])
                    except Exception:
                        pass
            return None

        # 2. 遠端 HTTP 探測 (2秒超時，靜默例外)
        try:
            url = f"{provider_url.rstrip('/')}/{module_name}/index.json"
            req = urllib.request.Request(url, headers={"User-Agent": "yscb-update-checker/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, dict) and "versions" in data and isinstance(data["versions"], list):
                        return semver.find_best_version(data["versions"])
        except Exception:
            pass

        return None

    def get_tips(self, updates: Optional[Dict[str, Any]] = None) -> List[str]:
        """讀取更新資訊並生成非阻塞提示清單。"""
        if updates is None:
            cached = self._load_cache()
            updates = cached.get("updates", {})

        tips: List[str] = []
        if isinstance(updates, dict):
            for mod, info in updates.items():
                if isinstance(info, dict) and info.get("has_update"):
                    cur_v = info.get("current_version", "")
                    lat_v = info.get("latest_version", "")
                    tips.append(
                        f"💡 提示: 模組 '{mod}' 有新版本可用 (當前: v{cur_v}, 最新: v{lat_v})。"
                        f" 可執行 'python yscb.py update {mod}' 進行升級。"
                    )
        return tips

    def print_tips_if_available(self) -> None:
        """非阻塞輸出更新提示至 stderr/stdout。"""
        tips = self.get_tips()
        if tips:
            print("\n" + "\n".join(tips))
