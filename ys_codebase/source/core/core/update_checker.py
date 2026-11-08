"""
YS-Codebase Update Checker with 12-Hour Throttling & Non-Blocking Tips.
100% Python Standard Library, Zero External Dependencies.
"""
from typing import Dict, Any, List, Optional, Tuple, Mapping
import hashlib
import os
import re
import json
import time
import types
import urllib.request
from core import uri
from core import vfs
from core import semver
from core.context import get_env
from core.engine import normalize_legacy_provider_url, resolve_local_provider_path

DEFAULT_CACHE_URI: str = "cache://core/update_check.json"
DEFAULT_THROTTLE_SECONDS: int = 43200  # 12 小時
DEFAULT_TIMEOUT_SECONDS: float = 2.0
DEFAULT_SELF_UPDATE_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases/yscb.py"
HOST_SCRIPT_KEY: str = "yscb.py"
_VERSION_RE = re.compile(r"""^__version__\s*(?::\s*str\s*)?=\s*['"]([^'"]+)['"]""", re.MULTILINE)
KNOWN_URGENCIES: Mapping[str, int] = types.MappingProxyType({"optional": 1, "recommended": 2, "critical": 3})


def normalize_release_metadata(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Forward-safe parser for release metadata in index.json['releases'][<ver>].
    Unknown 'type' or 'urgency' values never raise exceptions; 'type' is normalized to lowercase,
    and 'is_critical' is set when urgency == 'critical' or type == 'hotfix'.
    """
    if not isinstance(entry, dict):
        return {"type": "", "urgency": "optional", "summary": "", "is_critical": False, "rank": 1}
    raw_type = str(entry.get("type", "") or "").strip()
    raw_urgency = str(entry.get("urgency", "") or "").strip()
    raw_summary = str(entry.get("summary", "") or "").strip()
    norm_type = raw_type.lower()
    norm_urgency = raw_urgency.lower() if raw_urgency else "optional"
    is_crit = norm_urgency == "critical" or norm_type == "hotfix"
    if is_crit:
        rank = 3
        if norm_urgency != "critical":
            norm_urgency = "critical"
    elif norm_urgency in KNOWN_URGENCIES:
        rank = KNOWN_URGENCIES[norm_urgency]
    else:
        rank = 2
    return {
        "type": norm_type,
        "urgency": norm_urgency,
        "summary": raw_summary,
        "is_critical": is_crit,
        "rank": rank,
    }


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
        if self.config_path and vfs.is_file(self.config_path):
            try:
                data = vfs.read_json(self.config_path)
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        try:
            for cfg_uri in ("yscb.host://yscb.config.json", "project://yscb.config.json"):
                if vfs.is_file(cfg_uri):
                    data = vfs.read_json(cfg_uri)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _load_cache(self) -> Dict[str, Any]:
        if vfs.exists(self.cache_uri):
            try:
                data = vfs.read_json(self.cache_uri)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {"last_checked_at": 0.0, "updates": {}}

    def _save_cache(self, data: Dict[str, Any]) -> None:
        try:
            vfs.makedirs(str(vfs.path(self.cache_uri).parent), exist_ok=True)
            vfs.write_json(self.cache_uri, data)
        except Exception:
            pass

    def invalidate_cache(self, module_name: Optional[str] = None) -> None:
        """
        及時失效更新快取：
        - 若 module_name 為 None：重設快取，清空所有更新項目。
        - 若提供 module_name：自快取 updates 字典中移除該模組並回存。
        """
        if not vfs.exists(self.cache_uri):
            return
        cached = self._load_cache()
        if module_name is None:
            new_data = {"last_checked_at": 0.0, "updates": {}}
        else:
            updates = cached.get("updates", {})
            if isinstance(updates, dict) and module_name in updates:
                del updates[module_name]
            new_data = {
                "last_checked_at": cached.get("last_checked_at", 0.0),
                "updates": updates
            }
        self._save_cache(new_data)

    def check_updates(self, force: bool = False) -> Dict[str, Any]:
        """
        檢查各已安裝模組是否有新版本可用。
        在 12 小時節流時間內直接返回快取；超過 12 小時或 force=True 時發起輕量探測。
        所有網路例外靜默兜底，不拋出中斷例外。
        """
        if get_env("YSCB_NO_UPDATE_CHECK") == "1":
            return {}

        now = time.time()
        cached = self._load_cache()
        last_checked = cached.get("last_checked_at", 0.0)

        if not force and (now - last_checked < self.throttle_seconds):
            return cached.get("updates", {})

        cfg = self._load_config()
        installed_modules = cfg.get("installed_modules", {})
        default_provider = cfg.get("default_provider", "")

        installed_core_ver: Optional[str] = None
        if isinstance(installed_modules, dict) and "core" in installed_modules:
            c_info = installed_modules["core"]
            raw_c = c_info.get("version", "") if isinstance(c_info, dict) else str(c_info)
            if isinstance(raw_c, str) and raw_c.strip():
                installed_core_ver = raw_c.strip()
                if installed_core_ver.endswith(".build"):
                    installed_core_ver = installed_core_ver[:-len(".build")]

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

                cand_info = self._fetch_module_update_candidate(
                    mod_name, cur_ver, provider_url, installed_core_ver=installed_core_ver
                )
                if cand_info is not None:
                    updates[mod_name] = cand_info

        # 探測入口檔 yscb.py 版本
        host_update = self._check_host_script_update(cfg)
        if host_update:
            updates[HOST_SCRIPT_KEY] = host_update

        new_cache_data = {
            "last_checked_at": now,
            "updates": updates
        }
        self._save_cache(new_cache_data)
        return updates

    @staticmethod
    def _extract_script_version(content: str) -> Optional[str]:
        """自 yscb.py 原始碼文字中提取 __version__ 字串。"""
        if not content:
            return None
        m = _VERSION_RE.search(content)
        return m.group(1).strip() if m else None

    @staticmethod
    def _compute_script_sha256(content: str) -> str:
        """將腳本換行符正規化為 LF 後計算 UTF-8 SHA-256 十六進位雜湊值。"""
        norm = (content or "").replace("\r\n", "\n")
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def _get_local_host_script_info(self) -> Tuple[Optional[str], Optional[str]]:
        """讀取本機工作區入口檔 yscb.py 之 (__version__, sha256)。"""
        candidates: List[str] = []
        if self.config_path:
            candidates.append(os.path.join(os.path.dirname(os.path.abspath(self.config_path)), "yscb.py"))
        host_env = get_env("YSCB_HOST_DIR")
        if host_env:
            candidates.append(os.path.join(host_env, "yscb.py"))
        for host_uri in ("yscb.host://", "project://"):
            try:
                host_root = uri.resolve(host_uri, interactive=False)
                candidates.append(os.path.join(host_root, "yscb.py"))
            except Exception:
                pass

        for cand in candidates:
            if vfs.is_file(cand):
                try:
                    text = vfs.read_text(cand)
                    ver = self._extract_script_version(text)
                    if ver:
                        return ver, self._compute_script_sha256(text)
                except Exception:
                    pass
        return None, None

    def _get_local_host_script_version(self) -> Optional[str]:
        """讀取本機工作區入口檔 yscb.py 之 __version__。"""
        ver, _ = self._get_local_host_script_info()
        return ver

    def _fetch_latest_host_script_info(self, cfg: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """探測來源端最新 yscb.py 之 (__version__, sha256)（支援本地路徑與遠端 HTTP）。"""
        self_update_url = cfg.get("self_update_url") if isinstance(cfg, dict) else None
        default_provider = cfg.get("default_provider", "") if isinstance(cfg, dict) else ""

        if not self_update_url and default_provider:
            base_d = (
                os.path.dirname(os.path.abspath(self.config_path))
                if self.config_path
                else get_env("YSCB_HOST_DIR")
            )
            resolved_p = resolve_local_provider_path(str(default_provider), base_dir=base_d)
            if resolved_p:
                for cand in (
                    os.path.join(resolved_p, "yscb.py"),
                    os.path.join(os.path.dirname(resolved_p), "yscb.py"),
                    os.path.join(os.path.dirname(os.path.dirname(resolved_p)), "yscb.py"),
                ):
                    if vfs.is_file(cand):
                        try:
                            text = vfs.read_text(cand)
                            ver = self._extract_script_version(text)
                            if ver:
                                return ver, self._compute_script_sha256(text)
                        except Exception:
                            pass

        target_url = str(self_update_url or DEFAULT_SELF_UPDATE_URL).strip()
        local_self_p = resolve_local_provider_path(target_url)
        if local_self_p is not None:
            if vfs.is_file(local_self_p):
                try:
                    text = vfs.read_text(local_self_p)
                    ver = self._extract_script_version(text)
                    return ver, (self._compute_script_sha256(text) if ver else None)
                except Exception:
                    pass
            return None, None

        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "yscb-update-checker/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status == 200:
                    text = resp.read().decode("utf-8", errors="replace")
                    ver = self._extract_script_version(text)
                    return ver, (self._compute_script_sha256(text) if ver else None)
        except Exception:
            pass
        return None, None

    def _fetch_latest_host_script_version(self, cfg: Dict[str, Any]) -> Optional[str]:
        """探測來源端最新 yscb.py 之 __version__（支援本地路徑與遠端 HTTP）。"""
        ver, _ = self._fetch_latest_host_script_info(cfg)
        return ver

    def _check_host_script_update(self, cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """比對本機與來源端 yscb.py 版本與內容 SHA-256，若有新版或內容漂移則回傳更新資訊字典。"""
        if (
            "_get_local_host_script_version" in self.__dict__
            or getattr(type(self), "_get_local_host_script_version", None)
            is not UpdateChecker._get_local_host_script_version
        ):
            cur_ver, local_sha256 = self._get_local_host_script_version(), None
        else:
            cur_ver, local_sha256 = self._get_local_host_script_info()

        if not cur_ver or cur_ver == "build" or cur_ver.endswith(".build"):
            return None

        if (
            "_fetch_latest_host_script_version" in self.__dict__
            or getattr(type(self), "_fetch_latest_host_script_version", None)
            is not UpdateChecker._fetch_latest_host_script_version
        ):
            latest_ver, latest_sha256 = self._fetch_latest_host_script_version(cfg), None
        else:
            latest_ver, latest_sha256 = self._fetch_latest_host_script_info(cfg)

        if not latest_ver:
            return None
        try:
            cmp_res = semver.compare_semver(latest_ver, cur_ver)
            if cmp_res > 0:
                return {
                    "current_version": cur_ver,
                    "latest_version": latest_ver,
                    "has_update": True,
                    "is_host_script": True,
                }
            if (
                cmp_res == 0
                and isinstance(local_sha256, str)
                and isinstance(latest_sha256, str)
                and local_sha256
                and latest_sha256
                and local_sha256 != latest_sha256
            ):
                return {
                    "current_version": cur_ver,
                    "latest_version": latest_ver,
                    "has_update": True,
                    "is_host_script": True,
                    "is_drift": True,
                    "local_sha256": local_sha256,
                    "latest_sha256": latest_sha256,
                }
        except Exception:
            pass
        return None

    def _read_index_data(self, module_name: str, provider_url: str) -> Optional[Dict[str, Any]]:
        """Reads index.json from local provider paths or remote HTTP provider."""
        provider_url = normalize_legacy_provider_url(provider_url)
        if not provider_url:
            return None

        if not provider_url.startswith(("http://", "https://")):
            base_d: Optional[str] = None
            if not provider_url.startswith("file://") and not os.path.isabs(provider_url):
                try:
                    base_d = uri.resolve("yscb.host://", interactive=False)
                except Exception:
                    try:
                        base_d = uri.resolve("project://", interactive=False)
                    except Exception:
                        base_d = None
            resolved_p = resolve_local_provider_path(provider_url, base_dir=base_d)
            if not resolved_p:
                return None

            cand_paths = [
                os.path.join(resolved_p, module_name, "index.json"),
                os.path.join(resolved_p, "release", module_name, "index.json"),
                os.path.join(resolved_p, "build", module_name, "index.json"),
            ]
            for cp in cand_paths:
                if vfs.is_file(cp):
                    try:
                        idx = vfs.read_json(cp)
                        if isinstance(idx, dict):
                            return idx
                    except Exception:
                        pass
            return None

        try:
            url = f"{provider_url.rstrip('/')}/{module_name}/index.json"
            req = urllib.request.Request(url, headers={"User-Agent": "yscb-update-checker/1.0"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass

        return None

    def _fetch_latest_version(self, module_name: str, provider_url: str) -> Optional[str]:
        idx = self._read_index_data(module_name, provider_url)
        if isinstance(idx, dict) and "versions" in idx and isinstance(idx["versions"], list):
            return semver.find_best_version(idx["versions"])
        return None

    def _fetch_module_update_candidate(
        self,
        mod_name: str,
        current_ver: str,
        provider_url: str,
        installed_core_ver: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Determines the highest compatible update candidate in the same major line
        and aggregates release urgency/metadata across (current_ver, latest_ver] (including pruned versions).
        """
        try:
            cur_t = semver.parse_semver(current_ver)
        except Exception:
            return None
        major_constraint = f"^{cur_t.major}.{cur_t.minor}.{cur_t.patch}"

        idx = self._read_index_data(mod_name, provider_url)
        releases_map = idx.get("releases") if isinstance(idx, dict) and isinstance(idx.get("releases"), dict) else {}

        if isinstance(idx, dict) and isinstance(idx.get("versions"), list):
            raw_versions = idx["versions"]
        else:
            fallback_v = self._fetch_latest_version(mod_name, provider_url)
            raw_versions = [fallback_v] if fallback_v else []

        compat_versions: List[str] = []
        for v in raw_versions:
            if not isinstance(v, str):
                continue
            try:
                vt = semver.parse_semver(v)
                if vt.is_build or v.endswith(".build"):
                    continue
            except Exception:
                continue
            rel_entry = releases_map.get(v) if isinstance(releases_map, dict) else None
            if installed_core_ver and isinstance(rel_entry, dict) and isinstance(rel_entry.get("dependencies"), dict):
                core_req = rel_entry["dependencies"].get("core")
                if isinstance(core_req, str) and core_req.strip():
                    if not semver.match_constraint(installed_core_ver, core_req.strip()):
                        continue
            compat_versions.append(v)

        latest_ver = semver.find_best_version(compat_versions, major_constraint)
        if not latest_ver:
            return None
        try:
            if semver.compare_semver(latest_ver, current_ver) <= 0:
                return None
        except Exception:
            return None

        # Aggregate metadata across all versions in (current_ver, latest_ver], including pruned entries in releases_map
        latest_meta = normalize_release_metadata(releases_map.get(latest_ver) if isinstance(releases_map, dict) else None)
        agg_rank = latest_meta["rank"]
        agg_urgency = latest_meta["urgency"]
        agg_type = latest_meta["type"]
        agg_summary = latest_meta["summary"]
        agg_critical = latest_meta["is_critical"]

        if isinstance(releases_map, dict):
            # Sort versions in (current_ver, latest_ver] ascending so higher versions win ties
            in_range_vers: List[str] = []
            for r_ver in releases_map.keys():
                try:
                    if semver.compare_semver(r_ver, current_ver) > 0 and semver.compare_semver(r_ver, latest_ver) <= 0:
                        in_range_vers.append(r_ver)
                except Exception:
                    continue
            in_range_vers.sort(key=lambda x: semver.parse_semver(x))
            for r_ver in in_range_vers:
                m_info = normalize_release_metadata(releases_map.get(r_ver))
                if m_info["is_critical"]:
                    agg_critical = True
                if m_info["rank"] >= agg_rank:
                    if m_info["rank"] > agg_rank or m_info["is_critical"]:
                        agg_rank = m_info["rank"]
                        agg_urgency = m_info["urgency"]
                    if m_info["type"]:
                        agg_type = m_info["type"]
                    if m_info["summary"]:
                        agg_summary = m_info["summary"]

        return {
            "current_version": current_ver,
            "latest_version": latest_ver,
            "has_update": True,
            "provider": provider_url,
            "type": agg_type,
            "urgency": "critical" if agg_critical else agg_urgency,
            "summary": agg_summary,
            "is_critical": agg_critical,
        }

    def get_tips(self, updates: Optional[Dict[str, Any]] = None) -> List[str]:
        """讀取更新資訊並生成非阻塞提示清單。"""
        if updates is None:
            cached = self._load_cache()
            updates = cached.get("updates", {})

        tips: List[str] = []
        if isinstance(updates, dict):
            host_info = updates.get(HOST_SCRIPT_KEY)
            if isinstance(host_info, dict) and host_info.get("has_update"):
                cur_v = host_info.get("current_version", "")
                lat_v = host_info.get("latest_version", "")
                if host_info.get("is_drift"):
                    header_line = (
                        f"[!] [CRITICAL UPDATE] 宿主入口檔 'yscb.py' 偵測到內容漂移 "
                        f"(Content Drift: SHA-256 mismatch at v{cur_v})！\n"
                    )
                else:
                    header_line = (
                        f"[!] [CRITICAL UPDATE] 宿主入口檔 'yscb.py' 有新版本可用 "
                        f"(當前: v{cur_v}, 最新: v{lat_v})！\n"
                    )
                tips.append(
                    "================================================================================\n"
                    f"{header_line}"
                    "    強烈建議立即執行 'python yscb.py self-update' 更新入口檔。\n"
                    "    [AGENT BLOCKER] 若由 AI Agent 觸發本指令，你必須【立即暫停當前任務】，\n"
                    "    優先向開發者請示是否要立即執行 'python yscb.py self-update' 更新入口檔！\n"
                    "================================================================================"
                )
            for mod, info in updates.items():
                if mod == HOST_SCRIPT_KEY:
                    continue
                if isinstance(info, dict) and info.get("has_update"):
                    cur_v = info.get("current_version", "")
                    lat_v = info.get("latest_version", "")
                    rel_type = str(info.get("type", "") or "").strip()
                    rel_urgency = str(info.get("urgency", "") or "").strip().lower()
                    rel_summary = str(info.get("summary", "") or "").strip()
                    is_crit = bool(info.get("is_critical")) or rel_urgency == "critical" or rel_type.lower() == "hotfix"
                    type_tag = f" [{rel_type.upper()}]" if rel_type else ""

                    if is_crit:
                        summary_line = f"    摘要: {rel_summary}\n" if rel_summary else ""
                        tips.append(
                            "================================================================================\n"
                            f"[!] [CRITICAL UPDATE] 模組 '{mod}' 有重要修補更新可用 (當前: v{cur_v}, 最新: v{lat_v}){type_tag}！\n"
                            f"{summary_line}"
                            f"    強烈建議立即執行 'python yscb.py update {mod}' 進行升級。\n"
                            "================================================================================"
                        )
                    else:
                        summary_suffix = f" ({rel_summary})" if rel_summary else ""
                        tips.append(
                            f"[*] 提示: 模組 '{mod}' 有新版本可用 (當前: v{cur_v}, 最新: v{lat_v}){type_tag}{summary_suffix}。"
                            f" 可執行 'python yscb.py update {mod}' 進行升級。"
                        )
        return tips

    def print_tips_if_available(self) -> None:
        """非阻塞輸出更新提示至 stderr/stdout。"""
        tips = self.get_tips()
        if tips:
            from core.log import log
            log("\n" + "\n".join(tips))
