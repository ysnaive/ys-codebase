"""
Core Package Management Installer Subcommands (install, update, remove, list, status, rollback, reload).
Includes Major Boundary Lock & Incremental Migration Trigger.
"""
import os
import sys
import json
from typing import Optional, List, Dict, Tuple, Any
from core import uri
from core.context import ExecutionContext
from core.engine import AtomicEngine
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
    ]
    block_lines.extend(INTERNAL_IGNORE_PATTERNS)
    block_lines.append(INTERNAL_IGNORE_END)
    new_block_text = "\n".join(block_lines)

    existing_content = ""
    has_existing = os.path.isfile(gi_path)
    if has_existing:
        try:
            with open(gi_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
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
        with open(gi_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(merged_content)
    except Exception:
        pass


def fetch_and_extract_zip(source_url_or_path: str, dest_dir: str) -> None:
    """從本機路徑或遠端 URL 提取 Zip 壓縮檔至 dest_dir，嚴防 Zip Slip。"""
    import urllib.request
    import tempfile
    import shutil
    import zipfile

    os.makedirs(dest_dir, exist_ok=True)

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
            with zipfile.ZipFile(tmp_path, "r") as zf:
                if zf.testzip() is not None:
                    raise RuntimeError(f"Corrupted zip archive from '{source_url_or_path}'.")
                dest_dir_abs = os.path.abspath(dest_dir)
                for member in zf.infolist():
                    target_path = os.path.abspath(os.path.join(dest_dir_abs, member.filename))
                    if not target_path.startswith(dest_dir_abs + os.sep) and target_path != dest_dir_abs:
                        raise RuntimeError(f"Zip Slip vulnerability detected: '{member.filename}'")
                zf.extractall(dest_dir)
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
            shutil.copytree(file_path, dest_dir, dirs_exist_ok=True)
        elif zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, "r") as zf:
                if zf.testzip() is not None:
                    raise RuntimeError(f"Corrupted zip archive from '{source_url_or_path}'.")
                dest_dir_abs = os.path.abspath(dest_dir)
                for member in zf.infolist():
                    target_path = os.path.abspath(os.path.join(dest_dir_abs, member.filename))
                    if not target_path.startswith(dest_dir_abs + os.sep) and target_path != dest_dir_abs:
                        raise RuntimeError(f"Zip Slip vulnerability detected: '{member.filename}'")
                zf.extractall(dest_dir)
        else:
            raise RuntimeError(f"Source path '{source_url_or_path}' is neither a directory nor a valid zip file.")


class Installer:
    def __init__(self):
        self.engine = AtomicEngine()

    def _check_optional_dependencies(self, module_name: str) -> None:
        """
        走訪已安裝模組之 manifest.json 中宣告的 optional 擴充模組。
        若工作區尚未安裝該模組，於終端輸出結構化建議卡片與安裝指令引導。
        """
        try:
            manifest_uri = f"module://{module_name}/manifest.json"
            if not uri.exists(manifest_uri):
                return
            m_data = uri.read_json(manifest_uri)
            if not isinstance(m_data, dict):
                return
            optional_deps = m_data.get("optional", {})
            if not isinstance(optional_deps, dict) or not optional_deps:
                return

            cfg_path, cfg = self.engine._get_config()
            installed = cfg.get("installed_modules", {})

            missing_optionals: List[Tuple[str, str, str]] = []
            for opt_mod, opt_info in optional_deps.items():
                if opt_mod in installed and uri.exists(f"module://{opt_mod}"):
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

    def cmd_install(self, module_name: str, version: Optional[str] = None, provider: Optional[str] = None, force: bool = False) -> int:
        if not module_name:
            print("[core:install] Error: Module name is required.")
            return 1
        
        cfg_path, cfg = self.engine._get_config()
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
            self.engine.act_lock("install")
            targets = self.engine.act_solve_deps(module_name, ver_constraint, provider_url)
            self.engine.act_prepare(targets, provider_url, force=force)
            installed_ver = "1.0.0.0"
            for mod, ver in targets:
                self.engine.act_register(mod, ver, provider_url)
                if mod == module_name:
                    installed_ver = ver
            self.engine.act_reload(clean_stage=True, inject_stage=True)
            
            # Execute migration if upgrading
            if old_ver != "0.0.0.0" and semver.compare_semver(installed_ver, old_ver) > 0:
                print(f"[core:install] Running migration ladder for '{module_name}' ({old_ver} -> {installed_ver})...")
                self.engine.act_migrate(module_name, old_ver, installed_ver)
                
            events.broadcast("on_installed", ExecutionContext("core", "install", [module_name, installed_ver]), emit_module="core")
            self.sync_pip_dependencies()
            self.engine.act_unlock("install")
            print(f"[core:install] Successfully installed '{module_name}@{installed_ver}'.")
            self._check_optional_dependencies(module_name)
            return 0
        except Exception as e:
            self.engine.act_unlock("install")
            print(f"[core:install] Error during install: {e}")
            self.engine.act_restore_snapshot(snap_id)
            return 1

    def cmd_update(self, module_name: Optional[str] = None, provider: Optional[str] = None) -> int:
        cfg_path, cfg = self.engine._get_config()
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
        try:
            self.engine.act_lock("update")
            for mod in targets:
                cur_ver = installed.get(mod, {}).get("version", "1.0.0.0")
                cur_t = semver.parse_semver(cur_ver)
                # Major Boundary Lock: constrain update within same major (e.g. ^1.0.0.0)
                major_constraint = f"^{cur_t.major}.{cur_t.minor}.{cur_t.patch}"
                latest_ver = cur_ver
                
                # Check available versions in release/ & provider
                candidate_dirs = [
                    os.path.join(provider_url, "release", mod),
                    os.path.join(provider_url, mod),
                    os.path.join(provider_url, "build", mod)
                ]
                
                found_versions: List[str] = []
                for c_dir in candidate_dirs:
                    if os.path.isdir(c_dir):
                        found_versions.extend([v for v in os.listdir(c_dir) if os.path.isdir(os.path.join(c_dir, v))])
                
                if not found_versions:
                    # Remote lookup
                    ok, res = self.engine.act_fetch(provider_url, f"{mod}/index.json")
                    if ok and isinstance(res, dict) and "versions" in res:
                        found_versions = res["versions"]
                        
                best_v = semver.find_best_version(found_versions, major_constraint)
                if best_v:
                    latest_ver = best_v

                if semver.compare_semver(latest_ver, cur_ver) > 0:
                    print(f"[core:update] Updating '{mod}' from {cur_ver} -> {latest_ver}...")
                    self.engine.act_prepare([(mod, latest_ver)], provider_url, force=True)
                    self.engine.act_register(mod, latest_ver, provider_url)
                    # Run migration ladder
                    self.engine.act_migrate(mod, cur_ver, latest_ver)
                    updated_any = True
                else:
                    print(f"[core:update] Module '{mod}' is already up-to-date (v{cur_ver}).")
            
            if updated_any:
                self.engine.act_reload(clean_stage=True, inject_stage=True)
                events.broadcast("on_update", ExecutionContext("core", "update", targets), emit_module="core")
                self.sync_pip_dependencies()
                print(f"[core:update] Update completed successfully.")
            self.engine.act_unlock("update")
            return 0
        except Exception as e:
            self.engine.act_unlock("update")
            print(f"[core:update] Error during update: {e}")
            self.engine.act_restore_snapshot(snap_id)
            return 1

    def cmd_remove(self, module_name: str, clean: bool = False, purge: bool = False, force: bool = False) -> int:
        if not module_name:
            print("[core:remove] Error: Module name is required.")
            return 1
            
        cfg_path, cfg = self.engine._get_config()
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
            if uri.exists(manifest_uri):
                try:
                    m_data = uri.read_json(manifest_uri)
                    deps = self.engine._parse_dependencies(m_data.get("dependencies", {}))
                    if module_name in deps:
                        dependents.append(other_mod)
                except Exception:
                    pass
                    
        if dependents:
            if not force:
                print(f"[core:remove] Error: Cannot remove '{module_name}' because it is required by: {', '.join(dependents)}. Use --force to override.")
                return 1
            else:
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
        cfg_path, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})
        
        print("-" * 65)
        print(f"{'Module Name':<20} {'Version':<10} {'Provider':<15} {'Status':<15}")
        print("-" * 65)
        
        if not installed:
            print("  (No modules installed)")
        else:
            for mod, meta in installed.items():
                ver = meta.get("version", "unknown")
                prov = meta.get("provider", "local")
                status = "Installed" if uri.exists(f"module://{mod}") else "Missing files"
                print(f"{mod:<20} {ver:<10} {prov:<15} {status:<15}")
        print("-" * 65)
        return 0

    def cmd_status(self) -> int:
        cfg_path, cfg = self.engine._get_config()
        installed = cfg.get("installed_modules", {})
        
        print("=" * 60)
        print("YS-Codebase Core Health Diagnostic Report")
        print("=" * 60)
        print(f"YS-Codebase Root : {cfg.get('yscb_root', 'unknown')}")
        print(f"Total Modules    : {len(installed)}")
        
        healthy = True
        for mod, meta in installed.items():
            mod_exists = uri.exists(f"module://{mod}/manifest.json")
            cli_exists = uri.exists(f"module://{mod}/scripts/cli.py")
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
        if not uri.exists("snapshot://"):
            print("[core:rollback] No snapshots found.")
            return 1
            
        snaps = sorted(uri.listdir("snapshot://"))
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
        self.engine.act_reload(clean_stage=True, inject_stage=True)
        self.sync_pip_dependencies()
        try:
            cfg_path, cfg = self.engine._get_config()
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

        default_provider = cfg.get("default_provider", "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release")
        modules_dir = os.path.join(yscb_abs, ".modules")
        os.makedirs(modules_dir, exist_ok=True)

        print(f"[core:restore] Restoring {len(installed)} module(s) to '{modules_dir}'...")
        success_count = 0
        failed_mods = []

        # 確保 core 優先還原，隨後依字母排序
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
                print(f"[core:restore] Error: Unable to restore module '{mod_name}@{ver}' from provider '{prov}'.")
                failed_mods.append(mod_name)

        if failed_mods:
            print(f"[core:restore] Warning: Completed with {len(failed_mods)} failure(s): {', '.join(failed_mods)}")
        else:
            print(f"[core:restore] Successfully restored all {success_count} module(s).")

        # 觸發 reload
        print("[core:restore] Triggering reload...")
        self.cmd_reload()
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
            os.path.join(yscb_abs, ".build", module_name),
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
            cfg_path, cfg = self.engine._get_config()
        except Exception:
            return

        installed = cfg.get("installed_modules", {})
        raw_specs: List[str] = []
        for mod in installed.keys():
            manifest_uri = f"module://{mod}/manifest.json"
            if uri.exists(manifest_uri):
                try:
                    m_data = uri.read_json(manifest_uri)
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

        # IDE 自動感知可復原軟合併投影 (若 project://.vscode 存在)
        try:
            proj_root = uri.resolve("project://", interactive=False)
            if proj_root and os.path.isdir(proj_root):
                ide_proj = IdeProjector(yscb_abs)
                if ide_proj.is_vscode_configured(proj_root):
                    ide_proj.sync_vscode_settings(proj_root)
        except Exception:
            pass
