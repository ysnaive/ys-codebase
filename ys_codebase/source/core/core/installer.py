"""
Core Package Management Installer Subcommands (install, update, remove, list, status, rollback, reload).
Includes Major Boundary Lock & Incremental Migration Trigger.
"""
import os
import json
from typing import Optional, List, Dict, Tuple, Any
from core import uri
from core import vfs
from core.context import ExecutionContext
from core.engine import AtomicEngine, _extract_zip_safely, _atomic_swap_dir, _parse_dependencies
from core import semver
from core import events

INTERNAL_IGNORE_BEGIN = "# === YSCB INTERNAL IGNORE BEGIN ==="
INTERNAL_IGNORE_END = "# === YSCB INTERNAL IGNORE END ==="
INTERNAL_IGNORE_PATTERNS = [
    "/.modules/",
    "/.build/",
    "/.mirror/",
    "/.temp/",
    "/.snapshots/",
    "/.cache/",
    "/.venv/",
    "*.local.json",
    "__pycache__/",
    "*.pyc",
    "yscb.py.bak",
    "*.bak",
]


def generate_internal_gitignore(yscb_dir: str) -> None:
    """
    非破壞性軟合併 yscb://.gitignore 中的 YSCB 內部管理區塊。
    支援 'yscb://' == 'project://' 之拓撲情境，完整保留宿主專案既有之自訂忽略規則
    及其他模組之管理區塊，杜絕粗暴覆蓋導致的設定丟失。
    """
    import re
    gi_path = os.path.join(yscb_dir, ".gitignore")
    block_lines = [
        INTERNAL_IGNORE_BEGIN,
        "# Auto-managed by YSCB host bootstrapper. Do not edit this block manually.",
        *INTERNAL_IGNORE_PATTERNS,
        INTERNAL_IGNORE_END,
    ]
    new_block_text = "\n".join(block_lines)

    existing_content = ""
    has_existing = vfs.is_file(gi_path)
    if has_existing:
        try:
            existing_content = vfs.read_text(gi_path)
        except Exception:
            existing_content = ""

    pattern_marker = re.compile(
        rf"{re.escape(INTERNAL_IGNORE_BEGIN)}[\s\S]*?{re.escape(INTERNAL_IGNORE_END)}",
        re.MULTILINE,
    )
    pattern_legacy = re.compile(
        r"# YS-Codebase Autonomous Internal Ignore Rules\n(?:(?!\n*# ===)[^\n]+\n*)*",
        re.MULTILINE,
    )

    if pattern_marker.search(existing_content):
        merged_content = pattern_marker.sub(new_block_text, existing_content)
    elif pattern_legacy.search(existing_content):
        merged_content = pattern_legacy.sub(new_block_text + "\n", existing_content)
    else:
        if existing_content and not existing_content.endswith("\n"):
            merged_content = existing_content + "\n\n" + new_block_text + "\n"
        elif existing_content:
            merged_content = existing_content + new_block_text + "\n"
        else:
            merged_content = new_block_text + "\n"

    if has_existing and existing_content == merged_content:
        return

    try:
        vfs.write_text(gi_path, merged_content, atomic=True)
    except Exception:
        pass


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
            raw_p = urllib.request.url2pathname(source_url_or_path[7:])
            while raw_p.startswith("//"):
                raw_p = raw_p[1:]
            source_url_or_path = raw_p

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


def _discover_available_versions_for_module(engine: AtomicEngine, mod: str, provider_url: str) -> List[str]:
    """Scans local provider directories/indexes or fetches remote index.json for non-build versions of a module."""
    candidate_dirs = [
        os.path.join(provider_url, "release", mod),
        os.path.join(provider_url, mod),
    ]
    found_versions: List[str] = []
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
                        if isinstance(idx_data, dict) and "versions" in idx_data:
                            found_versions.extend(idx_data["versions"])
                except Exception:
                    pass

    if not found_versions:
        ok, res = engine.act_fetch(provider_url, f"{mod}/index.json")
        if ok and isinstance(res, dict) and "versions" in res:
            found_versions = res["versions"]

    clean_versions: List[str] = []
    for v in found_versions:
        try:
            vt = semver.parse_semver(v)
            if not vt.is_build and not str(v).endswith(".build"):
                clean_versions.append(v)
        except Exception:
            pass
    return clean_versions


def _discover_remote_modules(engine: AtomicEngine, provider_url: str, installed: Dict[str, Any]) -> Dict[str, str]:
    """Scans local or remote provider for all available modules and their latest versions."""
    available_modules: Dict[str, str] = {}
    local_base = None
    if provider_url.startswith("file://"):
        import urllib.request
        local_base = urllib.request.url2pathname(provider_url[7:])
    elif not provider_url.startswith(("http://", "https://")):
        local_base = os.path.normpath(provider_url)

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
        candidate_mods = set(list(installed.keys()) + ["core", "dev", "server", "knowledge-db", "agents-workflow"])
        for m in sorted(candidate_mods):
            ok, res = engine.act_fetch(provider_url, f"{m}/index.json")
            if ok and isinstance(res, dict):
                latest = res.get("latest") or (
                    res.get("versions", [None])[-1] if isinstance(res.get("versions"), list) else None
                )
                if latest:
                    available_modules[m] = str(latest)

    return available_modules


def _print_restore_failure_guidance(mod_name: str, ver: str, prov: str) -> None:
    """Prints diagnostic recovery steps when restoring a module fails."""
    print(f"[core:restore] 錯誤: '{mod_name}' 模組 (v{ver}) 來源 '{prov}' 已遺失或無法存取，需手動修復。")
    print("               建議措施為:")
    if mod_name == "core":
        print("                 1. 修復核心模組並切換來源 : python yscb.py init --fix [--provider <valid_url_or_path>]")
    else:
        print(f"                 1. 重新指定來源安裝該模組 : python yscb.py install {mod_name} --force [--provider <valid_url_or_path>]")
    print("                 2. 以指定來源全量還原環境 : python yscb.py restore --force --provider <valid_url_or_path>")
    print(f"                 3. 檢查並修正 'yscb.config.json' 中 '{mod_name}' 的 version / provider 設定")


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
                print("\n[*] 偵測到可用的擴充模組 (Optional Modules):")
                for opt_mod, ver_range, hint in missing_optionals:
                    ver_str = f" ({ver_range})" if ver_range else ""
                    hint_str = f": {hint}" if hint else ""
                    print(f"    - {opt_mod}{ver_str}{hint_str}")
                    print(f"      (可執行: python yscb.py install {opt_mod} 啟用完整能力)")
                print()
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

            print(f"\n[*] Next Steps for '{module_name}':")
            for idx, step in enumerate(steps, 1):
                print(f"    {idx}. {step}")
            readme_uri = f"module://{module_name}/README.md"
            if vfs.exists(readme_uri):
                print(f"    * Quickstart & Manual: .modules/{module_name}/README.md")
        except Exception:
            pass

    def cmd_install(self, module_name: str, version: Optional[str] = None, provider: Optional[str] = None, force: bool = False) -> int:
        if not module_name:
            print("[core:install] Error: Module name is required.")
            return 1

        _, cfg = self.engine._get_config()
        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            print("[core:install] Error: No default_provider configured in yscb.config.json and no --provider specified.")
            return 1

        if version and (version == "build" or version.endswith(".build")):
            ver_constraint = version
        else:
            ver_constraint = semver.normalize_version(version) if version else None

        print(f"[core:install] Resolving dependencies for '{module_name}'...")
        snap_id = self.engine.act_snapshot(f"pre_install_{module_name}")

        installed = cfg.get("installed_modules", {})
        old_ver = installed.get(module_name, {}).get("version", "0.0.0.0")

        try:
            with self.engine.transaction_lock("install"):
                targets = self.engine.act_solve_deps(module_name, ver_constraint, provider_url)
                self.engine.act_prepare(targets, provider_url, force=force)
                installed_ver = "1.0.0.0"
                for mod, ver in targets:
                    self.engine.act_register(mod, ver, provider_url)
                    if mod == module_name:
                        installed_ver = ver
                self.engine.act_reload(clean_stage=True, inject_stage=True)

                if old_ver != "0.0.0.0" and semver.compare_semver(installed_ver, old_ver) > 0:
                    print(f"[core:install] Running migration ladder for '{module_name}' ({old_ver} -> {installed_ver})...")
                    self.engine.act_migrate(module_name, old_ver, installed_ver)

                events.broadcast("on_installed", ExecutionContext("core", "install", [module_name, installed_ver]), emit_module="core")
                self.sync_pip_dependencies()
                try:
                    from core.update_checker import UpdateChecker
                    UpdateChecker().invalidate_cache(module_name)
                except Exception:
                    pass
            print(f"[core:install] Successfully installed '{module_name}@{installed_ver}'.")
            if old_ver == "0.0.0.0":
                self._print_onboarding_guide(module_name)
                self._check_optional_dependencies(module_name)
            return 0
        except Exception as e:
            print(f"[core:install] Error during install: {e}")
            self.engine.act_restore_snapshot(snap_id)
            return 1

    def cmd_update(self, module_name: Optional[str] = None, provider: Optional[str] = None) -> int:
        _, cfg = self.engine._get_config()
        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            print("[core:update] Error: No default_provider configured in yscb.config.json and no --provider specified.")
            return 1

        installed = cfg.get("installed_modules", {})
        targets = [module_name] if module_name else list(installed.keys())
        if not targets:
            print("[core:update] No modules installed to update.")
            return 0

        print(f"[core:update] Checking updates for modules: {', '.join(targets)} (Major Lock active)...")
        snap_id = self.engine.act_snapshot("pre_update")

        updated_any = False
        migrations_to_run: List[Tuple[str, str, str]] = []
        try:
            with self.engine.transaction_lock("update"):
                for mod in targets:
                    cur_ver = installed.get(mod, {}).get("version", "1.0.0.0")
                    cur_t = semver.parse_semver(cur_ver)

                    if cur_t.is_build or cur_ver == "build" or str(cur_ver).endswith(".build"):
                        print(f"[core:update] Module '{mod}' is a development build (v{cur_ver}), skipping update.")
                        continue

                    major_constraint = f"^{cur_t.major}.{cur_t.minor}.{cur_t.patch}"
                    clean_versions = _discover_available_versions_for_module(self.engine, mod, provider_url)
                    best_v = semver.find_best_version(clean_versions, major_constraint)
                    latest_ver = best_v if best_v else cur_ver

                    if semver.compare_semver(latest_ver, cur_ver) > 0:
                        print(f"[core:update] Updating '{mod}' from {cur_ver} -> {latest_ver}...")
                        self.engine.act_prepare([(mod, latest_ver)], provider_url, force=True)
                        self.engine.act_register(mod, latest_ver, provider_url)
                        migrations_to_run.append((mod, cur_ver, latest_ver))
                        updated_any = True
                    else:
                        print(f"[core:update] Module '{mod}' is already up-to-date (v{cur_ver}).")

                if updated_any:
                    self.engine.act_reload(clean_stage=True, inject_stage=True)
                    for mod, old_v, new_v in migrations_to_run:
                        self.engine.act_migrate(mod, old_v, new_v)
                    events.broadcast("on_update", ExecutionContext("core", "update", targets), emit_module="core")
                    self.sync_pip_dependencies()
                    try:
                        from core.update_checker import UpdateChecker
                        checker = UpdateChecker()
                        for m in targets:
                            checker.invalidate_cache(m)
                    except Exception:
                        pass
                    print("[core:update] Update completed successfully.")
            return 0
        except Exception as e:
            print(f"[core:update] Error during update: {e}")
            self.engine.act_restore_snapshot(snap_id)
            return 1

    def cmd_remove(self, module_name: str, clean: bool = False, purge: bool = False, force: bool = False) -> int:
        if not module_name:
            print("[core:remove] Error: Module name is required.")
            return 1

        _, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})

        if module_name not in installed:
            print(f"[core:remove] Module '{module_name}' is not currently installed.")
            return 1

        if module_name == "core":
            print("[core:remove] Error: Cannot remove 'core' infrastructure module.")
            return 1

        dependents: List[str] = []
        for other_mod in installed.keys():
            if other_mod == module_name:
                continue
            manifest_uri = f"module://{other_mod}/manifest.json"
            if vfs.exists(manifest_uri):
                try:
                    m_data = vfs.read_json(manifest_uri)
                    deps = _parse_dependencies(m_data.get("dependencies", {}))
                    if module_name in deps:
                        dependents.append(other_mod)
                except Exception:
                    pass

        if dependents:
            if not force:
                print(
                    f"[core:remove] Error: Cannot remove '{module_name}' because it is required by: "
                    f"{', '.join(dependents)}. Use --force to override."
                )
                return 1
            print(f"[core:remove] Warning: Force removing '{module_name}' required by: {', '.join(dependents)}.")

        print(f"[core:remove] Removing module '{module_name}'...")
        events.broadcast("on_remove", ExecutionContext("core", "remove", [module_name]), emit_module="core")
        self.engine.act_snapshot(f"pre_remove_{module_name}")
        self.engine.act_unregister(module_name)
        self.engine.act_delete(module_name, clean_mirror=clean, purge=purge)
        self.engine.act_reload(clean_stage=True, inject_stage=True)
        self.sync_pip_dependencies()
        if purge:
            print(f"[core:remove] Module '{module_name}' and all its persistent data/config purged successfully.")
        else:
            print(f"[core:remove] Module '{module_name}' removed successfully (cache cleared, storage/config preserved).")
        return 0

    def cmd_list(self, remote: bool = False, provider: Optional[str] = None) -> int:
        _, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})

        if not remote:
            print("-" * 65)
            print(f"{'Module Name':<20} {'Version':<10} {'Provider':<15} {'Status':<15}")
            print("-" * 65)
            if not installed:
                print("  (No modules installed)")
            else:
                for mod, meta in installed.items():
                    ver = meta.get("version", "unknown")
                    prov = meta.get("provider", "local")
                    status = "Installed" if vfs.exists(f"module://{mod}") else "Missing files"
                    print(f"{mod:<20} {ver:<10} {prov:<15} {status:<15}")
            print("-" * 65)
            return 0

        default_provider = cfg.get("default_provider") or cfg.get("installed_modules", {}).get("core", {}).get("provider")
        provider_url = provider or default_provider
        if not provider_url:
            print("[core:list] Error: No default_provider configured and no --provider specified.")
            return 1

        print("-" * 75)
        print(f"{'Module Name':<20} {'Latest Ver':<12} {'Provider':<25} {'Local Status':<15}")
        print("-" * 75)

        available_modules = _discover_remote_modules(self.engine, provider_url, installed)
        if not available_modules:
            print(f"  (No remote modules found at provider: {provider_url})")
            print("-" * 75)
            return 1

        for mod in sorted(available_modules.keys()):
            latest_ver = available_modules[mod]
            if mod in installed:
                loc_ver = installed[mod].get("version", "unknown")
                loc_status = f"Installed (v{loc_ver})"
            else:
                loc_status = "Available"
            print(f"{mod:<20} {latest_ver:<12} {provider_url:<25} {loc_status:<15}")

        print("-" * 75)
        return 0

    def cmd_status(self) -> int:
        _, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})

        print("=" * 60)
        print("YS-Codebase Core Health Diagnostic Report")
        print("=" * 60)
        print(f"YS-Codebase Root : {cfg.get('yscb_root', 'unknown')}")
        print(f"Total Modules    : {len(installed)}")

        healthy = True
        for mod, meta in installed.items():
            mod_exists = vfs.exists(f"module://{mod}/manifest.json")
            cli_exists = vfs.exists(f"module://{mod}/scripts/cli.py")
            if not mod_exists or not cli_exists:
                healthy = False
                print(f"  [!] {mod}: Incomplete (manifest={mod_exists}, cli={cli_exists})")
            else:
                print(f"  [*] {mod}@{meta.get('version')}: Healthy")

        print("-" * 60)
        print(f"Overall Status   : {'HEALTHY (100% Ready)' if healthy else 'DEGRADED (Run reload)'}")
        print("=" * 60)
        return 0 if healthy else 1

    def cmd_rollback(self, target: Optional[str] = None) -> int:
        if not vfs.exists("snapshot://"):
            print("[core:rollback] No snapshots found.")
            return 1

        snaps = sorted(vfs.listdir("snapshot://"))
        if not snaps:
            print("[core:rollback] No snapshots available.")
            return 1

        target_snap = target or snaps[-1]
        print(f"[core:rollback] Rolling back to snapshot '{target_snap}'...")
        try:
            self.engine.act_restore_snapshot(target_snap)
            print(f"[core:rollback] Successfully restored to '{target_snap}'.")
            return 0
        except Exception as e:
            print(f"[core:rollback] Rollback failed: {e}")
            return 1

    def cmd_reload(self) -> int:
        print("[core:reload] Reconciling runtime modules from mirror...")
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
            print("[core:reload] Runtime environment reconciled and refreshed successfully.")
            return 0

    def cmd_restore(self, force: bool = False, provider: Optional[str] = None) -> int:
        """
        CLI 指令：python yscb.py restore [--force]
        讀取 yscb.config.json 之 installed_modules 清冊，批量還原所有模組至 .modules/，
        並於完成後自動觸發 reload 重聚環境。
        """
        cfg_path, cfg = self.engine._get_config()
        if not cfg_path or not cfg:
            print("[core:restore] Error: Configuration not found.")
            return 1

        host_dir, _ = uri._get_host_config()
        yscb_abs = os.path.normpath(os.path.join(host_dir, cfg.get("yscb_root", ".")))
        generate_internal_gitignore(yscb_abs)

        installed = cfg.get("installed_modules", {})
        if not installed:
            print("[core:restore] No installed_modules declared in configuration. Nothing to restore.")
            return 0

        default_provider = cfg.get(
            "default_provider",
            "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release",
        )
        modules_dir = os.path.join(yscb_abs, ".modules")
        os.makedirs(modules_dir, exist_ok=True)

        print(f"[core:restore] Restoring {len(installed)} module(s) to '{modules_dir}'...")
        success_count = 0
        failed_mods: List[str] = []

        with self.engine.transaction_lock("restore"):
            mod_keys = sorted(installed.keys(), key=lambda x: (0 if x == "core" else 1, x))
            for mod_name in mod_keys:
                mod_info = installed[mod_name]
                ver = mod_info.get("version", "1.0.0.0") if isinstance(mod_info, dict) else "1.0.0.0"
                prov = provider or (mod_info.get("provider", default_provider) if isinstance(mod_info, dict) else default_provider)
                dest = os.path.join(modules_dir, mod_name)
                mirror = os.path.join(yscb_abs, ".mirror", mod_name)

                if not force and os.path.isdir(dest) and os.path.isfile(os.path.join(dest, "manifest.json")):
                    print(f"  -> Skipping '{mod_name}@{ver}' (already installed, use --force to overwrite)")
                    success_count += 1
                    continue

                print(f"  -> Restoring '{mod_name}@{ver}'...")
                ok = self._restore_module_package(host_dir, cfg.get("yscb_root", "."), mod_name, ver, prov, dest, mirror)
                if ok:
                    success_count += 1
                else:
                    _print_restore_failure_guidance(mod_name, ver, prov)
                    failed_mods.append(mod_name)

            if failed_mods:
                print(f"[core:restore] Warning: Completed with {len(failed_mods)} failure(s): {', '.join(failed_mods)}")
            else:
                print(f"[core:restore] Successfully restored all {success_count} module(s).")

            print("[core:restore] Triggering reload...")
            self.engine.act_reload(clean_stage=True, inject_stage=True)
            self.sync_pip_dependencies()
            try:
                generate_internal_gitignore(yscb_abs)
            except Exception:
                pass
            print("[core:reload] Runtime environment reconciled and refreshed successfully.")
            return 0 if not failed_mods else 1

    def _restore_module_package(
        self,
        base_dir: str,
        yscb_root: str,
        module_name: str,
        version: str,
        provider_arg: str,
        dest_dir: str,
        mirror_dir: str,
    ) -> bool:
        """自 Provider、Build 或本機 Mirror 提取指定版本模組，原子解壓縮至 dest_dir。"""
        import zipfile
        import shutil
        os.makedirs(dest_dir, exist_ok=True)
        os.makedirs(mirror_dir, exist_ok=True)

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
        if found_b:
            is_newer = not os.path.isfile(mirror_zip) or (os.path.getmtime(found_b) >= os.path.getmtime(mirror_zip))
            if version.endswith(".build") or is_newer:
                try:
                    fetch_and_extract_zip(found_b, dest_dir)
                    if os.path.isfile(found_b) and (found_b.endswith(".zip") or zipfile.is_zipfile(found_b)):
                        try:
                            shutil.copy2(found_b, mirror_zip)
                        except Exception:
                            pass
                    return True
                except Exception:
                    pass

        # 2. 檢查本地鏡像庫 (.mirror/<mod>/<ver>.zip)
        if os.path.isfile(mirror_zip):
            try:
                fetch_and_extract_zip(mirror_zip, dest_dir)
                return True
            except Exception:
                pass

        # 3. 檢查 Provider 路徑 (local folder)
        if provider_arg.startswith("file://"):
            import urllib.request
            raw_p = urllib.request.url2pathname(provider_arg[7:])
            while raw_p.startswith("//"):
                raw_p = raw_p[1:]
            p_abs = os.path.normpath(raw_p)
        elif not provider_arg.startswith(("http://", "https://")):
            p_abs = os.path.normpath(os.path.join(base_dir, provider_arg))
        else:
            p_abs = None

        if p_abs and os.path.isdir(p_abs):
            candidates = [
                os.path.join(p_abs, module_name, f"{version}.zip"),
                os.path.join(p_abs, module_name, f"{version}"),
                os.path.join(p_abs, module_name),
                os.path.join(p_abs, "release", module_name, f"{version}.zip"),
                os.path.join(p_abs, ".build", module_name, f"{version}.zip"),
            ]
            found = next((c for c in candidates if os.path.exists(c)), None)
            if found:
                try:
                    fetch_and_extract_zip(found, dest_dir)
                    if os.path.isfile(found) and (found.endswith(".zip") or zipfile.is_zipfile(found)):
                        try:
                            shutil.copy2(found, mirror_zip)
                        except Exception:
                            pass
                    return True
                except Exception:
                    pass

        # 4. 遠端 Provider (HTTP/HTTPS)
        if provider_arg.startswith(("http://", "https://", "file://")):
            remote_zip_url = provider_arg.rstrip("/") + f"/{module_name}/{version}.zip"
            try:
                fetch_and_extract_zip(remote_zip_url, dest_dir)
                return True
            except Exception:
                pass

        return False

    def sync_pip_dependencies(self) -> None:
        """
        收集所有已安裝模組之 pip_dependencies 宣告聯集，
        透過 PipManager 於微環境執行 Wheel-Only 靜默物化；
        隨後若 project://.vscode 存在，調用 IdeProjector 執行明確標記 _yscb_managed 之可復原軟合併。
        """
        from core.pip_manager import PipManager, PipInstallError
        from core.ide_projector import IdeProjector

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
                print(f"[core:pip] Warning: {e}")

        try:
            proj_root = uri.resolve("project://", interactive=False)
            if proj_root and os.path.isdir(proj_root):
                ide_proj = IdeProjector(yscb_abs)
                if ide_proj.is_vscode_configured(proj_root):
                    ide_proj.sync_vscode_settings(proj_root)
        except Exception:
            pass

