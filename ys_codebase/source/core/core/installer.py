"""
Core Package Management Installer Subcommands (install, update, remove, list, status, rollback, reload).
Includes Major Boundary Lock & Incremental Migration Trigger.
"""
import os
import json
from typing import Optional, List, Dict, Tuple, Any, Sequence, Union
from core import uri
from core import vfs
from core.context import ExecutionContext
from core.engine import (
    AtomicEngine,
    DEFAULT_PROVIDER_URL,
    _extract_zip_safely,
    _atomic_swap_dir,
    _is_build_version_request,
    _parse_dependencies,
    compute_file_sha256,
    find_matching_local_source_dir,
    normalize_legacy_provider_url,
    package_local_source_if_exact_match,
    resolve_local_provider_path,
)
from core import semver
from core import events
from core.log import log, log_error, log_info, log_warn

INTERNAL_IGNORE_PATTERNS = (
    "/.modules/",
    "/.build/",
    "/.mirror/",
    "/.temp/",
    "/.snapshots/",
    "/.cache/",
    "/.config.local/",
    "/.storage.local/",
    "/.venv/",
    "*.local.json",
    "__pycache__/",
    "*.pyc",
    "yscb.py.bak",
    "*.bak",
)


def generate_internal_gitignore(yscb_dir: str) -> None:
    """
    相容性委派層：將內部 `.gitignore` 管理統一收斂至 `core.gitignore.sync()`。
    若傳入之 `yscb_dir` 為獨立測試目錄（非當前活躍工作區之 `yscb://`），
    則以對應之專案根目錄執行 `core.gitignore.sync`；否則直接同步全專案 `project://.gitignore`。
    """
    from core import gitignore as gi_mod

    if not yscb_dir:
        gi_mod.sync()
        return

    abs_dir = os.path.abspath(yscb_dir)
    base_name = os.path.basename(abs_dir)
    if base_name in ("ys_codebase", ".yscb", "engine") and os.path.isfile(
        os.path.join(os.path.dirname(abs_dir), "yscb.config.json")
    ):
        proj_dir = os.path.dirname(abs_dir)
        gi_mod.sync(proj_root=proj_dir, yscb_root=abs_dir)
    else:
        default_yscb = ""
        try:
            default_yscb = os.path.abspath(uri.resolve("yscb://", interactive=False))
        except Exception:
            pass
        if default_yscb and os.path.normcase(os.path.realpath(abs_dir)) == os.path.normcase(os.path.realpath(default_yscb)):
            gi_mod.sync()
        else:
            gi_mod.sync(proj_root=abs_dir, yscb_root=abs_dir)


def fetch_and_extract_zip(source_url_or_path: str, dest_dir: str) -> None:
    """從本機路徑或遠端 URL 提取 Zip 壓縮檔至同父目錄 .staging 臨時空間，驗證無誤後原子替換至 dest_dir，嚴防 Zip Slip 與非原子撕裂。"""
    import urllib.request
    import tempfile
    import time
    import shutil
    import zipfile

    dest_abs = os.path.abspath(dest_dir)
    parent_dir = os.path.dirname(dest_abs)
    base_name = os.path.basename(dest_abs)
    os.makedirs(parent_dir, exist_ok=True)
    staging_dir = os.path.join(parent_dir, f".staging_{base_name}_{os.getpid()}_{int(time.time() * 1000)}")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)
    os.makedirs(staging_dir, exist_ok=True)

    try:
        if source_url_or_path.startswith("file://"):
            source_url_or_path = resolve_local_provider_path(source_url_or_path) or source_url_or_path

        if source_url_or_path.startswith(("http://", "https://")):
            req = urllib.request.Request(source_url_or_path, headers={"User-Agent": "yscb-core/2.0"})
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_f:
                tmp_path = tmp_f.name
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    with open(tmp_path, "wb") as out_f:
                        shutil.copyfileobj(resp, out_f)
                if not zipfile.is_zipfile(tmp_path):
                    raise RuntimeError(f"Downloaded payload from '{source_url_or_path}' is not a valid zip file.")
                _extract_zip_safely(tmp_path, staging_dir, source_label=source_url_or_path)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        else:
            file_path = os.path.abspath(source_url_or_path)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Source file or directory '{source_url_or_path}' does not exist.")
            if os.path.isdir(file_path):
                shutil.copytree(file_path, staging_dir, dirs_exist_ok=True)
            elif zipfile.is_zipfile(file_path):
                _extract_zip_safely(file_path, staging_dir, source_label=source_url_or_path)
            else:
                raise RuntimeError(f"Source path '{source_url_or_path}' is neither a directory nor a valid zip file.")

        _atomic_swap_dir(staging_dir, dest_abs)
    finally:
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)


def _discover_available_versions_for_module(
    engine: AtomicEngine,
    mod: str,
    provider_url: str,
    candidate_core_version: Optional[str] = None,
) -> List[str]:
    """Scans local provider directories/indexes or fetches remote index.json for non-build, environment-compatible versions of a module."""
    local_prov = resolve_local_provider_path(provider_url)
    candidate_dirs = (
        [
            os.path.join(local_prov, "release", mod),
            os.path.join(local_prov, mod),
        ]
        if local_prov
        else []
    )
    found_versions: List[str] = []
    releases_map: Dict[str, Any] = {}
    for c_dir in candidate_dirs:
        if os.path.isdir(c_dir):
            for entry in os.listdir(c_dir):
                full_p = os.path.join(c_dir, entry)
                if os.path.isdir(full_p):
                    found_versions.append(entry)
                elif entry.endswith(".zip") and not entry.endswith(".build.zip"):
                    found_versions.append(entry[:-4])
            idx_file = os.path.join(c_dir, "index.json")
            if os.path.isfile(idx_file):
                try:
                    with open(idx_file, "r", encoding="utf-8") as f:
                        idx_data = json.load(f)
                        if isinstance(idx_data, dict):
                            engine._cache_release_index_to_mirror(mod, idx_data)
                            if "versions" in idx_data and isinstance(idx_data["versions"], list):
                                found_versions.extend(idx_data["versions"])
                            if isinstance(idx_data.get("releases"), dict):
                                releases_map.update(idx_data["releases"])
                except Exception:
                    pass

    if not found_versions:
        ok, res = engine.act_fetch(provider_url, f"{mod}/index.json")
        if ok and isinstance(res, dict):
            engine._cache_release_index_to_mirror(mod, res)
            if "versions" in res and isinstance(res["versions"], list):
                found_versions = res["versions"]
            if isinstance(res.get("releases"), dict):
                releases_map.update(res["releases"])

    clean_versions: List[str] = []
    for v in found_versions:
        try:
            vt = semver.parse_semver(v)
            if vt.is_build or str(v).endswith(".build"):
                continue
            rel_entry = releases_map.get(v) if isinstance(releases_map, dict) else None
            if isinstance(rel_entry, dict) and isinstance(rel_entry.get("dependencies"), dict):
                if not engine._is_dependencies_compatible_with_env(
                    rel_entry["dependencies"],
                    candidate_core_version=candidate_core_version,
                ):
                    continue
            clean_versions.append(v)
        except Exception:
            pass
    return clean_versions


def _discover_remote_modules(engine: AtomicEngine, provider_url: str, installed: Dict[str, Any]) -> Dict[str, str]:
    """Scans local or remote provider for all available modules and their latest versions."""
    available_modules: Dict[str, str] = {}
    local_base = resolve_local_provider_path(provider_url)

    if local_base and os.path.isdir(local_base):
        sub_dirs = [local_base]
        rel_dir = os.path.join(local_base, "release")
        if os.path.isdir(rel_dir):
            sub_dirs.append(rel_dir)
        for search_dir in sub_dirs:
            try:
                for entry in os.listdir(search_dir):
                    idx_file = os.path.join(search_dir, entry, "index.json")
                    if os.path.isfile(idx_file):
                        try:
                            with open(idx_file, "r", encoding="utf-8") as f:
                                idx_data = json.load(f)
                                latest = idx_data.get("latest") or (
                                    idx_data.get("versions", [None])[-1]
                                    if isinstance(idx_data.get("versions"), list)
                                    else "unknown"
                                )
                                if latest:
                                    available_modules[entry] = str(latest)
                        except Exception:
                            pass
            except Exception:
                pass

    if not available_modules:
        ok, res = engine.act_fetch(provider_url, "index.json")
        if ok and isinstance(res, dict):
            mods_dict = res.get("modules", {})
            if isinstance(mods_dict, dict):
                for m, m_info in mods_dict.items():
                    latest = m_info.get("latest") if isinstance(m_info, dict) else str(m_info)
                    available_modules[m] = latest or "unknown"

    if not available_modules:
        candidate_mods = set(
            list(installed.keys())
            + ["core", "dev", "server", "ast", "knowledge-db", "agents-workflow"]
        )
        for m in sorted(candidate_mods):
            ok, res = engine.act_fetch(provider_url, f"{m}/index.json")
            if ok and isinstance(res, dict):
                latest = res.get("latest") or (
                    res.get("versions", [None])[-1] if isinstance(res.get("versions"), list) else None
                )
                if latest:
                    available_modules[m] = str(latest)

    return available_modules


def _notify_server_release_handles(yscb_root: Optional[str] = None) -> bool:
    """
    在執行模組安裝、更新、移除或還原前，若偵測到常駐 Server 正在運行，
    主動發送輕量 HTTP POST /api/reload 請求通知 Server 重啟 Worker 以釋放 .pyd/.dll 等檔案句柄。
    任何網路或狀態異常皆靜默容錯，絕不阻斷主安裝流程。
    """
    import urllib.request
    try:
        if not yscb_root:
            host_dir, _ = uri._get_host_config()
            cfg_p = os.path.join(host_dir, "yscb.config.json")
            yscb_rel = "."
            if vfs.is_file(cfg_p):
                cfg_d = vfs.read_json(cfg_p)
                if isinstance(cfg_d, dict):
                    yscb_rel = cfg_d.get("yscb_root", ".")
            yscb_root = os.path.normpath(os.path.join(host_dir, yscb_rel))

        state_file = os.path.join(yscb_root, ".cache", "server", "daemon.json")
        if not os.path.isfile(state_file):
            return False

        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not isinstance(state, dict):
            return False

        port = state.get("port")
        token = state.get("token")
        if not port or not token:
            return False

        url = f"http://127.0.0.1:{port}/api/reload"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _cleanup_stale_old_dirs(parent_dir: str) -> None:
    """非阻塞清理 parent_dir 下歷史遺留之 .old_* 與 .staging_* 目錄；若仍被鎖定則靜默跳過延遲回收。"""
    from core.engine import _cleanup_stale_swap_dirs
    try:
        _cleanup_stale_swap_dirs(parent_dir)
    except Exception:
        pass


def _print_restore_failure_guidance(mod_name: str, ver: str, prov: str) -> None:
    """Prints diagnostic recovery steps when restoring a module fails."""
    log_error(f"[core:restore] 錯誤: '{mod_name}' 模組 (v{ver}) 來源 '{prov}' 已遺失或無法存取，需手動修復。")
    log_info("               建議措施為:")
    if mod_name == "core":
        log_info("                 1. 修復核心模組並切換來源 : python yscb.py init --fix [--provider <valid_url_or_path>]")
    else:
        log_info(f"                 1. 重新指定來源安裝該模組 : python yscb.py install {mod_name} --force [--provider <valid_url_or_path>]")
    log_info("                 2. 以指定來源全量還原環境 : python yscb.py restore --force --provider <valid_url_or_path>")
    log_info(f"                 3. 檢查並修正 'yscb.config.json' 中 '{mod_name}' 的 version / provider 設定")


class Installer:
    def __init__(self) -> None:
        self.engine = AtomicEngine()

    def _check_optional_dependencies(self, module_name: str) -> None:
        """
        走訪已安裝模組之 manifest.json 中宣告的 optional 擴充模組。
        若工作區尚未安裝該模組，於終端輸出結構化建議卡片與安裝指令引導。
        """
        try:
            manifest_uri = f"module://{module_name}/manifest.json"
            if not vfs.exists(manifest_uri):
                return
            m_data = vfs.read_json(manifest_uri)
            if not isinstance(m_data, dict):
                return
            optional_deps = m_data.get("optional", {})
            if not isinstance(optional_deps, dict) or not optional_deps:
                return

            _, cfg = self.engine._get_config()
            installed = cfg.get("installed_modules", {})

            missing_optionals: List[Tuple[str, str, str]] = []
            for opt_mod, opt_info in optional_deps.items():
                if opt_mod in installed and vfs.exists(f"module://{opt_mod}"):
                    continue
                ver_range = ""
                hint = ""
                if isinstance(opt_info, dict):
                    ver_range = str(opt_info.get("version", ""))
                    hint = str(opt_info.get("hint", ""))
                elif isinstance(opt_info, str):
                    ver_range = opt_info
                missing_optionals.append((opt_mod, ver_range, hint))

            if missing_optionals:
                log("\n[*] 偵測到可用的擴充模組 (Optional Modules):")
                for opt_mod, ver_range, hint in missing_optionals:
                    ver_str = f" ({ver_range})" if ver_range else ""
                    hint_str = f": {hint}" if hint else ""
                    log(f"    - {opt_mod}{ver_str}{hint_str}")
                    log(f"      (可執行: python yscb.py install {opt_mod} 啟用完整能力)")
                log()
        except Exception:
            pass

    def _print_onboarding_guide(self, module_name: str) -> None:
        """
        讀取 module://{module_name}/manifest.json 中選填之 'onboarding' 步驟清單，
        於模組安裝完成後輸出結構化 Next Steps 引導卡片。
        """
        try:
            manifest_uri = f"module://{module_name}/manifest.json"
            if not vfs.exists(manifest_uri):
                return
            m_data = vfs.read_json(manifest_uri)
            if not isinstance(m_data, dict):
                return
            raw_steps = m_data.get("onboarding")
            if not isinstance(raw_steps, list):
                return
            steps = [s.strip() for s in raw_steps if isinstance(s, str) and s.strip()]
            if not steps:
                return

            log(f"\n[*] Next Steps for '{module_name}':")
            for idx, step in enumerate(steps, 1):
                log(f"    {idx}. {step}")
            readme_uri = f"module://{module_name}/README.md"
            if vfs.exists(readme_uri):
                log(f"    * Quickstart & Manual: .modules/{module_name}/README.md")
        except Exception:
            pass

    @staticmethod
    def _normalize_ver_constraint(ver_str: Optional[str]) -> Optional[str]:
        if not ver_str:
            return None
        v_clean = str(ver_str).strip()
        if not v_clean:
            return None
        if v_clean == "build" or v_clean.endswith(".build"):
            return v_clean
        return semver.normalize_version(v_clean)

    def _parse_install_requests(
        self,
        module_name: Union[str, Sequence[str]],
        version: Optional[str] = None,
    ) -> List[Tuple[str, Optional[str]]]:
        """Normalizes single or sequence module specifiers into a list of (mod_name, ver_constraint) tuples."""
        raw_items: List[str] = []
        if isinstance(module_name, str):
            s = module_name.strip()
            if s:
                raw_items.append(s)
        elif isinstance(module_name, Sequence):
            for item in module_name:
                s = str(item).strip() if item is not None else ""
                if s:
                    raw_items.append(s)

        fallback_ver = self._normalize_ver_constraint(version)
        requests: List[Tuple[str, Optional[str]]] = []
        for spec in raw_items:
            if "@" in spec:
                m_name, m_ver = spec.split("@", 1)
                m_name = m_name.strip()
                norm_v = self._normalize_ver_constraint(m_ver)
            else:
                m_name = spec.strip()
                norm_v = fallback_ver
            if m_name:
                requests.append((m_name, norm_v))
        return requests

    @staticmethod
    def _normalize_target_names(module_name: Optional[Union[str, Sequence[str]]]) -> List[str]:
        """Normalizes single or sequence module names into a deduplicated, order-preserving list."""
        if module_name is None:
            return []
        raw_list: List[str] = [module_name] if isinstance(module_name, str) else [str(x) for x in module_name if x is not None]
        seen = set()
        result: List[str] = []
        for item in raw_list:
            clean = item.strip()
            if clean and clean not in seen:
                seen.add(clean)
                result.append(clean)
        return result

    def cmd_install(
        self,
        module_name: Union[str, Sequence[str]],
        version: Optional[str] = None,
        provider: Optional[str] = None,
        force: bool = False,
        ignore_sha256: bool = False,
    ) -> int:
        try:
            requests = self._parse_install_requests(module_name, version)
        except Exception as e:
            log_error(f"[core:install] Error parsing module version specification: {e}")
            return 1

        if not requests:
            log_error("[core:install] Error: Module name is required.")
            return 1

        _, cfg = self.engine._get_config()
        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            log_error("[core:install] Error: No default_provider configured in yscb.config.json and no --provider specified.")
            return 1

        req_names_ordered: List[str] = []
        for m_name, _ in requests:
            if m_name not in req_names_ordered:
                req_names_ordered.append(m_name)

        label_str = ", ".join(req_names_ordered)
        snap_suffix = req_names_ordered[0] if len(req_names_ordered) == 1 else f"batch_{len(req_names_ordered)}"
        log_info(f"[core:install] Resolving dependencies for '{label_str}'...")

        try:
            with self.engine.transaction_lock("install"):
                _, cfg = self.engine._get_config()
                installed = cfg.get("installed_modules", {})
                old_versions: Dict[str, str] = {
                    mod: (installed.get(mod, {}).get("version", "0.0.0.0") if isinstance(installed.get(mod, {}), dict) else str(installed.get(mod)))
                    for mod in set(list(installed.keys()) + req_names_ordered)
                }
                snap_id = self.engine.act_snapshot(f"pre_install_{snap_suffix}")
                try:
                    _notify_server_release_handles()
                    if len(requests) == 1:
                        targets = self.engine.act_solve_deps(requests[0][0], requests[0][1], provider_url)
                    else:
                        targets = self.engine.act_solve_deps(requests, None, provider_url)
                    self.engine.act_prepare(targets, provider_url, force=force, ignore_sha256=ignore_sha256)
                    resolved_map: Dict[str, str] = {}
                    for mod, ver in targets:
                        self.engine.act_register(mod, ver, provider_url)
                        resolved_map[mod] = ver
                    self.engine.act_reload(clean_stage=True, inject_stage=True, ignore_sha256=ignore_sha256)

                    for mod, installed_ver in targets:
                        old_ver = old_versions.get(mod, "0.0.0.0")
                        if old_ver != "0.0.0.0" and semver.compare_semver(installed_ver, old_ver) > 0:
                            log_info(f"[core:install] Running migration ladder for '{mod}' ({old_ver} -> {installed_ver})...")
                            self.engine.act_migrate(mod, old_ver, installed_ver)

                    for req_mod in req_names_ordered:
                        inst_v = resolved_map.get(req_mod, "1.0.0.0")
                        events.broadcast("on_installed", ExecutionContext("core", "install", [req_mod, inst_v]), emit_module="core")

                    self.sync_pip_dependencies()
                    try:
                        from core.update_checker import UpdateChecker
                        checker = UpdateChecker()
                        for req_mod in req_names_ordered:
                            checker.invalidate_cache(req_mod)
                    except Exception:
                        pass
                except Exception as e:
                    log_error(f"[core:install] Error during install: {e}")
                    self.engine.act_restore_snapshot(snap_id)
                    return 1

            for req_mod in req_names_ordered:
                inst_v = resolved_map.get(req_mod, "1.0.0.0")
                log_info(f"[core:install] Successfully installed '{req_mod}@{inst_v}'.")
                if old_versions.get(req_mod, "0.0.0.0") == "0.0.0.0":
                    self._print_onboarding_guide(req_mod)
                    self._check_optional_dependencies(req_mod)
            return 0
        except Exception as e:
            log_error(f"[core:install] Error acquiring install lock: {e}")
            return 1

    def cmd_update(
        self,
        module_name: Optional[Union[str, Sequence[str]]] = None,
        provider: Optional[str] = None,
        ignore_sha256: bool = False,
    ) -> int:
        _, cfg = self.engine._get_config()
        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            log_error("[core:update] Error: No default_provider configured in yscb.config.json and no --provider specified.")
            return 1

        installed = cfg.get("installed_modules", {})
        explicit_targets = self._normalize_target_names(module_name)
        if explicit_targets:
            missing_mods = [m for m in explicit_targets if m not in installed]
            if missing_mods:
                for m in missing_mods:
                    log_error(f"[core:update] Error: Module '{m}' is not currently installed.")
                return 1
            targets = explicit_targets
        else:
            targets = list(installed.keys())

        if not targets:
            log_info("[core:update] No modules installed to update.")
            return 0

        log_info(f"[core:update] Checking updates for modules: {', '.join(targets)} (Major Lock active)...")

        updated_any = False
        updated_mods: List[str] = []
        migrations_to_run: List[Tuple[str, str, str]] = []
        newly_installed_deps: List[Tuple[str, str]] = []
        try:
            with self.engine.transaction_lock("update"):
                snap_id = self.engine.act_snapshot("pre_update")
                try:
                    _notify_server_release_handles()
                    ordered_targets = sorted(targets, key=lambda m: (0 if m == "core" else 1, targets.index(m)))
                    candidate_core_ver: Optional[str] = None
                    for mod in ordered_targets:
                        cur_ver = installed.get(mod, {}).get("version", "1.0.0.0") if isinstance(installed.get(mod, {}), dict) else str(installed.get(mod))
                        cur_t = semver.parse_semver(cur_ver)

                        if cur_t.is_build or cur_ver == "build" or str(cur_ver).endswith(".build"):
                            log_info(f"[core:update] Module '{mod}' is a development build (v{cur_ver}), skipping update.")
                            continue

                        major_constraint = f"^{cur_t.major}.{cur_t.minor}.{cur_t.patch}"
                        clean_versions = _discover_available_versions_for_module(
                            self.engine,
                            mod,
                            provider_url,
                            candidate_core_version=candidate_core_ver,
                        )
                        best_v = semver.find_best_version(clean_versions, major_constraint)
                        latest_ver = best_v if best_v else cur_ver

                        if semver.compare_semver(latest_ver, cur_ver) > 0:
                            log_info(f"[core:update] Updating '{mod}' from {cur_ver} -> {latest_ver}...")
                            self.engine.act_prepare([(mod, latest_ver)], provider_url, force=True, ignore_sha256=ignore_sha256)
                            self.engine.act_register(mod, latest_ver, provider_url)
                            migrations_to_run.append((mod, cur_ver, latest_ver))
                            updated_any = True
                            if mod not in updated_mods:
                                updated_mods.append(mod)
                            if mod == "core":
                                candidate_core_ver = latest_ver
                        else:
                            log_info(f"[core:update] Module '{mod}' is already up-to-date (v{cur_ver}).")

                    # Reconcile dependencies across all installed & newly updated modules
                    healed_deps = self.engine.reconcile_installed_dependencies(
                        provider_url=provider_url, ignore_sha256=ignore_sha256
                    )
                    for h_mod, h_old, h_new in healed_deps:
                        updated_any = True
                        if h_old is None:
                            log_info(f"[core:update] Installing required dependency '{h_mod}@{h_new}'...")
                            newly_installed_deps.append((h_mod, h_new))
                        elif semver.compare_semver(h_new, h_old) > 0:
                            log_info(f"[core:update] Auto-upgrading dependency '{h_mod}' from {h_old} -> {h_new}...")
                            migrations_to_run.append((h_mod, h_old, h_new))
                            if h_mod not in updated_mods:
                                updated_mods.append(h_mod)

                    if updated_any:
                        self.engine.act_reload(clean_stage=True, inject_stage=True, ignore_sha256=ignore_sha256)
                        for mod, old_v, new_v in migrations_to_run:
                            self.engine.act_migrate(mod, old_v, new_v)
                        for dep_mod, dep_ver in newly_installed_deps:
                            events.broadcast(
                                "on_installed",
                                ExecutionContext("core", "install", [dep_mod, dep_ver]),
                                emit_module="core",
                            )
                        if updated_mods:
                            events.broadcast(
                                "on_update",
                                ExecutionContext("core", "update", updated_mods),
                                emit_module="core",
                            )
                        self.sync_pip_dependencies()
                        for dep_mod, _dep_ver in newly_installed_deps:
                            self._print_onboarding_guide(dep_mod)
                            self._check_optional_dependencies(dep_mod)
                        log_info("[core:update] Update completed successfully.")
                    try:
                        from core.update_checker import UpdateChecker
                        checker = UpdateChecker()
                        for m in set(list(targets) + [h[0] for h in healed_deps]):
                            checker.invalidate_cache(m)
                    except Exception:
                        pass
                except Exception as e:
                    log_error(f"[core:update] Error during update: {e}")
                    self.engine.act_restore_snapshot(snap_id)
                    return 1
            return 0
        except Exception as e:
            log_error(f"[core:update] Error acquiring update lock: {e}")
            return 1

    def cmd_remove(
        self,
        module_name: Union[str, Sequence[str]],
        clean: bool = False,
        purge: bool = False,
        force: bool = False,
    ) -> int:
        targets = self._normalize_target_names(module_name)
        if not targets:
            log_error("[core:remove] Error: Module name is required.")
            return 1

        if "core" in targets:
            log_error("[core:remove] Error: Cannot remove 'core' infrastructure module.")
            return 1

        _, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})

        for mod in targets:
            if mod not in installed:
                log_error(f"[core:remove] Module '{mod}' is not currently installed.")
                return 1

        target_set = set(targets)
        for mod in targets:
            dependents: List[str] = []
            for other_mod in installed.keys():
                if other_mod in target_set:
                    continue
                manifest_uri = f"module://{other_mod}/manifest.json"
                if vfs.exists(manifest_uri):
                    try:
                        m_data = vfs.read_json(manifest_uri)
                        deps = _parse_dependencies(m_data.get("dependencies", {}))
                        if mod in deps:
                            dependents.append(other_mod)
                    except Exception:
                        pass

            if dependents:
                if not force:
                    log_error(
                        f"[core:remove] Error: Cannot remove '{mod}' because it is required by: "
                        f"{', '.join(dependents)}. Use --force to override."
                    )
                    return 1
                log_warn(f"[core:remove] Warning: Force removing '{mod}' required by: {', '.join(dependents)}.")

        snap_suffix = targets[0] if len(targets) == 1 else f"batch_{len(targets)}"
        try:
            with self.engine.transaction_lock("remove"):
                snap_id = self.engine.act_snapshot(f"pre_remove_{snap_suffix}")
                try:
                    _notify_server_release_handles()
                    events.broadcast("on_remove", ExecutionContext("core", "remove", list(targets)), emit_module="core")
                    for mod in targets:
                        log_info(f"[core:remove] Removing module '{mod}'...")
                        self.engine.act_unregister(mod)
                        self.engine.act_delete(mod, clean_mirror=clean, purge=purge)
                    self.engine.act_reload(clean_stage=True, inject_stage=True, reconcile_deps=False)
                    self.sync_pip_dependencies()
                except Exception as e:
                    log_error(f"[core:remove] Error during remove: {e}")
                    self.engine.act_restore_snapshot(snap_id)
                    return 1
            for mod in targets:
                if purge:
                    log_info(f"[core:remove] Module '{mod}' and all its persistent data/config purged successfully.")
                else:
                    log_info(f"[core:remove] Module '{mod}' removed successfully (cache cleared, storage/config preserved).")
            return 0
        except Exception as e:
            log_error(f"[core:remove] Error acquiring remove lock: {e}")
            return 1

    def cmd_list(self, remote: bool = False, provider: Optional[str] = None) -> int:
        _, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})

        if not remote:
            log("-" * 65)
            log(f"{'Module Name':<20} {'Version':<10} {'Provider':<15} {'Status':<15}")
            log("-" * 65)
            if not installed:
                log("  (No modules installed)")
            else:
                for mod, meta in installed.items():
                    ver = meta.get("version", "unknown") if isinstance(meta, dict) else str(meta)
                    prov = meta.get("provider", "local") if isinstance(meta, dict) else "local"
                    status = "Installed" if vfs.exists(f"module://{mod}") else "Missing files"
                    log(f"{mod:<20} {ver:<10} {prov:<15} {status:<15}")
            log("-" * 65)
            return 0

        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            log_error("[core:list] Error: No default_provider configured and no --provider specified.")
            return 1

        log("-" * 75)
        log(f"{'Module Name':<20} {'Latest Ver':<12} {'Provider':<25} {'Local Status':<15}")
        log("-" * 75)

        available_modules = _discover_remote_modules(self.engine, provider_url, installed)
        if not available_modules:
            log(f"  (No remote modules found at provider: {provider_url})")
            log("-" * 75)
            return 1

        for mod in sorted(available_modules.keys()):
            latest_ver = available_modules[mod]
            if mod in installed:
                loc_ver = installed[mod].get("version", "unknown") if isinstance(installed[mod], dict) else str(installed[mod])
                loc_status = f"Installed (v{loc_ver})"
            else:
                loc_status = "Available"
            log(f"{mod:<20} {latest_ver:<12} {provider_url:<25} {loc_status:<15}")

        log("-" * 75)
        return 0

    def cmd_status(self) -> int:
        _, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})

        log("=" * 60)
        log("YS-Codebase Core Health Diagnostic Report")
        log("=" * 60)
        log(f"YS-Codebase Root : {cfg.get('yscb_root', 'unknown')}")
        log(f"Total Modules    : {len(installed)}")

        healthy = True
        for mod, meta in installed.items():
            mod_exists = vfs.exists(f"module://{mod}/manifest.json")
            cli_exists = vfs.exists(f"module://{mod}/scripts/cli.py")
            if not mod_exists or not cli_exists:
                healthy = False
                log_warn(f"  [!] {mod}: Incomplete (manifest={mod_exists}, cli={cli_exists})")
            else:
                log(f"  [*] {mod}@{meta.get('version') if isinstance(meta, dict) else meta}: Healthy")

        log("-" * 60)
        log(f"Overall Status   : {'HEALTHY (100% Ready)' if healthy else 'DEGRADED (Run reload)'}")
        log("=" * 60)
        return 0 if healthy else 1

    def cmd_rollback(self, target: Optional[str] = None) -> int:
        if not vfs.exists("snapshot://"):
            log_error("[core:rollback] No snapshots found.")
            return 1

        snap_root = uri.resolve("snapshot://")

        def _snap_sort_key(name: str) -> Tuple[float, str]:
            try:
                return (os.path.getmtime(os.path.join(snap_root, name)), name)
            except OSError:
                return (0.0, name)

        snaps = sorted(vfs.listdir("snapshot://"), key=_snap_sort_key)
        if not snaps:
            log_error("[core:rollback] No snapshots available.")
            return 1

        target_snap = target or snaps[-1]
        log_info(f"[core:rollback] Rolling back to snapshot '{target_snap}'...")
        try:
            with self.engine.transaction_lock("rollback"):
                _notify_server_release_handles()
                self.engine.act_restore_snapshot(target_snap)
                self.sync_pip_dependencies()
            log_info(f"[core:rollback] Successfully restored to '{target_snap}'.")
            return 0
        except Exception as e:
            log_error(f"[core:rollback] Rollback failed: {e}")
            return 1

    def cmd_reload(self) -> int:
        log_info("[core:reload] Reconciling runtime modules from mirror...")
        with self.engine.transaction_lock("reload"):
            self.engine.act_reload(clean_stage=True, inject_stage=True)
            self.sync_pip_dependencies()
            try:
                _, cfg = self.engine._get_config()
                host_dir, _ = uri._get_host_config()
                yscb_abs = os.path.normpath(os.path.join(host_dir, cfg.get("yscb_root", ".")))
                generate_internal_gitignore(yscb_abs)
            except Exception:
                pass
            log_info("[core:reload] Runtime environment reconciled and refreshed successfully.")
            return 0

    def cmd_restore(self, force: bool = False, provider: Optional[str] = None, ignore_sha256: bool = False) -> int:
        """
        CLI 指令：python yscb.py restore [--force] [--provider <url>] [--ignore-sha256]
        讀取 yscb.config.json 之 installed_modules 清冊，批量還原所有模組至 .modules/，
        並於完成後自動觸發 reload 重聚環境；若中途發生未預期異常則回滾至 pre_restore 快照。
        """
        cfg_path, cfg = self.engine._get_config()
        if not cfg_path or not cfg:
            log_error("[core:restore] Error: Configuration not found.")
            return 1

        host_dir, _ = uri._get_host_config()
        yscb_abs = os.path.normpath(os.path.join(host_dir, cfg.get("yscb_root", ".")))
        generate_internal_gitignore(yscb_abs)

        installed = cfg.get("installed_modules", {})
        if not installed:
            log_info("[core:restore] No installed_modules declared in configuration. Nothing to restore.")
            return 0

        default_provider = normalize_legacy_provider_url(
            cfg.get(
                "default_provider",
                DEFAULT_PROVIDER_URL,
            )
        )
        modules_dir = os.path.join(yscb_abs, ".modules")
        os.makedirs(modules_dir, exist_ok=True)

        log_info(f"[core:restore] Restoring {len(installed)} module(s) to '{modules_dir}'...")
        success_count = 0
        failed_mods: List[str] = []
        materialized_mods: List[str] = []
        migrations_to_run: List[Tuple[str, str, str]] = []

        with self.engine.transaction_lock("restore"):
            snap_id = self.engine.act_snapshot("pre_restore")
            try:
                _notify_server_release_handles(yscb_abs)
                _cleanup_stale_old_dirs(modules_dir)
                mod_keys = sorted(installed.keys(), key=lambda x: (0 if x == "core" else 1, x))
                for mod_name in mod_keys:
                    mod_info = installed[mod_name]
                    ver = mod_info.get("version", "1.0.0.0") if isinstance(mod_info, dict) else str(mod_info)
                    prov = provider or (mod_info.get("provider", default_provider) if isinstance(mod_info, dict) else default_provider)
                    dest = os.path.join(modules_dir, mod_name)
                    mirror = os.path.join(yscb_abs, ".mirror", mod_name)
                    mf_path = os.path.join(dest, "manifest.json")
                    installed_ver = None
                    if os.path.isdir(dest) and os.path.isfile(mf_path):
                        try:
                            mf_data = vfs.read_json(mf_path)
                            if isinstance(mf_data, dict) and mf_data.get("version"):
                                installed_ver = str(mf_data["version"])
                        except Exception:
                            installed_ver = None

                    if not force and os.path.isdir(dest) and os.path.isfile(mf_path):
                        if ver == "build" or installed_ver == ver:
                            log_info(f"  -> Skipping '{mod_name}@{ver}' (already installed, use --force to overwrite)")
                            success_count += 1
                            materialized_mods.append(mod_name)
                            continue

                    log_info(f"  -> Restoring '{mod_name}@{ver}'...")
                    ok = self._restore_module_package(
                        host_dir, cfg.get("yscb_root", "."), mod_name, ver, prov, dest, mirror, ignore_sha256=ignore_sha256
                    )
                    if ok:
                        effective_ver = ver
                        try:
                            _, latest_cfg = self.engine._get_config()
                            latest_inst = latest_cfg.get("installed_modules", {})
                            if isinstance(latest_inst, dict) and mod_name in latest_inst:
                                m_meta = latest_inst[mod_name]
                                cfg_ver = m_meta.get("version") if isinstance(m_meta, dict) else str(m_meta)
                                if cfg_ver:
                                    effective_ver = str(cfg_ver)
                        except Exception:
                            pass
                        self.engine._apply_release_index_override_to_staging(mod_name, effective_ver, dest)
                        self.engine._deploy_and_strip_single_module_config(mod_name, dest)
                        success_count += 1
                        materialized_mods.append(mod_name)
                        if installed_ver and installed_ver != "0.0.0.0":
                            try:
                                if semver.compare_semver(effective_ver, installed_ver) > 0:
                                    migrations_to_run.append((mod_name, installed_ver, effective_ver))
                            except Exception:
                                pass
                    else:
                        _print_restore_failure_guidance(mod_name, ver, prov)
                        failed_mods.append(mod_name)

                if failed_mods:
                    log_warn(f"[core:restore] Warning: Completed with {len(failed_mods)} failure(s): {', '.join(failed_mods)}")
                else:
                    log_info(f"[core:restore] Successfully restored all {success_count} module(s).")

                log_info("[core:restore] Triggering reload...")
                self.engine.act_reload(
                    clean_stage=True,
                    inject_stage=True,
                    ignore_sha256=ignore_sha256,
                    skip_materialize_modules=materialized_mods,
                )
                for m_mod, m_old, m_new in migrations_to_run:
                    self.engine.act_migrate(m_mod, m_old, m_new)
                self.sync_pip_dependencies()
                try:
                    generate_internal_gitignore(yscb_abs)
                except Exception:
                    pass
                log_info("[core:reload] Runtime environment reconciled and refreshed successfully.")
                return 0 if not failed_mods else 1
            except Exception as e:
                log_error(f"[core:restore] Error during restore: {e}")
                self.engine.act_restore_snapshot(snap_id)
                return 1

    def _resolve_same_triplet_fallback_version(
        self,
        base_dir: str,
        provider_arg: str,
        module_name: str,
        requested_version: str,
    ) -> Optional[str]:
        """Resolves the highest available active version in the same triplet (X.Y.Z.*) when requested_version has been pruned."""
        return self.engine._resolve_same_triplet_fallback_version(
            module_name, requested_version, provider_arg, base_dir=base_dir
        )

    def _restore_module_package(
        self,
        base_dir: str,
        yscb_root: str,
        module_name: str,
        version: str,
        provider_arg: str,
        dest_dir: str,
        mirror_dir: str,
        _allow_fallback: bool = True,
        ignore_sha256: bool = False,
    ) -> bool:
        """自 Provider、Build 或本機 Mirror 提取指定版本模組，原子解壓縮至 dest_dir。"""
        import zipfile
        import shutil
        os.makedirs(os.path.dirname(os.path.abspath(dest_dir)), exist_ok=True)
        os.makedirs(mirror_dir, exist_ok=True)

        provider_arg = normalize_legacy_provider_url(provider_arg)
        yscb_abs = os.path.normpath(os.path.join(base_dir, yscb_root))
        mirror_zip = os.path.join(mirror_dir, f"{version}.zip")

        # 1. 優先檢查 yscb_abs 下的 .build/ 或 release/
        build_candidates = [
            os.path.join(yscb_abs, ".build", module_name, f"{version}.zip"),
            os.path.join(yscb_abs, ".build", module_name, f"{version}.build.zip"),
            os.path.join(yscb_abs, ".build", module_name, f"{version}"),
            os.path.join(yscb_abs, "release", module_name, f"{version}.zip"),
        ]
        found_b = next((c for c in build_candidates if os.path.exists(c)), None)
        if not found_b and (version == "build" or version.endswith(".build")):
            dot_build_mod_dir = os.path.join(yscb_abs, ".build", module_name)
            if os.path.isdir(dot_build_mod_dir):
                build_zips = sorted(
                    [
                        os.path.join(dot_build_mod_dir, f)
                        for f in os.listdir(dot_build_mod_dir)
                        if f.endswith(".build.zip") and os.path.isfile(os.path.join(dot_build_mod_dir, f))
                    ],
                    key=lambda p: os.path.getmtime(p),
                    reverse=True,
                )
                if build_zips:
                    found_b = build_zips[0]
                    new_build_ver = os.path.basename(found_b)[:-4]
                    mirror_zip = os.path.join(mirror_dir, f"{new_build_ver}.zip")
                    try:
                        cfg_p = os.path.join(base_dir, "yscb.config.json")
                        if vfs.is_file(cfg_p):
                            cfg_d = vfs.read_json(cfg_p)
                            if isinstance(cfg_d, dict) and isinstance(cfg_d.get("installed_modules"), dict):
                                m_entry = cfg_d["installed_modules"].get(module_name)
                                if isinstance(m_entry, dict):
                                    m_entry["version"] = new_build_ver
                                    vfs.write_json(cfg_p, cfg_d, indent=2, atomic=True)
                    except Exception:
                        pass
        if found_b:
            is_newer = not os.path.isfile(mirror_zip) or (os.path.getmtime(found_b) >= os.path.getmtime(mirror_zip))
            if version == "build" or version.endswith(".build") or is_newer:
                copied_to_mirror = False
                try:
                    if os.path.isfile(found_b) and (found_b.endswith(".zip") or zipfile.is_zipfile(found_b)):
                        os.makedirs(mirror_dir, exist_ok=True)
                        if os.path.abspath(found_b) != os.path.abspath(mirror_zip):
                            shutil.copy2(found_b, mirror_zip)
                            copied_to_mirror = True
                        if not _is_build_version_request(version) and found_b.endswith(".zip"):
                            self.engine._verify_zip_sha256(
                                module_name, version, mirror_zip, provider_arg, ignore_sha256=ignore_sha256
                            )
                        fetch_and_extract_zip(mirror_zip, dest_dir)
                    else:
                        fetch_and_extract_zip(found_b, dest_dir)
                    return True
                except Exception:
                    if copied_to_mirror and os.path.isfile(mirror_zip):
                        try:
                            os.remove(mirror_zip)
                        except OSError:
                            pass

        # 2. 檢查本地鏡像庫 (.mirror/<mod>/<ver>.zip)
        if os.path.isfile(mirror_zip):
            try:
                fetch_and_extract_zip(mirror_zip, dest_dir)
                return True
            except Exception:
                pass

        # 3. 檢查 Provider 路徑 (local folder)
        p_abs = resolve_local_provider_path(provider_arg, base_dir=base_dir)

        if p_abs and os.path.isdir(p_abs):
            candidates = [
                os.path.join(p_abs, module_name, f"{version}.zip"),
                os.path.join(p_abs, module_name, f"{version}"),
                os.path.join(p_abs, module_name),
                os.path.join(p_abs, "release", module_name, f"{version}.zip"),
                os.path.join(p_abs, ".build", module_name, f"{version}.zip"),
            ]
            for cand in candidates:
                if not os.path.exists(cand):
                    continue
                if os.path.isdir(cand) and not os.path.isfile(os.path.join(cand, "manifest.json")):
                    continue
                copied_cand_to_mirror = False
                try:
                    if os.path.isfile(cand) and (cand.endswith(".zip") or zipfile.is_zipfile(cand)):
                        if os.path.abspath(cand) != os.path.abspath(mirror_zip):
                            shutil.copy2(cand, mirror_zip)
                            copied_cand_to_mirror = True
                        self.engine._verify_zip_sha256(module_name, version, mirror_zip, p_abs, ignore_sha256=ignore_sha256)
                        fetch_and_extract_zip(mirror_zip, dest_dir)
                    else:
                        fetch_and_extract_zip(cand, dest_dir)
                    return True
                except Exception:
                    if copied_cand_to_mirror and os.path.isfile(mirror_zip):
                        try:
                            os.remove(mirror_zip)
                        except OSError:
                            pass

        # 3b. 本地同版 source/<mod> 動態打包自給自足（僅寫入 .mirror/，絕不反向寫入 release/）
        src_dir = find_matching_local_source_dir(module_name, [yscb_abs, p_abs or "", base_dir])
        if src_dir and package_local_source_if_exact_match(src_dir, version, mirror_zip, release_zip_path=None):
            try:
                fetch_and_extract_zip(mirror_zip, dest_dir)
                return True
            except Exception:
                pass

        # 4. 遠端 Provider (HTTP/HTTPS)
        if provider_arg.startswith(("http://", "https://", "file://")):
            try:
                self.engine._download_from_remote_tier(
                    module_name, version, provider_arg, mirror_zip, f"module.mirror://{module_name}/{version}.zip",
                    ignore_sha256=ignore_sha256,
                )
                fetch_and_extract_zip(mirror_zip, dest_dir)
                return True
            except Exception:
                pass

        # 5. 若鎖定版本已被滑動視窗淘汰 (pruned)，自動退回同三元組 (X.Y.Z.*) 最高可用 active 版本
        if _allow_fallback:
            fallback_ver = self._resolve_same_triplet_fallback_version(base_dir, provider_arg, module_name, version)
            if fallback_ver and fallback_ver != version:
                log_info(
                    f"[core:restore] Exact revision '{module_name}@{version}' has been pruned upstream; "
                    f"seamlessly restoring compatible same-triplet revision '{fallback_ver}'."
                )
                ok = self._restore_module_package(
                    base_dir,
                    yscb_root,
                    module_name,
                    fallback_ver,
                    provider_arg,
                    dest_dir,
                    mirror_dir,
                    _allow_fallback=False,
                    ignore_sha256=ignore_sha256,
                )
                if ok:
                    try:
                        cfg_p = os.path.join(base_dir, "yscb.config.json")
                        if vfs.is_file(cfg_p):
                            cfg_d = vfs.read_json(cfg_p)
                            if isinstance(cfg_d, dict):
                                inst_d = cfg_d.get("installed_modules")
                                if not isinstance(inst_d, dict):
                                    inst_d = {}
                                    cfg_d["installed_modules"] = inst_d
                                if isinstance(inst_d.get(module_name), dict):
                                    inst_d[module_name]["version"] = fallback_ver
                                else:
                                    inst_d[module_name] = {
                                        "version": fallback_ver,
                                        "provider": provider_arg,
                                    }
                                vfs.write_json(cfg_p, cfg_d, indent=2, atomic=True)
                    except Exception:
                        pass
                    return True

        return False

    def sync_pip_dependencies(self) -> None:
        """
        收集所有已安裝模組之 pip_dependencies 宣告聯集，
        透過 PipManager 於微環境執行 Wheel-Only 靜默物化；
        隨後廣播 on_env_synced 生命週期事件供訂閱模組（如 vscode-support）同步環境路徑。
        """
        from core.pip_manager import PipManager, PipInstallError

        try:
            _, cfg = self.engine._get_config()
        except Exception:
            return

        installed = cfg.get("installed_modules", {})
        raw_specs: List[str] = []
        for mod in installed.keys():
            manifest_uri = f"module://{mod}/manifest.json"
            if vfs.exists(manifest_uri):
                try:
                    m_data = vfs.read_json(manifest_uri)
                    pip_deps = m_data.get("pip_dependencies", {})
                    raw_specs.extend(PipManager.parse_pip_dependencies(pip_deps))
                except Exception:
                    pass

        specs = PipManager.parse_pip_dependencies(raw_specs)

        yscb_abs = None
        if "yscb_root" in cfg:
            host_dir, _ = uri._get_host_config()
            yscb_abs = os.path.normpath(os.path.join(host_dir, cfg["yscb_root"]))

        pip_mgr = PipManager(yscb_abs)
        if specs:
            try:
                pip_mgr.install_packages(specs)
            except PipInstallError as e:
                log_warn(f"[core:pip] Warning: {e}")

        try:
            events.broadcast("on_env_synced", ExecutionContext("core", "env_sync", []), emit_module="core")
        except Exception:
            pass
