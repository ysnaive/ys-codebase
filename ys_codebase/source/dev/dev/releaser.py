"""
Releaser & Release Toolchain Implementation for YS-Codebase modules.
Implements:
- 3-Gate Release Verification (Manifest Compliance, Immutability, Monotonicity)
- Pure Packaging Dispatcher (via Builder.package_release)
- DAG Dependency Topological Sort for Batch Release (release --all)
- release-git 4-Step Pipeline (test -> release-check -> release -> local git commit & tag)
- Strict Local-Only Git Safety (No remote push)
"""
import os
import re
import functools
import subprocess
from typing import Optional, Tuple, Dict, Any, List, Set

from core import uri, vfs, semver, events
from core.context import ExecutionContext
from dev.builder import Builder, compare_semver_safe
from dev.checker import Checker, discover_source_modules


class CyclicDependencyError(RuntimeError):
    """Raised when cyclic dependencies are detected during topological sorting."""
    pass


def resolve_module_dependency_order(
    available_modules: Set[str],
    dep_map: Dict[str, List[str]],
) -> List[str]:
    """
    Execute Kahn's algorithm with alphabetical stability over available_modules.
    Raises CyclicDependencyError if a cycle is detected.
    """
    in_degree: Dict[str, int] = {m: 0 for m in available_modules}
    adj_list: Dict[str, List[str]] = {m: [] for m in available_modules}

    for m in available_modules:
        for dep in dict.fromkeys(dep_map.get(m, [])):
            if dep in available_modules:
                adj_list[dep].append(m)
                in_degree[m] += 1

    queue = sorted([m for m, deg in in_degree.items() if deg == 0])
    topo_order: List[str] = []

    while queue:
        curr = queue.pop(0)
        topo_order.append(curr)
        for neighbor in sorted(adj_list[curr]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
                queue.sort()

    if len(topo_order) != len(available_modules):
        cyclic_mods = sorted([m for m, deg in in_degree.items() if deg > 0])
        raise CyclicDependencyError(f"Cyclic dependency detected among modules: {cyclic_mods}")

    return topo_order


def _extract_manifest_dependencies(mdata: Dict[str, Any]) -> List[str]:
    raw_deps = mdata.get("dependencies", {})
    if isinstance(raw_deps, dict):
        return list(raw_deps.keys())
    if isinstance(raw_deps, list):
        return list(raw_deps)
    return []


class Releaser:
    """純淨發布調度器：負責發布前 3-Gate 校驗、DAG 拓撲排序批次發布與 release-git 本地流水線。"""

    def __init__(
        self,
        builder: Optional[Builder] = None,
        checker: Optional[Checker] = None,
        tester: Optional[Any] = None,
    ) -> None:
        self.builder = builder or Builder()
        self.checker = checker or Checker()
        self.tester = tester

    def _run_git_cmd(self, args: List[str], cwd: Optional[str] = None, timeout: float = 30.0) -> Tuple[int, str, str]:
        """Runs a Git command safely within local repository."""
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=cwd or uri.resolve("yscb://"),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            return res.returncode, (res.stdout or "").strip(), (res.stderr or "").strip()
        except Exception as e:
            return -1, "", str(e)

    @staticmethod
    def sync_package_dunder_version(mod_name: str, old_ver: str, new_ver: str) -> None:
        """若模組套件目錄之 __init__.py 宣告有 __version__ 字面量，自動同步更新為新版本。"""
        src_dir = uri.resolve(f"module.source://{mod_name}")
        if not src_dir or not os.path.isdir(src_dir):
            return
        for entry in sorted(os.listdir(src_dir)):
            if entry in ("tests", "scripts", "contributes", "configurable", "assets", "skills") or entry.startswith("."):
                continue
            init_uri = f"module.source://{mod_name}/{entry}/__init__.py"
            if not vfs.is_file(init_uri):
                continue
            content = vfs.read_text(init_uri)
            updated = re.sub(
                r'^(__version__\s*(?::\s*str\s*)?=\s*[\'"])' + re.escape(old_ver) + r'([\'"])',
                rf"\g<1>{new_ver}\g<2>",
                content,
                flags=re.MULTILINE,
            )
            if updated != content:
                vfs.write_text(init_uri, updated, atomic=True)

    def bump_module_version(self, mod_name: str, bump_type: str) -> Tuple[bool, str]:
        """Atomically bumps module version in source/<mod>/manifest.json and syncs package __version__."""
        src_manifest_uri = f"module.source://{mod_name}/manifest.json"
        if not vfs.exists(src_manifest_uri):
            return False, f"Source module '{mod_name}' not found at {src_manifest_uri}."
        try:
            manifest_data = vfs.read_json(src_manifest_uri)
            curr_ver = manifest_data.get("version", "1.0.0.0")
            next_ver = semver.bump_version(curr_ver, bump_type)
            manifest_data["version"] = next_ver
            vfs.write_json(src_manifest_uri, manifest_data, indent=2, atomic=True)
            self.sync_package_dunder_version(mod_name, curr_ver, next_ver)
            return True, f"Successfully bumped '{mod_name}': {curr_ver} -> {next_ver} ({bump_type})."
        except Exception as e:
            return False, f"Error bumping version for '{mod_name}': {e}"

    def _collect_all_known_released_versions(self, module_name: str) -> Set[str]:
        """Collects all known released versions from index.json ('versions' and 'releases' ledger) and physical .zip files."""
        known: Set[str] = set()
        mod_rel_root = f"module.release://{module_name}"
        if not vfs.exists(mod_rel_root):
            return known

        index_uri = f"{mod_rel_root}/index.json"
        if vfs.exists(index_uri):
            try:
                idx_data = vfs.read_json(index_uri)
                if isinstance(idx_data, dict):
                    if isinstance(idx_data.get("versions"), list):
                        for v in idx_data["versions"]:
                            if isinstance(v, str) and v.strip():
                                known.add(v.strip())
                    if isinstance(idx_data.get("releases"), dict):
                        for v in idx_data["releases"].keys():
                            if isinstance(v, str) and v.strip():
                                known.add(v.strip())
            except Exception:
                pass

        real_rel_dir = uri.resolve(mod_rel_root)
        if os.path.isdir(real_rel_dir):
            for item in os.listdir(real_rel_dir):
                if item.endswith(".zip"):
                    known.add(item[:-4])
        return known

    def release_check(self, module_name: str, force: bool = False) -> Tuple[bool, List[str]]:
        """
        獨立發布就緒預檢門面 (dev release-check <mod> [--force]):
        - Gate 1: Checker.check_module(module_name) 靜態合規性。
        - Gate 2: 版本不可變性（release/<mod>/<target_ver>.zip 不得已存在；force=True 時放行）。
        - Gate 3: 版本單調遞增（target_ver 必須嚴格大於全倉庫最高已發布版本 global_highest；force=True 且 target == global_highest 時放行同版本覆蓋，但小於歷史最高版本仍阻斷）。
        """
        errors: List[str] = []
        src_uri = f"module.source://{module_name}"
        if not vfs.exists(src_uri):
            errors.append(f"Source module '{module_name}' not found at {src_uri}.")
            return False, errors

        manifest_uri = f"{src_uri}/manifest.json"
        if not vfs.exists(manifest_uri):
            errors.append(f"manifest.json not found for module '{module_name}'.")
            return False, errors

        # Gate 1: Manifest compliance check
        report = self.checker.check_module(module_name)
        if not report.passed:
            errors.append("Gate 1 Failed (Manifest Compliance):\n  - " + "\n  - ".join(report.errors))

        try:
            manifest_data = vfs.read_json(manifest_uri)
            target_version = manifest_data.get("version", "")
            target_tuple = semver.parse_semver(target_version)
        except Exception as e:
            errors.append(f"Invalid version string in manifest.json: {e}")
            return False, errors

        # Gate 2: Immutability / Version Conflict
        known_versions = self._collect_all_known_released_versions(module_name)
        exact_rel_zip = f"module.release://{module_name}/{target_version}.zip"
        if (vfs.exists(exact_rel_zip) or target_version in known_versions) and not force:
            errors.append(
                f"Gate 2 Failed (Immutability): Version '{target_version}' already exists in release repository "
                f"({exact_rel_zip}). Duplicate release forbidden (use --force to override)."
            )

        # Gate 3: Monotonicity / No Rollback
        all_existing_versions: List[semver.VersionTuple] = []
        for item_ver in known_versions:
            try:
                all_existing_versions.append(semver.parse_semver(item_ver))
            except ValueError:
                pass

        if all_existing_versions:
            all_existing_versions.sort(key=functools.cmp_to_key(semver.compare_semver))
            global_highest = all_existing_versions[-1]
            cmp_res = semver.compare_semver(target_tuple, global_highest)

            if not force:
                if cmp_res <= 0:
                    errors.append(
                        f"Gate 3 Failed (Monotonicity): Target version '{target_version}' must be strictly greater than "
                        f"the highest existing version '{global_highest}' in release repository."
                    )
            else:
                if cmp_res < 0:
                    errors.append(
                        f"Gate 3 Failed (Monotonicity): Target version '{target_version}' is less than "
                        f"the highest existing version '{global_highest}'. Version rollback is forbidden even with --force."
                    )

        return len(errors) == 0, errors

    def _apply_release_meta_to_source_manifest(
        self,
        module_name: str,
        release_meta: Optional[Dict[str, str]],
    ) -> Tuple[bool, str]:
        """Writes or merges release metadata (type, urgency, summary) into module.source://<mod>/manifest.json['release']."""
        if not release_meta:
            return True, ""
        cleaned = {
            k: str(v).strip()
            for k, v in release_meta.items()
            if k in ("type", "urgency", "summary") and v is not None and str(v).strip()
        }
        if not cleaned:
            return True, ""
        mf_uri = f"module.source://{module_name}/manifest.json"
        if not vfs.exists(mf_uri):
            return False, f"manifest.json not found for module '{module_name}'."
        try:
            mf_data = vfs.read_json(mf_uri)
            if not isinstance(mf_data, dict):
                return False, f"Invalid manifest.json format for '{module_name}'."
            cur_rel = mf_data.get("release") if isinstance(mf_data.get("release"), dict) else {}
            merged_rel = dict(cur_rel)
            merged_rel.update(cleaned)
            mf_data["release"] = merged_rel
            vfs.write_json(mf_uri, mf_data, indent=2, atomic=True)
            return True, ""
        except Exception as e:
            return False, f"Failed to write release metadata into manifest.json for '{module_name}': {e}"

    @staticmethod
    def _snapshot_manifest_text(manifest_uri: str) -> Optional[str]:
        if not vfs.is_file(manifest_uri):
            return None
        try:
            return vfs.read_text(manifest_uri)
        except Exception:
            return None

    @staticmethod
    def _restore_manifest_text(manifest_uri: str, orig_text: Optional[str]) -> None:
        if orig_text is None:
            return
        try:
            vfs.write_text(manifest_uri, orig_text, encoding="utf-8", atomic=True)
        except Exception:
            pass

    def release_module(
        self,
        module_name: str,
        force: bool = False,
        _skip_check: bool = False,
        release_meta: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str]:
        """
        單一模組純淨發布 (dev release <mod> [--force]):
        1. 若 _skip_check=False，先執行 pre-flight release_check(module_name, force=force)（避免預檢失敗時污染 manifest.json）。
        2. 若傳入 release_meta，寫入 source/<mod>/manifest.json["release"]，若後續失敗或拋出例外則於 finally 強制原子回滾。
        3. 調用 Builder.package_release(module_name, target_version)。
        4. 廣播標準事件 on_module_released。
        """
        manifest_uri = f"module.source://{module_name}/manifest.json"
        orig_manifest_text = self._snapshot_manifest_text(manifest_uri) if release_meta else None
        manifest_mutated = False
        committed = False

        try:
            if not _skip_check:
                passed, errors = self.release_check(module_name, force=force)
                if not passed:
                    err_msg = "\n  - ".join(errors)
                    return False, f"Release pre-flight check failed for '{module_name}':\n  - {err_msg}"

            if release_meta:
                ok_meta, err_meta = self._apply_release_meta_to_source_manifest(module_name, release_meta)
                if not ok_meta:
                    return False, err_meta
                manifest_mutated = True
                if not _skip_check:
                    passed_post, errors_post = self.release_check(module_name, force=force)
                    if not passed_post:
                        err_msg = "\n  - ".join(errors_post)
                        return False, f"Release pre-flight check failed for '{module_name}':\n  - {err_msg}"

            if not vfs.exists(manifest_uri):
                return False, f"manifest.json not found for module '{module_name}'."
            try:
                manifest_data = vfs.read_json(manifest_uri)
                if not isinstance(manifest_data, dict):
                    return False, f"Invalid manifest.json format for module '{module_name}'."
            except Exception as e:
                return False, f"Invalid JSON in manifest.json for module '{module_name}': {e}"
            target_version = manifest_data.get("version", "1.0.0.0")

            ok, msg = self.builder.package_release(module_name, target_version)
            if not ok:
                return ok, msg

            rel_zip_uri = f"module.release://{module_name}/{target_version}.zip"
            zip_real = uri.resolve(rel_zip_uri) if vfs.exists(rel_zip_uri) else ""
            ctx = ExecutionContext(
                "dev",
                "on_module_released",
                [module_name, target_version],
                metadata={
                    "module": module_name,
                    "version": target_version,
                    "zip_path": zip_real,
                },
            )
            events.broadcast("on_module_released", context=ctx, emit_module="dev")
            committed = True
            return ok, msg
        finally:
            if manifest_mutated and not committed:
                self._restore_manifest_text(manifest_uri, orig_manifest_text)

    def release_all(self, force: bool = False) -> Dict[str, Tuple[bool, str]]:
        """
        全量模組依賴拓撲批次發布 (dev release --all [--force]):
        1. 讀取 source/ 下所有模組 manifest.json 中的 dependencies。
        2. 建構 DAG 並使用 Kahn 演算法按字母序穩定計算拓撲發布序列。
        3. 依序調用 release_module(mod_name, force=force)；若上游失敗則下游自動標記跳過。
        """
        results: Dict[str, Tuple[bool, str]] = {}
        available_modules: Set[str] = set(discover_source_modules())
        if not available_modules:
            return results

        dep_map: Dict[str, List[str]] = {}
        for m in available_modules:
            try:
                mdata = vfs.read_json(f"module.source://{m}/manifest.json")
                dep_map[m] = _extract_manifest_dependencies(mdata) if isinstance(mdata, dict) else []
            except Exception:
                dep_map[m] = []

        topo_order = resolve_module_dependency_order(available_modules, dep_map)

        failed_modules: Set[str] = set()
        for mod_name in topo_order:
            failed_deps = [d for d in dep_map.get(mod_name, []) if d in failed_modules]
            if failed_deps:
                failed_modules.add(mod_name)
                results[mod_name] = (False, f"Skipped because dependency '{failed_deps[0]}' failed release.")
                continue

            ok, msg = self.release_module(mod_name, force=force)
            results[mod_name] = (ok, msg)
            if not ok:
                failed_modules.add(mod_name)

        return results

    def _resolve_module_git_stage_paths(self, module_name: str) -> List[str]:
        """Resolves module-scoped paths (`source/<mod>`, `release/<mod>`) for targeted `git add`."""
        stage_paths: List[str] = []
        try:
            yscb_root = uri.resolve("yscb://")
        except Exception:
            yscb_root = ""
        for rel_cand in (f"source/{module_name}", f"release/{module_name}"):
            if yscb_root and os.path.exists(os.path.join(yscb_root, rel_cand)):
                stage_paths.append(rel_cand)
        if not stage_paths:
            stage_paths.append(f"source/{module_name}")
        return stage_paths

    def release_git(
        self,
        module_name: str,
        commit_msg: str,
        force: bool = False,
        release_meta: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str]:
        """
        4 步發布與版本控制安全流水線 (dev release-git <mod> "<msg>" [--force]):
        1. 先調用 Tester 執行 dev test <mod>（測試未通過前絕不修改磁碟 manifest.json）。
        2. 檢查目標版本是否已發布：
           - 若尚未發布或傳入 --force：套用 release_meta（若傳入），執行 release_check -> release_module(_skip_check=True)。
           - 若已發布且無 --force：略過打包與 manifest 改寫，直接推進至本地 Git 提交。
        3. 本地 Git 提交：僅針對目標模組之 source/<mod> 與 release/<mod> 執行 git add -> git commit -m commit_msg -> git tag [-f] -a "<mod>/v<ver>" -m commit_msg。
        4. 任何階段失敗或拋出例外時，透過 try...finally 100% 還原 manifest.json 原始文本。
        """
        if not commit_msg or not commit_msg.strip():
            return False, "Commit message cannot be empty for release-git."

        src_uri = f"module.source://{module_name}"
        manifest_uri = f"{src_uri}/manifest.json"
        if not vfs.exists(manifest_uri):
            return False, f"manifest.json not found for module '{module_name}'."

        try:
            manifest_data = vfs.read_json(manifest_uri)
            if not isinstance(manifest_data, dict):
                return False, f"Invalid manifest.json format for module '{module_name}'."
        except Exception as e:
            return False, f"Invalid JSON in manifest.json for module '{module_name}': {e}"

        ver = manifest_data.get("version", "1.0.0.0")
        exact_rel_zip = f"module.release://{module_name}/{ver}.zip"
        known_versions = self._collect_all_known_released_versions(module_name)
        is_already_released = vfs.exists(exact_rel_zip) or (ver in known_versions)

        orig_manifest_text = self._snapshot_manifest_text(manifest_uri) if release_meta else None
        manifest_mutated = False
        committed = False

        try:
            # Step 1: E2E Test BEFORE mutating manifest.json on disk
            tester = self.tester
            if tester is None:
                from dev.tester import Tester
                tester = Tester()
            test_ret = tester.run(["test", module_name])
            if test_ret != 0:
                return False, f"Step 1 Failed: E2E test failed for module '{module_name}'. Release aborted."

            # Step 2 & 3: Release Check and Packaging (Smart Skip or Force Overwrite)
            if is_already_released and not force:
                from core.log import log
                log(f"[dev:release-git] Target version '{module_name}@{ver}' is already released ({exact_rel_zip}). Skipping packaging step.")
            else:
                if release_meta:
                    ok_meta, err_meta = self._apply_release_meta_to_source_manifest(module_name, release_meta)
                    if not ok_meta:
                        return False, err_meta
                    manifest_mutated = True

                passed, chk_errors = self.release_check(module_name, force=force)
                if not passed:
                    err_details = "\n  - ".join(chk_errors)
                    return False, f"Step 2 Failed: Release readiness check failed for '{module_name}':\n  - {err_details}"

                ok_pkg, msg_pkg = self.release_module(module_name, force=force, _skip_check=True)
                if not ok_pkg:
                    return False, f"Step 3 Failed: Release packaging failed for '{module_name}': {msg_pkg}"

            # Step 4: Local Git Commit and Tag
            tag_name = f"{module_name}/v{ver}"

            git_check, _, _ = self._run_git_cmd(["rev-parse", "--is-inside-work-tree"])
            if git_check != 0:
                committed = True
                return True, f"Successfully packaged release '{module_name}@{ver}'. (Warning: Not a Git repository, skipped commit & tag)"

            stage_paths = self._resolve_module_git_stage_paths(module_name)
            c_code, _, c_err = self._run_git_cmd(["add", "--", *stage_paths])
            if c_code != 0:
                return False, f"Git add failed during release-git: {c_err}"

            c_code, c_out, c_err = self._run_git_cmd(["commit", "-m", commit_msg])
            if c_code != 0:
                combined_err = f"{c_out}\n{c_err}".lower()
                if "nothing to commit" not in combined_err and "working tree clean" not in combined_err:
                    return False, f"Git commit failed during release-git: {c_err or c_out}"

            tag_cmd = ["tag", "-f", "-a", tag_name, "-m", commit_msg] if force else ["tag", "-a", tag_name, "-m", commit_msg]
            t_code, _, t_err = self._run_git_cmd(tag_cmd)
            if t_code != 0:
                return False, f"Git tag failed for '{tag_name}': {t_err}"

            committed = True
            return True, f"Successfully processed '{module_name}@{ver}' and updated local Git commit & tag '{tag_name}'."
        finally:
            if manifest_mutated and not committed:
                self._restore_manifest_text(manifest_uri, orig_manifest_text)

    def patch_release_index(
        self,
        module_name: str,
        version: str,
        dependencies: Optional[Dict[str, str]] = None,
        status: Optional[str] = None,
        release_type: Optional[str] = None,
        urgency: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Lightweight post-release metadata and dependency patcher (dev index-patch).
        Directly updates module.release://<module_name>/index.json['releases'][<version>]
        and synchronizes top-level 'versions' list when status changes between 'active' and 'pruned'.
        """
        if not module_name or not str(module_name).strip():
            return False, "Module name cannot be empty."
        clean_ver = str(version or "").strip()
        if not clean_ver:
            return False, "Target version (--ver) is required."
        try:
            semver.parse_semver(clean_ver)
        except Exception as e:
            return False, f"Invalid SemVer version '{clean_ver}': {e}"

        if status is not None and status not in ("active", "pruned"):
            return False, f"Invalid status '{status}': must be 'active' or 'pruned'."

        index_uri = f"module.release://{module_name}/index.json"
        if not vfs.is_file(index_uri):
            return False, f"Release index not found at {index_uri}."

        try:
            idx_data = vfs.read_json(index_uri)
            if not isinstance(idx_data, dict):
                return False, f"Invalid JSON object in {index_uri}."
        except Exception as e:
            return False, f"Failed to read {index_uri}: {e}"

        active_versions = [v for v in idx_data.get("versions", []) if isinstance(v, str)]
        releases_map = idx_data.get("releases") if isinstance(idx_data.get("releases"), dict) else {}
        releases_map = {str(k): dict(v) if isinstance(v, dict) else {} for k, v in releases_map.items()}

        entry = dict(releases_map.get(clean_ver, {}))
        if "status" not in entry:
            entry["status"] = "active" if clean_ver in active_versions else "pruned"
        if "dependencies" not in entry or not isinstance(entry.get("dependencies"), dict):
            entry["dependencies"] = {}

        if status is not None:
            entry["status"] = status
            if status == "active" and clean_ver not in active_versions:
                active_versions.append(clean_ver)
            elif status == "pruned" and clean_ver in active_versions:
                active_versions = [v for v in active_versions if v != clean_ver]
        elif clean_ver not in releases_map and clean_ver not in active_versions:
            active_versions.append(clean_ver)
            entry["status"] = "active"

        if isinstance(dependencies, dict) and dependencies:
            cur_deps = dict(entry.get("dependencies", {}))
            for dk, dv in dependencies.items():
                cur_deps[str(dk).strip()] = str(dv).strip()
            entry["dependencies"] = cur_deps

        if release_type is not None and str(release_type).strip():
            entry["type"] = str(release_type).strip()
        if urgency is not None and str(urgency).strip():
            entry["urgency"] = str(urgency).strip()
        if summary is not None and str(summary).strip():
            entry["summary"] = str(summary).strip()

        releases_map[clean_ver] = entry

        active_versions = sorted(set(active_versions), key=functools.cmp_to_key(compare_semver_safe))
        sorted_rel_keys = sorted(releases_map.keys(), key=functools.cmp_to_key(compare_semver_safe))
        idx_data["versions"] = active_versions
        idx_data["releases"] = {k: releases_map[k] for k in sorted_rel_keys}

        try:
            vfs.write_json(index_uri, idx_data, indent=2, atomic=True)
        except Exception as e:
            return False, f"Failed to write {index_uri}: {e}"

        return True, f"Successfully patched release index for '{module_name}@{clean_ver}' ({index_uri})."
