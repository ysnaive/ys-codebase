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
import functools
import subprocess
from typing import Optional, Tuple, Dict, Any, List, Set

from core import uri, vfs, semver
from dev.builder import Builder
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
        for dep in dep_map.get(m, []):
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

    def _run_git_cmd(self, args: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
        """Runs a Git command safely within local repository."""
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=cwd or uri.resolve("yscb://"),
                capture_output=True,
                text=True,
                check=False,
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except Exception as e:
            return -1, "", str(e)

    def release_check(self, module_name: str, force: bool = False) -> Tuple[bool, List[str]]:
        """
        獨立發布就緒預檢門面 (dev release-check <mod> [--force]):
        - Gate 1: Checker.check_module(module_name) 靜態合規性。
        - Gate 2: 版本不可變性（release/<mod>/<target_ver>.zip 不得已存在；force=True 時放行）。
        - Gate 3: 版本單調遞增（target_ver 必須嚴格大於同三元組在庫最高 revision；force=True 且 target == highest 時放行同版本覆蓋，但小於歷史舊版本仍阻斷）。
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
        exact_rel_zip = f"module.release://{module_name}/{target_version}.zip"
        if vfs.exists(exact_rel_zip) and not force:
            errors.append(
                f"Gate 2 Failed (Immutability): Version '{target_version}' already exists in release repository "
                f"({exact_rel_zip}). Duplicate release forbidden (use --force to override)."
            )

        # Gate 3: Monotonicity / No Rollback
        mod_rel_root = f"module.release://{module_name}"
        if vfs.exists(mod_rel_root):
            real_rel_dir = uri.resolve(mod_rel_root)
            if os.path.isdir(real_rel_dir):
                all_existing_versions: List[semver.VersionTuple] = []
                for item in os.listdir(real_rel_dir):
                    if item.endswith(".zip"):
                        item_ver = item[:-4]
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

    def release_module(self, module_name: str, force: bool = False, _skip_check: bool = False) -> Tuple[bool, str]:
        """
        單一模組純淨發布 (dev release <mod> [--force]):
        1. 若 _skip_check=False，執行 release_check(module_name, force=force)。
        2. 調用 Builder.package_release(module_name, target_version)。
        """
        if not _skip_check:
            passed, errors = self.release_check(module_name, force=force)
            if not passed:
                err_msg = "\n  - ".join(errors)
                return False, f"Release pre-flight check failed for '{module_name}':\n  - {err_msg}"

        src_uri = f"module.source://{module_name}"
        manifest_data = vfs.read_json(f"{src_uri}/manifest.json")
        target_version = manifest_data.get("version", "1.0.0.0")

        return self.builder.package_release(module_name, target_version)

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
            mdata = vfs.read_json(f"module.source://{m}/manifest.json")
            dep_map[m] = _extract_manifest_dependencies(mdata)

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

    def release_git(self, module_name: str, commit_msg: str, force: bool = False) -> Tuple[bool, str]:
        """
        4 步發布與版本控制安全流水線 (dev release-git <mod> "<msg>" [--force]):
        1. 調用 Tester 執行 dev test <mod>（失敗即中斷）。
        2. 檢查目標版本是否已發布：
           - 若尚未發布：調用 release_check -> release_module(_skip_check=True)。
           - 若已發布且無 --force：略過打包動作，直接推進至本地 Git 提交。
           - 若已發布且傳入 --force：強制調用 release_check(force=True) -> release_module(force=True, _skip_check=True) 覆蓋打包。
        3. 本地 Git 提交：git add -A -> git commit -m commit_msg（攔截致命錯誤） -> git tag [-f] -a "<mod>/v<ver>" -m commit_msg。
        """
        if not commit_msg or not commit_msg.strip():
            return False, "Commit message cannot be empty for release-git."

        src_uri = f"module.source://{module_name}"
        if not vfs.exists(f"{src_uri}/manifest.json"):
            return False, f"manifest.json not found for module '{module_name}'."

        manifest_data = vfs.read_json(f"{src_uri}/manifest.json")
        ver = manifest_data.get("version", "1.0.0.0")
        exact_rel_zip = f"module.release://{module_name}/{ver}.zip"
        is_already_released = vfs.exists(exact_rel_zip)

        # Step 1: E2E Test
        tester = self.tester
        if tester is None:
            from dev.tester import Tester
            tester = Tester()
        test_ret = tester.run(["test", module_name])
        if test_ret != 0:
            return False, f"Step 1 Failed: E2E test failed for module '{module_name}'. Release aborted."

        # Step 2 & 3: Release Check and Packaging (Smart Skip or Force Overwrite)
        if is_already_released and not force:
            print(f"[dev:release-git] Target version '{module_name}@{ver}' is already released ({exact_rel_zip}). Skipping packaging step.")
        else:
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
            return True, f"Successfully packaged release '{module_name}@{ver}'. (Warning: Not a Git repository, skipped commit & tag)"

        c_code, _, c_err = self._run_git_cmd(["add", "-A"])
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

        return True, f"Successfully processed '{module_name}@{ver}' and updated local Git commit & tag '{tag_name}'."
