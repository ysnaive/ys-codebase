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
import sys
import json
import functools
import subprocess
from typing import Optional, Tuple, Dict, Any, List

from core import uri
from core import semver
from dev.builder import Builder
from dev.checker import Checker

class ReleaseVersionExistsError(RuntimeError):
    """Raised when the target release version already exists in the release repository (Gate 2)."""
    pass

class VersionRollbackError(RuntimeError):
    """Raised when the target release version is less than or equal to existing highest revision (Gate 3)."""
    pass

class CyclicDependencyError(RuntimeError):
    """Raised when cyclic dependencies are detected during topological sorting."""
    pass

class Releaser:
    """純淨發布調度器：負責發布前 3-Gate 校驗、DAG 拓撲排序批次發布與 release-git 本地流水線。"""

    def __init__(self, builder: Optional[Builder] = None, checker: Optional[Checker] = None):
        self.builder = builder or Builder()
        self.checker = checker or Checker()

    def _run_git_cmd(self, args: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
        """Runs a Git command safely within local repository."""
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=cwd or uri._get_yscb_root(),
                capture_output=True,
                text=True,
                check=False
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except Exception as e:
            return -1, "", str(e)

    def release_check(self, module_name: str) -> Tuple[bool, List[str]]:
        """
        獨立發布就緒預檢門面 (dev release-check <mod>):
        - Gate 1: Checker.check_module(module_name) 靜態合規性。
        - Gate 2: 版本不可變性（release/<mod>/<target_ver>.zip 不得已存在）。
        - Gate 3: 版本單調遞增（target_ver 必須嚴格大於同三元組在庫最高 revision）。
        - Returns: (passed: bool, error_messages: List[str])
        """
        errors: List[str] = []
        src_uri = f"module.source://{module_name}"
        if not uri.exists(src_uri):
            errors.append(f"Source module '{module_name}' not found at {src_uri}.")
            return False, errors

        manifest_uri = f"{src_uri}/manifest.json"
        if not uri.exists(manifest_uri):
            errors.append(f"manifest.json not found for module '{module_name}'.")
            return False, errors

        # Gate 1: Manifest compliance check
        passed, chk_errors = self.checker.check_module(module_name)
        if not passed:
            errors.append("Gate 1 Failed (Manifest Compliance):\n  - " + "\n  - ".join(chk_errors))

        try:
            manifest_data = uri.read_json(manifest_uri)
            target_version = manifest_data.get("version", "")
            target_tuple = semver.parse_semver(target_version)
        except Exception as e:
            errors.append(f"Invalid version string in manifest.json: {e}")
            return False, errors

        # Gate 2: Immutability / Version Conflict
        exact_rel_zip = f"module.release://{module_name}/{target_version}.zip"
        if uri.exists(exact_rel_zip):
            errors.append(
                f"Gate 2 Failed (Immutability): Version '{target_version}' already exists in release repository "
                f"({exact_rel_zip}). Duplicate release forbidden."
            )

        # Gate 3: Monotonicity / No Rollback
        mod_rel_root = f"module.release://{module_name}"
        if uri.exists(mod_rel_root):
            real_rel_dir = uri.resolve(mod_rel_root)
            if os.path.isdir(real_rel_dir):
                same_triplet_versions: List[semver.VersionTuple] = []
                for item in os.listdir(real_rel_dir):
                    if item.endswith(".zip"):
                        item_ver = item[:-4]
                        try:
                            item_tuple = semver.parse_semver(item_ver)
                            if item_tuple.triplet == target_tuple.triplet:
                                same_triplet_versions.append(item_tuple)
                        except Exception:
                            pass
                
                if same_triplet_versions:
                    same_triplet_versions.sort(key=functools.cmp_to_key(semver.compare_semver))
                    highest_tuple = same_triplet_versions[-1]
                    if semver.compare_semver(target_tuple, highest_tuple) <= 0:
                        errors.append(
                            f"Gate 3 Failed (Monotonicity): Target version '{target_version}' must be strictly greater than "
                            f"the highest existing revision '{highest_tuple}' in the same triplet."
                        )

        return len(errors) == 0, errors

    def release_module(self, module_name: str) -> Tuple[bool, str]:
        """
        單一模組純淨發布 (dev release <mod>):
        1. 執行 release_check(module_name)，若未通過拋出錯誤中斷。
        2. 調用 Builder.package_release(module_name, target_version)。
        """
        passed, errors = self.release_check(module_name)
        if not passed:
            err_msg = "\n  - ".join(errors)
            return False, f"Release pre-flight check failed for '{module_name}':\n  - {err_msg}"

        src_uri = f"module.source://{module_name}"
        manifest_data = uri.read_json(f"{src_uri}/manifest.json")
        target_version = manifest_data.get("version", "1.0.0.0")

        return self.builder.package_release(module_name, target_version)

    def release_all(self) -> Dict[str, Tuple[bool, str]]:
        """
        全量模組依賴拓撲批次發布 (dev release --all):
        1. 讀取 source/ 下所有模組 manifest.json 中的 dependencies。
        2. 建構 DAG 並使用 Kahn 演算法計算拓撲發布序列。
        3. 依序調用 release_module()。
        """
        results: Dict[str, Tuple[bool, str]] = {}
        src_root_uri = "module.source://"
        if not uri.exists(src_root_uri):
            return results

        available_modules = set()
        for item in uri.listdir(src_root_uri):
            m_path = f"module.source://{item}/manifest.json"
            if uri.exists(m_path):
                available_modules.add(item)

        if not available_modules:
            return results

        # Build Dependency Graph
        in_degree: Dict[str, int] = {m: 0 for m in available_modules}
        adj_list: Dict[str, List[str]] = {m: [] for m in available_modules}

        for m in available_modules:
            mdata = uri.read_json(f"module.source://{m}/manifest.json")
            raw_deps = mdata.get("dependencies", {})
            if isinstance(raw_deps, dict):
                dep_names = list(raw_deps.keys())
            elif isinstance(raw_deps, list):
                dep_names = raw_deps
            else:
                dep_names = []

            for dep in dep_names:
                if dep in available_modules:
                    # dep must be released before m (dep -> m)
                    adj_list[dep].append(m)
                    in_degree[m] += 1

        # Kahn's Algorithm
        queue = [m for m, deg in in_degree.items() if deg == 0]
        topo_order: List[str] = []

        while queue:
            curr = queue.pop(0)
            topo_order.append(curr)
            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(topo_order) != len(available_modules):
            cyclic_mods = [m for m, deg in in_degree.items() if deg > 0]
            raise CyclicDependencyError(f"Cyclic dependency detected among modules: {cyclic_mods}")

        # Execute release in topological order
        for mod_name in topo_order:
            results[mod_name] = self.release_module(mod_name)

        return results

    def release_git(self, module_name: str, commit_msg: str) -> Tuple[bool, str]:
        """
        4 步發布與版本控制安全流水線 (dev release-git <mod> <msg>):
        1. 調用 Tester 執行 dev test <mod>（失敗即中斷）。
        2. 調用 release_check(module_name)（失敗即中斷）。
        3. 調用 release_module(module_name)（失敗即中斷）。
        4. 本地 Git 提交：git add -A -> git commit -m commit_msg -> git tag -a "<mod>/v<ver>" -m commit_msg。
        🚨 防呆約束：嚴禁調用 git push，所有操作僅於本地端完成。
        """
        if not commit_msg or not commit_msg.strip():
            return False, "Commit message cannot be empty for release-git."

        # Step 1: E2E Test
        from dev.tester import Tester
        tester = Tester()
        test_ret = tester.run(["test", module_name])
        if test_ret != 0:
            return False, f"Step 1 Failed: E2E test failed for module '{module_name}'. Release aborted."

        # Step 2: Release Check
        passed, chk_errors = self.release_check(module_name)
        if not passed:
            err_details = "\n  - ".join(chk_errors)
            return False, f"Step 2 Failed: Release readiness check failed for '{module_name}':\n  - {err_details}"

        # Step 3: Pure Release Packaging
        ok_pkg, msg_pkg = self.release_module(module_name)
        if not ok_pkg:
            return False, f"Step 3 Failed: Release packaging failed for '{module_name}': {msg_pkg}"

        # Step 4: Local Git Commit and Tag
        src_uri = f"module.source://{module_name}"
        manifest_data = uri.read_json(f"{src_uri}/manifest.json")
        ver = manifest_data.get("version", "1.0.0.0")
        tag_name = f"{module_name}/v{ver}"

        git_check, _, _ = self._run_git_cmd(["rev-parse", "--is-inside-work-tree"])
        if git_check != 0:
            return True, f"Successfully packaged release '{module_name}@{ver}'. (Warning: Not a Git repository, skipped commit & tag)"

        # Local Add & Commit
        c_code, _, c_err = self._run_git_cmd(["add", "-A"])
        if c_code != 0:
            return False, f"Git add failed during release-git: {c_err}"

        c_code, _, c_err = self._run_git_cmd(["commit", "-m", commit_msg])
        if c_code != 0:
            # If nothing to commit (e.g. workspace clean), continue to tag
            pass

        # Local Tag
        t_code, _, t_err = self._run_git_cmd(["tag", "-a", tag_name, "-m", commit_msg])
        if t_code != 0:
            return False, f"Git tag failed for '{tag_name}': {t_err}"

        return True, f"Successfully released '{module_name}@{ver}' and created local Git commit & tag '{tag_name}'."

# Backward compatibility alias
ReleasePipeline = Releaser
