#!/usr/bin/env python3
"""
yscb_installer.py — YS-Codebase 核心模組化工具庫安裝管理系統 (v2.0)

核心特性：
  - 純 Python 3 標準庫實現，Zero External Dependency
  - 支援 Source (源碼/開發者模式) 與 Build (發布物/使用者模式) 雙軌安裝
  - 支援 2×2 設定協定 (Codebase/Module × Project/User)
  - 核心 Core SDK (yscb_core) 作為標準相依與建置產出物
  - 提供完整 CLI 工具鏈 (help, init, install, pull, build, push, status, list, remove, diff)
"""

import sys
import os
import re
import shutil
import subprocess
import json
import argparse
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Union

# Windows 控制台編碼防呆 (強制 UTF-8 輸出)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── 常量定義 ─────────────────────────────────────────────────────────────
DEFAULT_REPO = "https://github.com/YsNaive/ys-codebase.git"
DEFAULT_BRANCH = "main"
CONFIG_FILENAME = "yscb_config.json"
LOCAL_CONFIG_FILENAME = "yscb_config.local.json"
TEMPLATE_CONFIG_FILENAME = "yscb_config.template.json"
CACHE_DIRNAME = ".yscb_cache"
INSTALLER_VERSION = "2.2.0"


def extract_installer_version(script_path: Path) -> Optional["SemVer"]:
    """從起手腳本內容中提取 INSTALLER_VERSION"""
    if not script_path.is_file():
        return None
    try:
        content = script_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'INSTALLER_VERSION\s*=\s*["\']([^"\']+)["\']', content)
        if m:
            return SemVer(m.group(1))
    except Exception:
        pass
    return None



# ── 工具函式 ─────────────────────────────────────────────────────────────
def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """遞迴無損合併兩個字典"""
    import copy
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


# ── 語意化版本與相依約束 (SemVer 2.0.0 & Constraints) ───────────────────
SEMVER_REGEX = re.compile(
    r"^[vV]?(?P<major>0|[1-9]\d*)"
    r"(?:\.(?P<minor>0|[1-9]\d*))?"
    r"(?:\.(?P<patch>0|[1-9]\d*))?"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def _compare_prerelease(pre1: Optional[str], pre2: Optional[str]) -> int:
    if pre1 is None and pre2 is None:
        return 0
    if pre1 is None and pre2 is not None:
        return 1
    if pre1 is not None and pre2 is None:
        return -1

    parts1 = pre1.split(".")  # type: ignore
    parts2 = pre2.split(".")  # type: ignore

    for p1, p2 in zip(parts1, parts2):
        if p1 == p2:
            continue
        p1_is_num = p1.isdigit()
        p2_is_num = p2.isdigit()
        if p1_is_num and p2_is_num:
            return 1 if int(p1) > int(p2) else -1
        elif p1_is_num and not p2_is_num:
            return -1
        elif not p1_is_num and p2_is_num:
            return 1
        else:
            return 1 if p1 > p2 else -1

    if len(parts1) > len(parts2):
        return 1
    elif len(parts1) < len(parts2):
        return -1
    return 0


class SemVer:
    """SemVer 2.0.0 語意化版本類別"""
    __slots__ = ("major", "minor", "patch", "prerelease", "build")

    def __init__(self, version: Union[str, "SemVer"]):
        if isinstance(version, SemVer):
            self.major = version.major
            self.minor = version.minor
            self.patch = version.patch
            self.prerelease = version.prerelease
            self.build = version.build
            return

        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"無效的版本格式: {repr(version)}")

        cleaned = version.strip()
        match = SEMVER_REGEX.match(cleaned)
        if not match:
            raise ValueError(f"無法解析為合法 SemVer 2.0.0 格式: '{version}'")

        gd = match.groupdict()
        self.major = int(gd["major"])
        self.minor = int(gd["minor"]) if gd["minor"] is not None else 0
        self.patch = int(gd["patch"]) if gd["patch"] is not None else 0
        self.prerelease = gd["prerelease"]
        self.build = gd["build"]

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        return cls(version_str)

    @classmethod
    def is_valid(cls, version_str: Any) -> bool:
        if not isinstance(version_str, str) or not version_str.strip():
            return False
        return bool(SEMVER_REGEX.match(version_str.strip()))

    def bump_major(self) -> "SemVer":
        return SemVer(f"{self.major + 1}.0.0")

    def bump_minor(self) -> "SemVer":
        return SemVer(f"{self.major}.{self.minor + 1}.0")

    def bump_patch(self) -> "SemVer":
        return SemVer(f"{self.major}.{self.minor}.{self.patch + 1}")

    def bump(self, level: str) -> "SemVer":
        norm_level = level.strip().lower()
        if norm_level == "major":
            return self.bump_major()
        elif norm_level == "minor":
            return self.bump_minor()
        elif norm_level == "patch":
            return self.bump_patch()
        else:
            raise ValueError(f"未知的遞進等級 '{level}'，僅支援 'major', 'minor', 'patch'。")

    def __tuple_key(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            if not SemVer.is_valid(other):
                return False
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return (
            self.__tuple_key() == other.__tuple_key()
            and _compare_prerelease(self.prerelease, other.prerelease) == 0
        )

    def __ne__(self, other: Any) -> bool:
        eq = self.__eq__(other)
        if eq is NotImplemented:
            return NotImplemented
        return not eq

    def __lt__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        if self.__tuple_key() < other.__tuple_key():
            return True
        elif self.__tuple_key() > other.__tuple_key():
            return False
        return _compare_prerelease(self.prerelease, other.prerelease) < 0

    def __le__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return not self.__le__(other)

    def __ge__(self, other: Union[str, "SemVer"]) -> bool:
        if isinstance(other, str):
            other = SemVer(other)
        if not isinstance(other, SemVer):
            return NotImplemented
        return not self.__lt__(other)

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease is not None:
            s += f"-{self.prerelease}"
        if self.build is not None:
            s += f"+{self.build}"
        return s

    def __repr__(self) -> str:
        return f"SemVer('{str(self)}')"


class VersionConstraint:
    """語意化版本相依約束表達式解析與匹配器"""
    __slots__ = ("raw_expr", "_predicates")

    def __init__(self, constraint_expr: str):
        self.raw_expr = constraint_expr.strip() if constraint_expr else "*"
        self._predicates: List[Tuple[str, SemVer]] = []
        self._parse(self.raw_expr)

    def _parse(self, expr: str):
        if not expr or expr == "*":
            return

        raw_parts = [p.strip() for p in expr.split(",") if p.strip()]

        for part in raw_parts:
            if part == "*":
                continue

            op_match = re.match(r"^(\^|~|>=|<=|>|<|==|!=|=)?\s*(.+)$", part)
            if not op_match:
                continue

            op, v_str = op_match.groups()
            op = op or "=="
            if op == "=":
                op = "=="
            v = SemVer(v_str.strip())

            # Caret 相容 (^1.2.3)
            if op == "^":
                self._predicates.append((">=", v))
                if v.major > 0:
                    self._predicates.append(("<", SemVer(f"{v.major + 1}.0.0")))
                elif v.minor > 0:
                    self._predicates.append(("<", SemVer(f"0.{v.minor + 1}.0")))
                else:
                    self._predicates.append(("<", SemVer(f"0.0.{v.patch + 1}")))
                continue

            # Tilde 相容 (~1.2.3 或 ~1.2)
            if op == "~":
                self._predicates.append((">=", v))
                self._predicates.append(("<", SemVer(f"{v.major}.{v.minor + 1}.0")))
                continue

            # 標準運算符
            self._predicates.append((op, v))


    def matches(self, version: Union[str, SemVer]) -> bool:
        if not isinstance(version, SemVer):
            try:
                version = SemVer(version)
            except Exception:
                return False
        for op, target_v in self._predicates:
            if op == ">=" and not (version >= target_v):
                return False
            elif op == "<=" and not (version <= target_v):
                return False
            elif op == ">" and not (version > target_v):
                return False
            elif op == "<" and not (version < target_v):
                return False
            elif op == "==" and not (version == target_v):
                return False
            elif op == "!=" and not (version != target_v):
                return False
        return True

    @classmethod
    def parse_dependency_spec(cls, spec_str: str) -> Tuple[str, "VersionConstraint"]:
        if not spec_str or not spec_str.strip():
            raise ValueError("相依性描述不能為空。")
        cleaned = spec_str.strip()
        match = re.search(r"(\^|~|>=|<=|>|<|==|=|!=)", cleaned)
        if match:
            idx = match.start()
            mod_name = cleaned[:idx].strip()
            expr = cleaned[idx:].strip()
            return mod_name, cls(expr)
        parts = cleaned.split(maxsplit=1)
        if len(parts) == 1:
            return parts[0].strip(), cls("*")
        else:
            return parts[0].strip(), cls(parts[1].strip())

    def __str__(self) -> str:
        return self.raw_expr

    def __repr__(self) -> str:
        return f"VersionConstraint('{self.raw_expr}')"


# ── 配置管理 (Config Manager) ───────────────────────────────────────────
class ConfigManager:
    """管理 yscb_config.json 與 yscb_config.local.json 的讀寫、驗證與更新"""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.config_path = root_dir / CONFIG_FILENAME
        self.local_config_path = root_dir / LOCAL_CONFIG_FILENAME
        self.template_path = root_dir / TEMPLATE_CONFIG_FILENAME

    def exists(self) -> bool:
        return self.config_path.exists()

    def create_default(
        self,
        repo: str = DEFAULT_REPO,
        branch: str = DEFAULT_BRANCH,
        project_root: str = ".",
        force: bool = False
    ) -> Dict[str, Any]:
        if self.exists() and not force:
            raise FileExistsError(f"設定檔已存在：{self.config_path}。若需重新初始化請加上 --force。")

        yscb_dir = self.root_dir.resolve()
        project_dir = (yscb_dir / project_root).resolve()
        rel_project_root = os.path.relpath(project_dir, yscb_dir).replace("\\", "/")
        rel_yscb_root = os.path.relpath(yscb_dir, project_dir).replace("\\", "/")

        if self.template_path.exists():
            try:
                with open(self.template_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                if "remote" not in config:
                    config["remote"] = {}
                config["remote"]["repo"] = repo
                config["remote"]["branch"] = branch
                if "paths" not in config:
                    config["paths"] = {}
                config["paths"]["project_root"] = rel_project_root
                config["paths"]["yscb_root"] = rel_yscb_root
                self.save(config)
                return config
            except Exception as e:
                print(f"[WARN] 讀取模板檔 {TEMPLATE_CONFIG_FILENAME} 失敗: {e}，改用內建預設值。")

        config = {
            "version": "2.0",
            "paths": {
                "project_root": rel_project_root,
                "yscb_root": rel_yscb_root
            },
            "remote": {
                "repo": repo,
                "branch": branch
            },
            "installed_modules": {},
            "custom_settings": {}
        }
        self.save(config)
        return config

    def get_project_root(self) -> Path:
        """取得專案根目錄 (project_root) 的絕對 Path"""
        cfg = self.load()
        rel = cfg.get("paths", {}).get("project_root", ".")
        return (self.root_dir / rel).resolve()

    def get_yscb_root(self) -> Path:
        """取得 YSCB 工具庫根目錄 (yscb_root) 的絕對 Path"""
        return self.root_dir.resolve()

    def load(self, include_local: bool = True) -> Dict[str, Any]:
        """載入設定檔（若存在 yscb_config.local.json 則自動無損合併）"""
        base_cfg = {
            "version": "2.0",
            "paths": {
                "project_root": ".",
                "yscb_root": "."
            },
            "remote": {
                "repo": DEFAULT_REPO,
                "branch": DEFAULT_BRANCH
            },
            "installed_modules": {},
            "custom_settings": {}
        }

        if self.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        base_cfg = deep_merge(base_cfg, loaded)
            except Exception as e:
                print(f"[WARN] 讀取 {CONFIG_FILENAME} 失敗: {e}，回退至預設配置。")

        if include_local and self.local_config_path.is_file():
            try:
                with open(self.local_config_path, "r", encoding="utf-8") as f:
                    local_cfg = json.load(f)
                    if isinstance(local_cfg, dict):
                        base_cfg = deep_merge(base_cfg, local_cfg)
            except Exception:
                pass

        return base_cfg

    def save(self, config: Dict[str, Any]):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def record_installed_module(self, module_name: str, mode: str, version: str = "1.0.0", meta: Optional[Dict[str, Any]] = None):
        # 僅讀寫基礎 yscb_config.json，不混淆 local 設定
        if not self.exists():
            cfg = self.load(include_local=False)
        else:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

        if "installed_modules" not in cfg:
            cfg["installed_modules"] = {}

        now_str = datetime.datetime.now().isoformat(timespec="seconds")
        entry = {
            "version": version,
            "mode": mode,
            "installed_at": now_str
        }
        if meta:
            entry.update(meta)

        cfg["installed_modules"][module_name] = entry
        self.save(cfg)

    def remove_installed_module(self, module_name: str):
        if not self.exists():
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        if "installed_modules" in cfg and module_name in cfg["installed_modules"]:
            del cfg["installed_modules"][module_name]
            self.save(cfg)


# ── Git 遠端倉庫與快取管理 (Git Remote Client) ───────────────────────────
class GitRemoteClient:
    """負責同步、快取與推送中央 Git 倉庫"""

    def __init__(self, root_dir: Path, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH):
        self.root_dir = root_dir
        self.repo = repo
        self.branch = branch
        self.cache_dir = root_dir / CACHE_DIRNAME

    def is_git_available(self) -> bool:
        return shutil.which("git") is not None

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        if not self.is_git_available():
            raise RuntimeError("本機環境未安裝 Git 或未加入 PATH，無法執行遠端倉庫操作。")
        cmd = ["git"] + args
        return subprocess.run(
            cmd,
            cwd=str(cwd or self.root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600
        )

    def sync_cache(self, force_refresh: bool = False) -> Path:
        """將遠端倉庫 clone 或 pull 至本地快取 (.yscb_cache)"""
        # 若 repo 指向當前目錄且非快取本體，直接回傳
        if os.path.exists(self.repo) and Path(self.repo).resolve() == self.root_dir.resolve():
            return self.root_dir

        if self.cache_dir.exists() and not force_refresh:
            return self.cache_dir

        # 若 repo 為本機存在的目錄（例如本地回歸測試或聯調）
        if os.path.isdir(self.repo):
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir, ignore_errors=True)
            self.cache_dir.parent.mkdir(parents=True, exist_ok=True)

            def ignore_cache_files(folder, files):
                ignored = []
                for f in files:
                    if f in [CACHE_DIRNAME, ".git", "__pycache__", "env", "venv", ".venv", "modules"]:
                        ignored.append(f)
                return ignored

            shutil.copytree(self.repo, self.cache_dir, ignore=ignore_cache_files, dirs_exist_ok=True)
            return self.cache_dir

        if not self.cache_dir.exists():
            print(f"[INFO] 正在複製遠端庫至快取: {self.repo} ({self.branch})...")
            self.cache_dir.parent.mkdir(parents=True, exist_ok=True)
            res = self._run_git(["clone", "--depth", "1", "--branch", self.branch, self.repo, str(self.cache_dir)])
            if res.returncode != 0:
                res2 = self._run_git(["clone", "--depth", "1", self.repo, str(self.cache_dir)])
                if res2.returncode != 0:
                    raise RuntimeError(f"Clone 遠端庫失敗: {res.stderr.strip() or res2.stderr.strip()}")
            print("[INFO] 遠端庫快取初始化完成。")
        else:
            print(f"[INFO] 正在更新快取庫: {self.repo}...")
            res = self._run_git(["pull", "origin", self.branch], cwd=self.cache_dir)
            if res.returncode != 0:
                print(f"[WARN] Pull 快取失敗: {res.stderr.strip()}，嘗試重新 clone...")
                shutil.rmtree(self.cache_dir, ignore_errors=True)
                return self.sync_cache(force_refresh=True)

        return self.cache_dir

    def push_changes(self, commit_msg: str, branch: Optional[str] = None) -> bool:
        """推送變更至遠端庫"""
        target_branch = branch or self.branch
        print(f"[INFO] 正在提交並推送變更至分支: {target_branch}...")

        if (self.root_dir / ".git").is_dir():
            target_repo_dir = self.root_dir
        elif self.cache_dir.is_dir() and (self.cache_dir / ".git").is_dir():
            target_repo_dir = self.cache_dir
        else:
            target_repo_dir = self.root_dir

        self._run_git(["add", "."], cwd=target_repo_dir)
        res_commit = self._run_git(["commit", "-m", commit_msg], cwd=target_repo_dir)
        if res_commit.returncode != 0:
            if "nothing to commit" in res_commit.stdout or "nothing to commit" in res_commit.stderr:
                print("[INFO] 無任何變更需要提交 (Working tree clean)。")
                return True
            print(f"[WARN] Commit 輸出: {res_commit.stderr.strip() or res_commit.stdout.strip()}")

        res_push = self._run_git(["push", "origin", target_branch], cwd=target_repo_dir)
        if res_push.returncode != 0:
            raise RuntimeError(f"Push 失敗: {res_push.stderr.strip()}")
        print("[INFO] 推送成功！")
        return True


# ── 模組管理與解析引擎 (Module Manager & Resolver) ─────────────────────────
class ModuleManager:
    """管理模組的發現、相依解析、安裝、建置與移除"""

    def __init__(self, root_dir: Path, config_mgr: ConfigManager, git_client: GitRemoteClient):
        self.root_dir = root_dir
        self.config_mgr = config_mgr
        self.git_client = git_client

    def _broadcast_modules_changed(self, changes: List[Tuple[str, str]]) -> None:
        """
        於整批安裝/更新/移除事務完成後，單次向所有具備 Hook 之已安裝模組派發廣播。

        :param changes: 本次指令所有異動模組清單，每項為 Tuple(action, module_name)
                        action 可為: "installed" | "updated" | "removed"
        """
        if not changes:
            return

        arg_payload = [f"{action}:{mod_name}" for action, mod_name in changes]
        installed_dict = self.config_mgr.load(include_local=False).get("installed_modules", {})

        for mod_name, mod_info in installed_dict.items():
            mode = mod_info.get("mode", "build")
            mod_dir = self.root_dir / ("source" if mode == "source" else "modules") / mod_name
            if not mod_dir.is_dir():
                mod_dir = self.root_dir / "modules" / mod_name
            hook_script = mod_dir / "scripts" / "_on_modules_changed.py"
            if not hook_script.is_file():
                hook_script = mod_dir / "_on_modules_changed.py"

            if hook_script.is_file():
                print(f"[HOOK] 執行 '{mod_name}' 生命週期連動 Hook: {hook_script.name}...")
                try:
                    cmd = [sys.executable, str(hook_script)] + arg_payload
                    res = subprocess.run(cmd, cwd=str(self.root_dir), timeout=120)
                    if res.returncode != 0:
                        print(f"[WARN] Hook _on_modules_changed.py 執行返回非 0 狀態碼 ({mod_name}): {res.returncode}")
                except Exception as e:
                    print(f"[WARN] 呼叫 _on_modules_changed.py Hook 失敗 ({mod_name}): {e}")

    def _get_source_dir(self, use_cache: bool = False) -> Path:

        if not use_cache:
            for candidate in [
                self.root_dir / "source",
                self.root_dir / "ys_codebase" / "source",
                self.root_dir.parent / "ys_codebase" / "source"
            ]:
                if candidate.is_dir():
                    return candidate
        for cache_candidate in [
            self.git_client.cache_dir / "source",
            self.git_client.cache_dir / "ys_codebase" / "source"
        ]:
            if cache_candidate.is_dir():
                return cache_candidate
        return self.root_dir / "source"

    def _get_build_dir(self, use_cache: bool = False) -> Path:
        if not use_cache:
            for candidate in [
                self.root_dir / "build",
                self.root_dir / "ys_codebase" / "build",
                self.root_dir.parent / "ys_codebase" / "build"
            ]:
                if candidate.is_dir():
                    return candidate
        for cache_candidate in [
            self.git_client.cache_dir / "build",
            self.git_client.cache_dir / "ys_codebase" / "build"
        ]:
            if cache_candidate.is_dir():
                return cache_candidate
        return self.root_dir / "build"

    def read_manifest(self, module_path: Path) -> Dict[str, Any]:
        manifest_file = module_path / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] 解析 manifest 失敗 ({manifest_file}): {e}")
        return {
            "name": module_path.name,
            "version": "1.0.0",
            "description": "",
            "dependencies": []
        }

    def discover_modules(self, from_remote: bool = False) -> Dict[str, Dict[str, Any]]:
        """掃描可用模組（含 source 與 build 狀態）"""
        if from_remote:
            self.git_client.sync_cache(force_refresh=False)
            source_root = self._get_source_dir(use_cache=True)
            build_root = self._get_build_dir(use_cache=True)
        else:
            source_root = self._get_source_dir(use_cache=False)
            build_root = self._get_build_dir(use_cache=False)
            if not source_root.exists() and not build_root.exists():
                if self.git_client.cache_dir.exists():
                    source_root = self._get_source_dir(use_cache=True)
                    build_root = self._get_build_dir(use_cache=True)

        modules = {}

        # 掃描 source/
        if source_root.is_dir():
            for item in source_root.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    m_name = item.name
                    meta = self.read_manifest(item)
                    if m_name not in modules:
                        modules[m_name] = {"name": m_name, "has_source": True, "has_build": False, "meta": meta}
                    else:
                        modules[m_name]["has_source"] = True
                        modules[m_name]["meta"] = meta

        # 掃描 build/
        if build_root.is_dir():
            for item in build_root.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    m_name = item.name
                    meta = self.read_manifest(item)
                    if m_name not in modules:
                        modules[m_name] = {"name": m_name, "has_source": False, "has_build": True, "meta": meta}
                    else:
                        modules[m_name]["has_build"] = True
                        if not modules[m_name].get("meta"):
                            modules[m_name]["meta"] = meta

        return modules

    def resolve_dependencies(self, module_names: List[str], is_source_mode: bool = False) -> List[str]:
        """解析相依性，確保以拓撲順序安裝，並在相依或源碼模式下優先安裝 core"""
        available = self.discover_modules(from_remote=False)
        if not available:
            available = self.discover_modules(from_remote=True)

        resolved: List[str] = []
        visited: Set[str] = set()

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)

            m_info = available.get(name)
            deps = []
            if m_info and "meta" in m_info:
                deps = m_info["meta"].get("dependencies", [])

            for dep in deps:
                try:
                    dep_name = VersionConstraint.parse_dependency_spec(dep)[0]
                except Exception:
                    dep_name = dep.split()[0]
                visit(dep_name)

            resolved.append(name)

        for m in module_names:
            visit(m)

        # 若安裝任何模組或在源碼模式下，確保 core 始終處於最前端安裝位置
        if is_source_mode or any(m != "core" for m in module_names):
            if "core" in available or "core" in resolved:
                if "core" in resolved:
                    resolved.remove("core")
                resolved.insert(0, "core")

        return resolved

    def resolve_build_dependencies(self, module_names: List[str]) -> List[str]:
        """解析建置相依性，確保以正確順序建置所有相依模組"""
        available = self.discover_modules(from_remote=False)
        resolved: List[str] = []
        visited: Set[str] = set()

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)

            m_info = available.get(name)
            deps = []
            if m_info and "meta" in m_info:
                deps = m_info["meta"].get("dependencies", [])

            for dep in deps:
                try:
                    dep_name = VersionConstraint.parse_dependency_spec(dep)[0]
                except Exception:
                    dep_name = dep.split()[0]
                visit(dep_name)

            resolved.append(name)

        for m in module_names:
            visit(m)

        return resolved

    def _locate_module_dir(self, module_name: str, mode: str) -> Optional[Path]:
        """定位模組來源目錄（本地優先，包含本地 ys_codebase，其次快取）"""
        target_sub = "source" if mode == "source" else "build"
        
        # 1. 本地目錄搜尋候選
        candidates = [
            self.root_dir / target_sub / module_name,
            self.root_dir / "ys_codebase" / target_sub / module_name,
            self.root_dir.parent / "ys_codebase" / target_sub / module_name
        ]
        for p in candidates:
            if p.is_dir():
                return p

        # 2. 快取目錄
        cache_candidates = [
            self.git_client.cache_dir / target_sub / module_name,
            self.git_client.cache_dir / "ys_codebase" / target_sub / module_name
        ]
        for cp in cache_candidates:
            if cp.is_dir():
                return cp

        return None

    def check_module_dependencies(self, module_name: str, manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """校驗模組相依性約束 (支援 SemVer 與 VersionConstraint)"""
        deps = manifest.get("dependencies", [])
        if not deps:
            return True, []

        installed_dict = self.config_mgr.load(include_local=False).get("installed_modules", {})
        errors = []

        for dep_spec in deps:
            try:
                dep_name, constraint = VersionConstraint.parse_dependency_spec(dep_spec)
            except Exception as e:
                errors.append(f"相依性描述語法錯誤 '{dep_spec}': {e}")
                continue

            if dep_name == module_name:
                continue

            if dep_name not in installed_dict:
                # 若尚未在 installed_dict，檢查來源庫是否有可用模組
                dep_dir = self._locate_module_dir(dep_name, "build") or self._locate_module_dir(dep_name, "source")
                if not dep_dir:
                    errors.append(f"相依模組 '{dep_name}' 尚未安裝且在來源目錄中找不到。")
                    continue
                dep_manifest = self.read_manifest(dep_dir)
                dep_ver_str = dep_manifest.get("version", "1.0.0")
            else:
                dep_ver_str = installed_dict[dep_name].get("version", "1.0.0")

            if not constraint.matches(dep_ver_str):
                errors.append(
                    f"相依模組 '{dep_name}' 版本不相容 (已安裝/可用: v{dep_ver_str}, 要求: {constraint.raw_expr})"
                )

        return len(errors) == 0, errors

    def _rollback_snapshot(self, dest_path: Path, backup_dir: Optional[Path]):
        """從快照備份目錄還原模組狀態"""
        if backup_dir and backup_dir.is_dir():
            print(f"[ROLLBACK] 正在從快照還原模組: {backup_dir.name} ➔ {dest_path}...")
            try:
                if dest_path.exists():
                    shutil.rmtree(dest_path, ignore_errors=True)
                shutil.copytree(backup_dir, dest_path, dirs_exist_ok=True)
                print(f"[ROLLBACK] 模組 '{dest_path.name}' 已成功還原至升級前狀態。")
            except Exception as e:
                print(f"[CRITICAL] 還原快照失敗: {e}")

    def install_module(self, module_name: str, mode: str = "build", force: bool = False) -> bool:
        """執行單個模組的五階段事務性安全安裝與升級"""
        print(f"[INSTALL] 正在安裝模組 '{module_name}' (模式: {mode})...")

        src_path = self._locate_module_dir(module_name, mode)
        if not src_path:
            self.git_client.sync_cache(force_refresh=True)
            src_path = self._locate_module_dir(module_name, mode)

        if not src_path:
            alt_source = self._locate_module_dir(module_name, "source")
            if mode == "build" and alt_source:
                raise FileNotFoundError(
                    f"找不到模組 '{module_name}' 的 build 發布產物，但已發現可用源碼 ({alt_source})。\n"
                    f"提示：可改用 '--source' 模式安裝源碼，或先執行 'python yscb_installer.py build {module_name}' 生成發布物。"
                )
            raise FileNotFoundError(f"找不到模組 '{module_name}' 的 {mode} 來源檔案。請確認模組名稱或遠端倉庫內容。")

        manifest = self.read_manifest(src_path)
        version = manifest.get("version", "1.0.0")

        # ── Stage 1: Pre-flight Check (相依約束與相容性檢查) ─────────────
        valid_deps, dep_errors = self.check_module_dependencies(module_name, manifest)
        if not valid_deps and not force:
            err_msg = "\n  - ".join(dep_errors)
            raise RuntimeError(f"模組 '{module_name}' 相依性檢查失敗，無法繼續安裝：\n  - {err_msg}\n(若需強制安裝請加上 --force)")

        # 取得已安裝之舊版本紀錄
        installed_dict = self.config_mgr.load(include_local=False).get("installed_modules", {})
        old_info = installed_dict.get(module_name)
        old_version = old_info.get("version") if old_info else None

        if mode == "source":
            dest_path = self.root_dir / "source" / module_name
        else:
            dest_path = self.root_dir / "modules" / module_name

        # ── Stage 2: Staging & Snapshot Backup (建立舊版快照備份) ────────
        backup_dir: Optional[Path] = None
        saved_configs: Dict[str, str] = {}

        if dest_path.exists():
            # 建立快照備份
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            old_ver_tag = old_version or "unknown"
            backup_dir = self.root_dir / CACHE_DIRNAME / "backup" / f"{module_name}_{old_ver_tag}_{timestamp}"
            try:
                backup_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(dest_path, backup_dir, dirs_exist_ok=True)
                # 備份保留策略：每模組僅保留最近 5 份快照，避免快取無限增長
                all_backups = sorted(
                    [d for d in backup_dir.parent.iterdir() if d.is_dir() and d.name.startswith(f"{module_name}_")],
                    key=lambda d: d.stat().st_mtime
                )
                for stale_backup in all_backups[:-5]:
                    shutil.rmtree(stale_backup, ignore_errors=True)
            except Exception as e:
                print(f"[WARN] 建立模組快照備份失敗: {e}")

            # 暫存保留本地既有的 2x2 設定檔
            for cfg_name in ["config.project.json", "config.local.json", "config.json", "config_global.json"]:
                cfg_file = dest_path / cfg_name
                if cfg_file.is_file():
                    try:
                        saved_configs[cfg_name] = cfg_file.read_text(encoding="utf-8")
                    except Exception:
                        pass

        # ── Stage 3: Protected Merge (分級資產覆蓋與增量合併) ───────────
        try:
            if dest_path.exists():
                if not force and dest_path.resolve() == src_path.resolve():
                    print(f"[INFO] 模組 '{module_name}' 已存在於本地 ({dest_path})，跳過本體覆寫。")
                else:
                    shutil.rmtree(dest_path, ignore_errors=True)
                    shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)

            # 結構化配置安全增量深層合併 (config.project.json)
            if "config.project.json" in saved_configs:
                user_cfg_str = saved_configs["config.project.json"]
                target_project_cfg = dest_path / "config.project.json"
                template_project_cfg = dest_path / "config.project.template.json"
                base_cfg_to_merge = {}
                if template_project_cfg.is_file():
                    try:
                        base_cfg_to_merge = json.loads(template_project_cfg.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                try:
                    user_cfg_obj = json.loads(user_cfg_str)
                    merged_project_cfg = deep_merge(base_cfg_to_merge, user_cfg_obj)
                    target_project_cfg.write_text(json.dumps(merged_project_cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                except Exception:
                    target_project_cfg.write_text(user_cfg_str, encoding="utf-8")

            # 本地配置 100% 唯讀保留 (config.local.json)
            if "config.local.json" in saved_configs:
                target_local_cfg = dest_path / "config.local.json"
                target_local_cfg.write_text(saved_configs["config.local.json"], encoding="utf-8")

            # 其餘配置還原
            for cfg_name, content in saved_configs.items():
                if cfg_name in ["config.project.json", "config.local.json"]:
                    continue
                cfg_target = dest_path / cfg_name
                if not cfg_target.exists():
                    try:
                        cfg_target.write_text(content, encoding="utf-8")
                    except Exception:
                        pass

            # ── Stage 4: Migration Execution (鏈式增量遷移與回滾守門) ────────
            migration_hook = dest_path / "scripts" / "_migration.py"
            if not migration_hook.is_file():
                migration_hook = dest_path / "_migration.py"

            if migration_hook.is_file() and old_version and old_version != version:
                print(f"[HOOK] 執行 '{module_name}' 版本遷移 Hook: {migration_hook.name} (v{old_version} ➔ v{version})...")
                try:
                    res = subprocess.run([sys.executable, str(migration_hook), str(old_version), str(version)], cwd=str(dest_path), timeout=600)
                    mig_rc = res.returncode
                except subprocess.TimeoutExpired:
                    print(f"[ERROR] Hook _migration.py 執行逾時 (>600s)！")
                    mig_rc = -1
                if mig_rc != 0:
                    print(f"[ERROR] Hook _migration.py 執行失敗 (狀態碼: {mig_rc})！")
                    self._rollback_snapshot(dest_path, backup_dir)
                    raise RuntimeError(f"模組 '{module_name}' 升級遷移失敗 (exit {mig_rc})，已安全還原至舊版。")

            # ── Stage 5: Commit & Finalize (後置 Hook 與狀態登記) ───────────
            installed_hook = dest_path / "scripts" / "_installed.py"
            if not installed_hook.is_file():
                installed_hook = dest_path / "_installed.py"
            if installed_hook.is_file():
                print(f"[HOOK] 執行 '{module_name}' 安裝後置 Hook: {installed_hook.name}...")
                try:
                    res = subprocess.run([sys.executable, str(installed_hook), str(dest_path), mode], cwd=str(dest_path), timeout=120)
                    if res.returncode != 0:
                        print(f"[WARN] Hook _installed.py 執行返回非 0 狀態碼: {res.returncode}")
                except Exception as e:
                    print(f"[WARN] 呼叫 _installed.py Hook 失敗: {e}")

            self.config_mgr.record_installed_module(
                module_name=module_name,
                mode=mode,
                version=version,
                meta={"description": manifest.get("description", "")}
            )
            print(f"[SUCCESS] 模組 '{module_name}' ({mode} v{version}) 安裝完成 ➔ {dest_path}")
            return True

        except Exception as e:
            if backup_dir and dest_path.exists():
                self._rollback_snapshot(dest_path, backup_dir)
            raise

    def remove_module(self, module_name: str, force: bool = False) -> bool:
        """卸載指定模組，並進行相依安全性檢查與 _uninstall.py Hook 調用"""
        cfg = self.config_mgr.load(include_local=False)
        installed = cfg.get("installed_modules", {})

        if module_name not in installed:
            print(f"[WARN] 模組 '{module_name}' 尚未安裝。")
            return False

        if not force:
            # 依據各已安裝模組 manifest.json 宣告之 dependencies 執行真實相依安全檢查
            blockers: List[str] = []
            for other_mod, info in installed.items():
                if other_mod == module_name:
                    continue
                other_mode = info.get("mode", "build")
                other_dir = self.root_dir / ("source" if other_mode == "source" else "modules") / other_mod
                if not (other_dir / "manifest.json").is_file():
                    located = self._locate_module_dir(other_mod, other_mode)
                    if not located:
                        located = self._locate_module_dir(other_mod, "source" if other_mode != "source" else "build")
                    if located:
                        other_dir = located
                deps = self.read_manifest(other_dir).get("dependencies", []) if other_dir.is_dir() else []
                for dep_spec in deps:
                    try:
                        dep_name, _ = VersionConstraint.parse_dependency_spec(dep_spec)
                    except Exception:
                        parts = str(dep_spec).split()
                        dep_name = parts[0] if parts else ""
                    if dep_name == module_name:
                        blockers.append(other_mod)
                        break
            if blockers:
                raise RuntimeError(
                    f"無法移除 '{module_name}'：模組 {', '.join(blockers)} 仍相依於此模組。若需強制移除請加 --force。"
                )

        mod_info = installed[module_name]
        mode = mod_info.get("mode", "build")
        target_dir = self.root_dir / ("source" if mode == "source" else "modules") / module_name

        if target_dir.exists():
            # 執行 _uninstall.py Hook
            uninstall_hook = target_dir / "scripts" / "_uninstall.py"
            if not uninstall_hook.is_file():
                uninstall_hook = target_dir / "_uninstall.py"
            if uninstall_hook.is_file():
                print(f"[HOOK] 執行 '{module_name}' 卸載前置 Hook: {uninstall_hook.name}...")
                try:
                    res = subprocess.run([sys.executable, str(uninstall_hook), str(target_dir), mode], cwd=str(target_dir), timeout=120)
                    if res.returncode != 0:
                        print(f"[WARN] Hook _uninstall.py 執行返回非 0 狀態碼: {res.returncode}")
                except Exception as e:
                    print(f"[WARN] 呼叫 _uninstall.py Hook 失敗: {e}")

            shutil.rmtree(target_dir, ignore_errors=True)
            print(f"[INFO] 已清理模組目錄：{target_dir}")

        self.config_mgr.remove_installed_module(module_name)
        print(f"[SUCCESS] 模組 '{module_name}' 已成功移除。")
        return True

    def list_module_backups(self, module_name: str) -> List[Path]:
        """列出指定模組於 .yscb_cache/backup/ 之可用快照備份（依時間新至舊排序）"""
        backup_root = self.root_dir / CACHE_DIRNAME / "backup"
        if not backup_root.is_dir():
            return []
        backups = [d for d in backup_root.iterdir() if d.is_dir() and d.name.startswith(f"{module_name}_")]
        return sorted(backups, key=lambda d: d.stat().st_mtime, reverse=True)

    def rollback_module(self, module_name: str, list_only: bool = False, backup_name: Optional[str] = None) -> bool:
        """自本地快照備份還原模組至升級前狀態，並同步回寫安裝紀錄"""
        backups = self.list_module_backups(module_name)

        if list_only:
            print(f"\n[ROLLBACK] 模組 '{module_name}' 可用快照備份清單：")
            if not backups:
                print("  [INFO] 無任何可用快照備份。")
                return True
            for b in backups:
                ts = datetime.datetime.fromtimestamp(b.stat().st_mtime).isoformat(timespec="seconds")
                print(f"  • {b.name}  (建立於 {ts})")
            print(f"\n提示: 執行 'python yscb_installer.py rollback {module_name}' 還原最近一份，或加 '--to <備份名稱>' 指定。\n")
            return True

        if not backups:
            raise RuntimeError(f"模組 '{module_name}' 無任何可用快照備份，無法執行還原。")

        target_backup: Optional[Path] = None
        if backup_name:
            for b in backups:
                if b.name == backup_name:
                    target_backup = b
                    break
            if not target_backup:
                raise RuntimeError(f"找不到名為 '{backup_name}' 的快照備份。可執行 'rollback {module_name} --list' 檢視可用清單。")
        else:
            target_backup = backups[0]

        installed = self.config_mgr.load(include_local=False).get("installed_modules", {})
        mode = installed.get(module_name, {}).get("mode", "build")
        dest_path = self.root_dir / ("source" if mode == "source" else "modules") / module_name

        self._rollback_snapshot(dest_path, target_backup)

        restored_manifest = self.read_manifest(dest_path)
        restored_version = restored_manifest.get("version", "1.0.0")
        self.config_mgr.record_installed_module(
            module_name=module_name,
            mode=mode,
            version=restored_version,
            meta={"description": restored_manifest.get("description", "")}
        )
        print(f"[SUCCESS] 模組 '{module_name}' 已自快照 '{target_backup.name}' 還原 (v{restored_version}) ➔ {dest_path}")
        return True

    def build_module(self, module_name: str) -> bool:
        """將 source/<module> 編譯/建置為 build/<module>"""
        src_path = self._locate_module_dir(module_name, "source")
        if not src_path or not src_path.is_dir():
            raise FileNotFoundError(f"找不到模組 '{module_name}' 的源碼目錄，無法執行 build。")

        # 決定 build 產出目標目錄
        if (self.root_dir / "source" / module_name).is_dir():
            dest_path = self.root_dir / "build" / module_name
        elif (self.root_dir / "ys_codebase" / "source" / module_name).is_dir():
            dest_path = self.root_dir / "ys_codebase" / "build" / module_name
        elif (self.root_dir.parent / "ys_codebase" / "source" / module_name).is_dir():
            dest_path = self.root_dir.parent / "ys_codebase" / "build" / module_name
        else:
            # 源碼來自遠端快取 (.yscb_cache) 等其他位置時，回退至本地 build/ 輸出
            dest_path = self.root_dir / "build" / module_name
        # 確保建置前徹底清理既有目標目錄，杜絕歷史殘留檔案
        if dest_path.exists():
            shutil.rmtree(dest_path, ignore_errors=True)
        dest_path.mkdir(parents=True, exist_ok=True)

        manifest = self.read_manifest(src_path)

        custom_build_script = src_path / "build.py"
        if custom_build_script.is_file():
            print(f"[BUILD] 執行 '{module_name}' 自訂建置腳本：{custom_build_script}...")
            res = subprocess.run([sys.executable, str(custom_build_script), str(src_path), str(dest_path)], cwd=str(src_path), timeout=600)
            if res.returncode != 0:
                raise RuntimeError(f"模組 '{module_name}' 自訂建置失敗 (Exit {res.returncode})。")
        else:
            print(f"[BUILD] 使用標準管線將 '{module_name}' 封裝至 {dest_path}...")
            custom_excludes = manifest.get("build_exclude", [])

            def ignore_dev_files(folder, files):
                ignored = []
                for f in files:
                    # 預設排除規則（排除開發檔案、快取與本地實例設定，保留範本 template）
                    if f in [
                        ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                        "tests", "scratch", ".vscode", ".idea", "build.py",
                        "config.json", "config_global.json", "config.project.json", "config.local.json",
                        "yscb_config.local.json"
                    ]:
                        ignored.append(f)
                    elif f.endswith(".pyc") or f.endswith(".pyo") or f.endswith(".pyd") or f.endswith(".local.json"):
                        ignored.append(f)
                    elif f in custom_excludes:
                        ignored.append(f)
                return ignored

            shutil.copytree(src_path, dest_path, ignore=ignore_dev_files, dirs_exist_ok=True)

        # 在 build/<module>/manifest.json 注入 built_at 時間戳與發布元數據
        build_manifest_path = dest_path / "manifest.json"
        build_manifest = self.read_manifest(dest_path)
        build_manifest["built_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        if "version" in manifest:
            build_manifest["version"] = manifest["version"]
        if "dependencies" in manifest:
            build_manifest["dependencies"] = manifest["dependencies"]
        if "description" in manifest:
            build_manifest["description"] = manifest["description"]

        with open(build_manifest_path, "w", encoding="utf-8") as f:
            json.dump(build_manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"[SUCCESS] 模組 '{module_name}' 建置完成 (v{build_manifest.get('version', '1.0.0')}) ➔ {dest_path}")
        return True

    def diff_modules(self, module_names: List[str]) -> bool:
        """比對本地已安裝模組與遠端 cache 最新版本之間的檔案差異"""
        print("[INFO] 正在同步遠端 cache...")
        try:
            self.git_client.sync_cache(force_refresh=True)
        except Exception as e:
            print(f"[WARN] 同步遠端 cache 失敗（可能在離線環境），改用本地快取比對: {e}")

        cfg = self.config_mgr.load(include_local=False)
        installed = cfg.get("installed_modules", {})

        if not module_names:
            module_names = list(installed.keys())

        if not module_names:
            print("[INFO] 目前無任何已安裝模組可供比對。")
            return True

        EXCLUDE_FILES = {
            "config.json", "config_global.json", "config.project.json", "config.local.json",
            "yscb_config.local.json"
        }
        total_diff = 0

        for mod in module_names:
            mod_info = installed.get(mod, {})
            mode = mod_info.get("mode", "build")
            target_sub = "source" if mode == "source" else "build"

            local_dir: Optional[Path] = None
            for candidate in [
                self.root_dir / ("source" if mode == "source" else "modules") / mod,
                self.root_dir / "modules" / mod,
            ]:
                if candidate.is_dir():
                    local_dir = candidate
                    break

            remote_dir = self.git_client.cache_dir / target_sub / mod
            if not remote_dir.is_dir():
                print(f"\n[{mod}] [WARN] 遠端 cache 無此模組 ({target_sub}/{mod})，跳過比對。")
                continue

            if not local_dir:
                print(f"\n[{mod}] [LOCAL_MISSING] 本地未安裝，遠端存在。")
                total_diff += 1
                continue

            print(f"\n[{mod}] 比對 {local_dir} ↔ {remote_dir}")
            print("  " + "-" * 66)

            def collect_files(base: Path) -> Dict[str, Path]:
                result = {}
                for f in base.rglob("*"):
                    if f.is_file() and f.name not in EXCLUDE_FILES and not f.name.endswith(".local.json") and "__pycache__" not in str(f):
                        result[f.relative_to(base).as_posix()] = f
                return result

            local_files = collect_files(local_dir)
            remote_files = collect_files(remote_dir)
            all_paths = sorted(set(local_files) | set(remote_files))
            mod_diff = 0

            for rel in all_paths:
                in_local = rel in local_files
                in_remote = rel in remote_files
                if in_local and in_remote:
                    c1 = local_files[rel].read_bytes()
                    c2 = remote_files[rel].read_bytes()
                    if c1 != c2:
                        print(f"  [MODIFIED]     {rel}")
                        mod_diff += 1
                elif in_local:
                    print(f"  [LOCAL_ONLY]   {rel}")
                    mod_diff += 1
                else:
                    print(f"  [REMOTE_ONLY]  {rel}")
                    mod_diff += 1

            if mod_diff == 0:
                print(f"  [SAME] 本地與遠端完全一致 ({len(all_paths)} 檔)")
            else:
                print(f"  --\n  共 {mod_diff} 個差異檔案。")
                total_diff += mod_diff

        print()
        if total_diff == 0:
            print("[SUCCESS] 所有比對模組均與遠端完全一致，無任何差異。")
        else:
            print(f"[INFO] 比對完成，共發現 {total_diff} 個差異。")
        return True

    def self_update(self, force: bool = False) -> bool:
        """從遠端倉庫或快取更新 installer (yscb_installer.py) 與統一 CLI (yscb_cli.py)"""
        print("[SELF-UPDATE] 正在檢查核心安裝器與起手腳本更新...")

        # 1. 優先同步快取
        try:
            self.git_client.sync_cache(force_refresh=True)
        except Exception as e:
            print(f"[WARN] 同步遠端快取失敗: {e}")

        # 2. 定位最新來源腳本
        cache_dir = self.git_client.cache_dir
        source_installer = cache_dir / "yscb_installer.py"
        if not source_installer.is_file():
            source_installer = cache_dir / "ys_codebase" / "yscb_installer.py"

        source_cli = cache_dir / "yscb_cli.py"
        if not source_cli.is_file():
            source_cli = cache_dir / "ys_codebase" / "yscb_cli.py"

        # 若在本地開發空間，亦可從本地 ys_codebase/ 取得
        if not source_installer.is_file():
            local_inst = self.root_dir / "ys_codebase" / "yscb_installer.py"
            if local_inst.is_file():
                source_installer = local_inst
        if not source_cli.is_file():
            local_cli = self.root_dir / "ys_codebase" / "yscb_cli.py"
            if local_cli.is_file():
                source_cli = local_cli

        if not source_installer.is_file():
            print("[ERROR] 找不到可用的最新 yscb_installer.py 來源檔案。")
            return False

        latest_ver = extract_installer_version(source_installer) or SemVer(INSTALLER_VERSION)
        curr_ver = extract_installer_version(self.root_dir / "yscb_installer.py") or SemVer(INSTALLER_VERSION)

        if latest_ver <= curr_ver and not force:
            print(f"[INFO] 當前核心安裝器已是最新版本 (v{curr_ver})，無須更新。")
            return True

        print(f"[SELF-UPDATE] 正在升級起手腳本: v{curr_ver} ➔ v{latest_ver}...")

        # 3. Windows 安全原子替換 (寫入 .tmp 再 rename/replace)
        target_installer = self.root_dir / "yscb_installer.py"
        target_cli = self.root_dir / "yscb_cli.py"

        def atomic_replace(src: Path, dst: Path):
            tmp_dst = dst.with_suffix(".tmp")
            try:
                shutil.copy2(src, tmp_dst)
                os.replace(tmp_dst, dst)
            except Exception as e:
                if tmp_dst.exists():
                    tmp_dst.unlink(missing_ok=True)
                raise e

        try:
            atomic_replace(source_installer, target_installer)
            if source_cli.is_file():
                atomic_replace(source_cli, target_cli)
            print(f"[SUCCESS] 核心安裝器與起手腳本已成功自更新至 v{latest_ver} ➔ {target_installer}")
            return True
        except Exception as e:
            print(f"[ERROR] 自更新失敗: {e}")
            return False



# ── CLI 介面與指令分派 (CLI Interface & Dispatcher) ───────────────────────

def format_help_doc() -> str:
    return f"""
================================================================================
  YS-Codebase 管理工具庫 (yscb_installer.py) v{INSTALLER_VERSION}
================================================================================

【核心定位】
  YS-Codebase 專為個人獨立開發者與中小型專案打造的輕量、模組化工具庫管理系統。
  支援 2×2 設定協定、Core SDK (yscb_core) 與 Source/Build 雙軌安裝模式。

【指令一覽 (Commands)】
  1. init
     初始化當前目錄，建立 {CONFIG_FILENAME} 設定檔，綁定專案根目錄 (project_root) 與 YSCB 工具庫路徑 (yscb_root)。
     用法: python yscb_installer.py init [-p/--project-root <PATH>] [--repo <URL>] [--branch <BRANCH>] [--force]

  2. install
     安裝指定模組（預設為 build 發布產物安裝至 modules/；加上 --source 則安裝原始碼至 source/ 並自動相依 core）。
     用法: python yscb_installer.py install [<module> ...] [--source] [--force]

  3. pull / update
     從遠端中央庫拉取並同步最新模組。
     用法: python yscb_installer.py pull [<module> ...] [--source]

  4. build
     [開發者模式] 將 source/<module> 編譯/打包為 build/<module> 發布物。
     用法: python yscb_installer.py build [<module> ...] [--all]

  5. push
     [開發者模式] 提交並推送本地 source 與 build 變更回中央倉庫。
     用法: python yscb_installer.py push -m "<commit_message>" [--branch <BRANCH>]

  6. status
     檢視專案目前已安裝模組、模式 (source/build)、版本與狀態矩陣。
     用法: python yscb_installer.py status

  7. list
     列出本地或遠端所有可用模組與其支援模式。
     用法: python yscb_installer.py list [--remote]

  8. remove / uninstall
     移除已安裝之模組（具備相依安全保護）。
     用法: python yscb_installer.py remove <module> [--force]

  9. diff
     從遠端拉取最新 cache 後，逐檔比對本地已安裝模組與遠端版本之差異。
     用法: python yscb_installer.py diff [<module> ...]

 10. rollback
     自本地快照備份 (.yscb_cache/backup/) 還原模組至升級前狀態。
     用法: python yscb_installer.py rollback <module> [--list] [--to <備份名稱>]

 11. self-update
     自遠端或快取升級 installer 與統一 CLI 起手腳本（Windows 原子安全覆蓋）。
     用法: python yscb_installer.py self-update [--force]

 12. help
     顯示本說明文檔或特定子指令詳解。
     用法: python yscb_installer.py help [command]
================================================================================
"""

def main():
    parser = argparse.ArgumentParser(
        prog="python yscb_installer.py",
        description="YS-Codebase 核心模組化工具庫安裝管理系統",
        add_help=False
    )
    parser.add_argument("-h", "--help", action="store_true", help="顯示完整說明文檔")

    subparsers = parser.add_subparsers(dest="subcommand", title="子指令", description="支援的子指令列表")

    # 1. help
    help_parser = subparsers.add_parser("help", help="顯示詳細說明與指令手冊")
    help_parser.add_argument("topic", nargs="?", help="欲查詢的特定子指令名稱 (可選)")

    # 2. init
    init_parser = subparsers.add_parser("init", help="初始化專案設定檔")
    init_parser.add_argument("-p", "--project-root", default=".", help="專案根目錄之相對路徑（以 yscb 安裝目錄為基準，預設: .）")
    init_parser.add_argument("--repo", default=DEFAULT_REPO, help=f"中央遠端倉庫 URL (預設: {DEFAULT_REPO})")
    init_parser.add_argument("--branch", default=DEFAULT_BRANCH, help=f"追蹤分支 (預設: {DEFAULT_BRANCH})")
    init_parser.add_argument("--force", action="store_true", help="強制覆寫既有設定檔")

    # 3. install
    install_parser = subparsers.add_parser("install", help="安裝模組")
    install_parser.add_argument("modules", nargs="*", help="欲安裝的模組名稱（若未指定則安裝設定檔中宣告之模組）")
    install_parser.add_argument("--source", action="store_true", help="以源碼模式 (Source Mode) 安裝")
    install_parser.add_argument("--force", action="store_true", help="強制重新安裝並覆寫檔案")

    # 4. pull / update
    pull_parser = subparsers.add_parser("pull", aliases=["update"], help="拉取並更新模組")
    pull_parser.add_argument("modules", nargs="*", help="欲更新的模組名稱（預設為全部已安裝模組）")
    pull_parser.add_argument("--source", action="store_true", help="更新為源碼模式")
    pull_parser.add_argument("--all", action="store_true", help="明確指定更新全部已安裝模組（等同於未指定模組名稱）")

    # 5. build
    build_parser = subparsers.add_parser("build", help="編譯/建置源碼模組至 build/")
    build_parser.add_argument("modules", nargs="*", help="欲建置的模組名稱")
    build_parser.add_argument("--all", action="store_true", help="建置 source/ 下的所有可用模組")

    # 6. push
    push_parser = subparsers.add_parser("push", help="推送本地修改回中央倉庫")
    push_parser.add_argument("-m", "--message", required=True, help="Git Commit 提交訊息")
    push_parser.add_argument("--branch", help="目標推送分支 (預設採用設定檔分支)")

    # 7. status
    subparsers.add_parser("status", help="檢視模組安裝狀態")

    # 8. list
    list_parser = subparsers.add_parser("list", help="列出可用模組")
    list_parser.add_argument("--remote", action="store_true", help="自遠端倉庫重新掃描可用模組清單")

    # 9. remove / uninstall
    remove_parser = subparsers.add_parser("remove", aliases=["uninstall"], help="卸載模組")
    remove_parser.add_argument("module", help="欲移除的模組名稱")
    remove_parser.add_argument("--force", action="store_true", help="忽略相依安全警告強制移除")

    # 10. diff
    diff_parser = subparsers.add_parser("diff", help="比對本地已安裝模組與遠端最新版本差異")
    diff_parser.add_argument("modules", nargs="*", help="欲比對的模組名稱（預設為全部已安裝模組）")

    # 11. self-update
    self_update_parser = subparsers.add_parser("self-update", help="自遠端或快取升級 installer 與統一 CLI 起手腳本")
    self_update_parser.add_argument("--force", action="store_true", help="強制重新拉取覆蓋")

    # 12. rollback
    rollback_parser = subparsers.add_parser("rollback", help="自本地快照備份還原模組至升級前狀態")
    rollback_parser.add_argument("module", help="欲還原的模組名稱")
    rollback_parser.add_argument("--list", action="store_true", dest="list_only", help="僅列出可用快照備份清單")
    rollback_parser.add_argument("--to", dest="backup_name", help="指定還原的快照備份名稱（預設為最近一份）")


    args, unknown = parser.parse_known_args()

    if args.help or args.subcommand == "help" or not args.subcommand:
        if args.subcommand == "help" and getattr(args, "topic", None):
            topic = args.topic
            sub = subparsers.choices.get(topic)
            if sub:
                sub.print_help()
                return 0
            else:
                print(f"[WARN] 未知的子指令：'{topic}'")
        print(format_help_doc())
        return 0

    root_dir = Path.cwd()
    config_mgr = ConfigManager(root_dir)

    try:
        if args.subcommand == "init":
            cfg = config_mgr.create_default(
                repo=args.repo,
                branch=args.branch,
                project_root=args.project_root,
                force=args.force
            )
            proj_rel = cfg.get("paths", {}).get("project_root", ".")
            yscb_rel = cfg.get("paths", {}).get("yscb_root", ".")
            proj_abs = (root_dir / proj_rel).resolve()
            print(f"[SUCCESS] 已建立專案設定檔：{root_dir / CONFIG_FILENAME}")
            print(f"  • Project Root : {proj_rel} (絕對路徑: {proj_abs})")
            print(f"  • YSCB Root    : {yscb_rel} (相對於 Project Root)")
            print(f"  • Repo         : {cfg['remote']['repo']}")
            print(f"  • Branch       : {cfg['remote']['branch']}")
            return 0

        # 強制要求：非 init 指令必須先完成初始化
        if not config_mgr.exists():
            print(f"[ERROR] 尚未初始化專案設定檔 ({CONFIG_FILENAME})！", file=sys.stderr)
            print(f"提示：請先執行 'python yscb_installer.py init' 進行初始化（可透過 -p/--project-root 指定專案根目錄）。", file=sys.stderr)
            return 1

        cfg = config_mgr.load()
        remote_info = cfg.get("remote", {})
        git_client = GitRemoteClient(
            root_dir=root_dir,
            repo=remote_info.get("repo", DEFAULT_REPO),
            branch=remote_info.get("branch", DEFAULT_BRANCH)
        )
        module_mgr = ModuleManager(root_dir, config_mgr, git_client)

        if args.subcommand == "install":
            target_modules = args.modules
            mode = "source" if args.source else "build"

            if not target_modules:
                cfg_installed = cfg.get("installed_modules", {})
                if not cfg_installed:
                    print("[INFO] 未指定模組名稱，且 yscb_config.json 中無已安裝模組記錄。")
                    print("提示: 可執行 'python yscb_installer.py list' 檢視可用模組，或 'python yscb_installer.py install <module>'")
                    return 0
                target_modules = list(cfg_installed.keys())

            resolved_modules = module_mgr.resolve_dependencies(target_modules, is_source_mode=args.source)
            print(f"[PLAN] 安裝序列（含相依）: {' -> '.join(resolved_modules)}")

            changes = []
            for mod in resolved_modules:
                mod_mode = "source" if args.source else mode
                module_mgr.install_module(mod, mode=mod_mode, force=args.force)
                changes.append(("installed", mod))

            # 觸發批次全域收斂廣播
            module_mgr._broadcast_modules_changed(changes)
            print("[SUCCESS] 所有指定模組已順利安裝完成！")
            return 0

        elif args.subcommand in ("pull", "update"):
            mode = "source" if args.source else "build"
            git_client.sync_cache(force_refresh=True)
            installed = cfg.get("installed_modules", {})
            target_modules = args.modules or list(installed.keys())

            if not target_modules:
                print("[INFO] 目前無任何已安裝模組需要更新。")
                return 0

            changes = []
            for mod in target_modules:
                m_mode = installed.get(mod, {}).get("mode", mode)
                module_mgr.install_module(mod, mode=m_mode, force=True)
                changes.append(("updated", mod))

            # 觸發批次全域收斂廣播
            module_mgr._broadcast_modules_changed(changes)
            print("[SUCCESS] 模組更新同步完成！")
            return 0

        elif args.subcommand == "build":
            modules_to_build = args.modules
            if args.all or not modules_to_build:
                source_dir = module_mgr._get_source_dir(use_cache=False)
                if not source_dir.is_dir():
                    print("[WARN] 本地無 source/ 目錄，無模組可供建置。")
                    return 0
                modules_to_build = [d.name for d in source_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

            if not modules_to_build:
                print("[INFO] 無任何模組需要建置。")
                return 0

            # 解析相依性序列
            resolved_build_order = module_mgr.resolve_build_dependencies(modules_to_build)
            print(f"[BUILD-PLAN] 建置序列（含相依）: {' -> '.join(resolved_build_order)}")

            for mod in resolved_build_order:
                module_mgr.build_module(mod)
            print("[SUCCESS] 指定模組建置作業已全部完成！")
            return 0

        elif args.subcommand == "push":
            git_client.push_changes(commit_msg=args.message, branch=args.branch)
            return 0

        elif args.subcommand == "status":
            installed = cfg.get("installed_modules", {})
            print("\n" + "=" * 70)
            print(f"  YS-Codebase 模組安裝狀態報告 ({root_dir.name})")
            print("=" * 70)
            print(f"  遠端庫: {remote_info.get('repo', DEFAULT_REPO)} ({remote_info.get('branch', DEFAULT_BRANCH)})")
            print(f"  設定檔: {root_dir / CONFIG_FILENAME}")
            print("-" * 70)
            if not installed:
                print("  [!] 當前未安裝任何模組。")
            else:
                print(f"  {'模組名稱':<20} | {'安裝模式':<10} | {'版本':<10} | {'實體狀態':<10} | {'安裝時間'}")
                print("  " + "-" * 66)
                for mod, info in installed.items():
                    m_mode = info.get("mode", "build")
                    mod_dir = root_dir / ("source" if m_mode == "source" else "modules") / mod
                    dir_state = "[OK]" if mod_dir.is_dir() else "[MISSING]"
                    print(f"  {mod:<20} | {m_mode:<10} | {info.get('version', '1.0.0'):<10} | {dir_state:<10} | {info.get('installed_at', '-')}")
                if any(not (root_dir / ("source" if i.get("mode") == "source" else "modules") / m).is_dir() for m, i in installed.items()):
                    print("  " + "-" * 66)
                    print("  [!] 偵測到 [MISSING] 孤兒紀錄：模組目錄已不存在。可執行 'install <module> --force' 重新安裝或 'remove <module>' 清除紀錄。")
            print("=" * 70 + "\n")
            return 0

        elif args.subcommand == "list":
            modules = module_mgr.discover_modules(from_remote=args.remote)
            installed = cfg.get("installed_modules", {})

            print("\n" + "=" * 75)
            print(f"  可用模組清單 {'(來源: 遠端庫)' if args.remote else '(來源: 本地/快取)'}")
            print("=" * 75)
            if not modules:
                print("  [!] 未掃描到任何可用模組。可嘗試執行 'python yscb_installer.py list --remote'")
            else:
                print(f"  {'模組名稱':<20} | {'支援模式':<16} | {'已安裝':<8} | {'描述'}")
                print("  " + "-" * 71)
                for mod_name, info in modules.items():
                    modes = []
                    if info.get("has_source"): modes.append("source")
                    if info.get("has_build"): modes.append("build")
                    mode_str = "/".join(modes) if modes else "-"
                    is_inst = "[V]" if mod_name in installed else "[ ]"
                    desc = info.get("meta", {}).get("description", "")
                    print(f"  {mod_name:<20} | {mode_str:<16} | {is_inst:<8} | {desc}")
            print("=" * 75 + "\n")
            return 0

        elif args.subcommand in ("remove", "uninstall"):
            if module_mgr.remove_module(args.module, force=args.force):
                # 觸發批次全域收斂廣播
                module_mgr._broadcast_modules_changed([("removed", args.module)])
            return 0


        elif args.subcommand == "diff":
            module_mgr.diff_modules(args.modules)
            return 0

        elif args.subcommand in ["self-update", "self_update", "upgrade-self"]:
            success = module_mgr.self_update(force=args.force)
            return 0 if success else 1

        elif args.subcommand == "rollback":
            success = module_mgr.rollback_module(
                args.module,
                list_only=args.list_only,
                backup_name=args.backup_name
            )
            return 0 if success else 1


    except Exception as e:
        if os.environ.get("YSCB_DEBUG"):
            import traceback
            traceback.print_exc()
        print(f"\n[ERROR] 執行失敗: {type(e).__name__}: {e}", file=sys.stderr)
        print("(提示: 設定環境變數 YSCB_DEBUG=1 可顯示完整錯誤堆疊)\n", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
