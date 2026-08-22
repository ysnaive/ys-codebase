#!/usr/bin/env python3
"""
yscb_installer.py — YS-Codebase 核心模組化工具庫安裝管理系統 (v2.0)

核心特性：
  - 純 Python 3 標準庫實現，Zero External Dependency
  - 支援 Source (源碼/開發者模式) 與 Build (發布物/使用者模式) 雙軌安裝
  - 源碼模式強制自動連動相依 source/core 基礎基座
  - 提供完整 CLI 工具鏈 (help, init, install, pull, build, push, status, list, remove)
"""

import sys
import os
import shutil
import subprocess
import json
import argparse
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

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
TEMPLATE_CONFIG_FILENAME = "yscb_config.template.json"
CACHE_DIRNAME = ".yscb_cache"
INSTALLER_VERSION = "2.0.0"


# ── 配置管理 (Config Manager) ───────────────────────────────────────────
class ConfigManager:
    """管理 yscb_config.json 的讀寫、驗證與更新"""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.config_path = root_dir / CONFIG_FILENAME
        self.template_path = root_dir / TEMPLATE_CONFIG_FILENAME

    def exists(self) -> bool:
        return self.config_path.exists()

    def create_default(self, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH, force: bool = False) -> Dict[str, Any]:
        if self.exists() and not force:
            raise FileExistsError(f"設定檔已存在：{self.config_path}。若需重新初始化請加上 --force。")

        if self.template_path.exists():
            try:
                with open(self.template_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                if "remote" not in config:
                    config["remote"] = {}
                config["remote"]["repo"] = repo
                config["remote"]["branch"] = branch
                self.save(config)
                return config
            except Exception as e:
                print(f"[WARN] 讀取模板檔 {TEMPLATE_CONFIG_FILENAME} 失敗: {e}，改用內建預設值。")

        config = {
            "version": "2.0",
            "remote": {
                "repo": repo,
                "branch": branch
            },
            "installed_modules": {},
            "custom_settings": {}
        }
        self.save(config)
        return config

    def load(self) -> Dict[str, Any]:
        if not self.exists():
            return {
                "version": "2.0",
                "remote": {
                    "repo": DEFAULT_REPO,
                    "branch": DEFAULT_BRANCH
                },
                "installed_modules": {},
                "custom_settings": {}
            }
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 讀取 {CONFIG_FILENAME} 失敗: {e}，回退至預設配置。")
            return {
                "version": "2.0",
                "remote": {
                    "repo": DEFAULT_REPO,
                    "branch": DEFAULT_BRANCH
                },
                "installed_modules": {},
                "custom_settings": {}
            }

    def save(self, config: Dict[str, Any]):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def record_installed_module(self, module_name: str, mode: str, version: str = "1.0.0", meta: Optional[Dict[str, Any]] = None):
        cfg = self.load()
        if "installed_modules" not in cfg:
            cfg["installed_modules"] = {}
        
        module_info = {
            "mode": mode,
            "version": version,
            "installed_at": datetime.datetime.now().isoformat(timespec="seconds")
        }
        if meta:
            module_info.update(meta)
        cfg["installed_modules"][module_name] = module_info
        self.save(cfg)

    def remove_installed_module(self, module_name: str):
        cfg = self.load()
        if "installed_modules" in cfg and module_name in cfg["installed_modules"]:
            del cfg["installed_modules"][module_name]
            self.save(cfg)


# ── Git 與遠端同步客戶端 (Git Remote Client) ─────────────────────────────
class GitRemoteClient:
    """管理與遠端中央標準庫的快取、拉取與推送"""

    def __init__(self, root_dir: Path, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH):
        self.root_dir = root_dir
        self.repo = repo
        self.branch = branch
        self.cache_dir = root_dir / CACHE_DIRNAME

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(cwd or self.root_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            return res
        except FileNotFoundError:
            raise RuntimeError("系統中未找到 git 命令，請確認已安裝 Git 並已加入系統 PATH。")

    def is_git_available(self) -> bool:
        try:
            res = self._run_git(["--version"])
            return res.returncode == 0
        except Exception:
            return False

    def sync_cache(self, force_refresh: bool = False) -> Path:
        """確保本機快取目錄存在並同步至最新遠端狀態"""
        if not self.is_git_available():
            raise RuntimeError("Git 未安裝或無法執行，無法同步遠端倉庫。")

        if not (self.cache_dir / ".git").exists():
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir, ignore_errors=True)
            print(f"[INFO] 正在複製遠端庫至快取: {self.repo} ({self.branch})...")
            res = self._run_git(["clone", "--depth", "1", "-b", self.branch, self.repo, str(self.cache_dir)])
            if res.returncode != 0:
                raise RuntimeError(f"Clone 失敗: {res.stderr.strip()}")
            print("[INFO] 遠端庫快取初始化完成。")
        else:
            if force_refresh:
                print(f"[INFO] 正在更新快取至最新 {self.branch} 分支...")
                res = self._run_git(["fetch", "origin", self.branch], cwd=self.cache_dir)
                if res.returncode != 0:
                    print(f"[WARN] Fetch 失敗: {res.stderr.strip()}")
                else:
                    self._run_git(["reset", "--hard", f"origin/{self.branch}"], cwd=self.cache_dir)
                    print("[INFO] 快取更新完成。")
        return self.cache_dir

    def push_changes(self, commit_msg: str, branch: Optional[str] = None) -> bool:
        """推送修改回遠端庫"""
        target_branch = branch or self.branch
        print(f"[INFO] 準備推送修改至 {self.repo} ({target_branch})...")
        
        # 檢查工作目錄是否有 git
        if not (self.root_dir / ".git").exists():
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

    def _get_source_dir(self, use_cache: bool = False) -> Path:
        local_source = self.root_dir / "source"
        if local_source.is_dir() and not use_cache:
            return local_source
        cache_source = self.git_client.cache_dir / "source"
        if cache_source.is_dir():
            return cache_source
        return local_source

    def _get_build_dir(self, use_cache: bool = False) -> Path:
        local_build = self.root_dir / "build"
        if local_build.is_dir() and not use_cache:
            return local_build
        cache_build = self.git_client.cache_dir / "build"
        if cache_build.is_dir():
            return cache_build
        return local_build

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

    def resolve_dependencies(self, module_names: List[str], is_source_mode: bool) -> List[str]:
        """解析相依性，確保以正確順序安裝，並在 --source 模式下強制補齊 core"""
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
                visit(dep)

            resolved.append(name)

        for m in module_names:
            visit(m)

        # 在源碼模式下，若安裝任何模組且不是純 core，必須強制引入 core 作為首個底層相依
        if is_source_mode:
            if "core" not in resolved:
                resolved.insert(0, "core")
            else:
                resolved.remove("core")
                resolved.insert(0, "core")

        return resolved

    def resolve_build_dependencies(self, module_names: List[str]) -> List[str]:
        """解析建置相依性，確保以正確順序建置所有相依模組（自動排除無需 build 的 core）"""
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
                if dep != "core":
                    visit(dep)

            if name != "core":
                resolved.append(name)

        for m in module_names:
            visit(m)

        return resolved

    def _locate_module_dir(self, module_name: str, mode: str) -> Optional[Path]:
        """定位模組來源目錄（本地優先，其次快取）"""
        target_sub = "source" if mode == "source" else "build"
        
        # 1. 本地目錄
        local_path = self.root_dir / target_sub / module_name
        if local_path.is_dir():
            return local_path

        # 2. 快取目錄
        cache_path = self.git_client.cache_dir / target_sub / module_name
        if cache_path.is_dir():
            return cache_path

        return None

    def install_module(self, module_name: str, mode: str = "build", force: bool = False) -> bool:
        """執行單個模組的複製與安裝註冊"""
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

        if mode == "source":
            dest_path = self.root_dir / "source" / module_name
        else:
            dest_path = self.root_dir / "modules" / module_name

        if dest_path.exists():
            if not force and dest_path.resolve() == src_path.resolve():
                print(f"[INFO] 模組 '{module_name}' 已存在於本地 ({dest_path})，跳過本體覆寫。")
            else:
                shutil.rmtree(dest_path, ignore_errors=True)
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_path, dest_path, dirs_exist_ok=True)

        self.config_mgr.record_installed_module(
            module_name=module_name,
            mode=mode,
            version=version,
            meta={"description": manifest.get("description", "")}
        )
        print(f"[SUCCESS] 模組 '{module_name}' ({mode} v{version}) 安裝完成 ➔ {dest_path}")

        # 執行 _installed.py Hook
        installed_hook = dest_path / "scripts" / "_installed.py"
        if installed_hook.is_file():
            print(f"[HOOK] 執行 '{module_name}' 安裝後置 Hook: {installed_hook.name}...")
            try:
                res = subprocess.run([sys.executable, str(installed_hook), str(dest_path), mode], cwd=str(dest_path))
                if res.returncode != 0:
                    print(f"[WARN] Hook _installed.py 執行返回非 0 狀態碼: {res.returncode}")
            except Exception as e:
                print(f"[WARN] 呼叫 _installed.py Hook 失敗: {e}")

        return True

    def remove_module(self, module_name: str, force: bool = False) -> bool:
        """卸載指定模組，並進行相依安全性檢查與 _uninstall.py Hook 調用"""
        cfg = self.config_mgr.load()
        installed = cfg.get("installed_modules", {})

        if module_name not in installed:
            print(f"[WARN] 模組 '{module_name}' 尚未安裝。")
            return False

        if not force:
            for other_mod, info in installed.items():
                if other_mod == module_name:
                    continue
                if module_name == "core" and info.get("mode") == "source":
                    raise RuntimeError(f"無法移除 'core'：模組 '{other_mod}' 處於 source 模式並相依於 core。若需強制移除請加 --force。")

        mod_info = installed[module_name]
        mode = mod_info.get("mode", "build")
        target_dir = self.root_dir / ("source" if mode == "source" else "modules") / module_name

        if target_dir.exists():
            # 執行 _uninstall.py Hook
            uninstall_hook = target_dir / "scripts" / "_uninstall.py"
            if uninstall_hook.is_file():
                print(f"[HOOK] 執行 '{module_name}' 卸載前置 Hook: {uninstall_hook.name}...")
                try:
                    res = subprocess.run([sys.executable, str(uninstall_hook), str(target_dir), mode], cwd=str(target_dir))
                    if res.returncode != 0:
                        print(f"[WARN] Hook _uninstall.py 執行返回非 0 狀態碼: {res.returncode}")
                except Exception as e:
                    print(f"[WARN] 呼叫 _uninstall.py Hook 失敗: {e}")

            shutil.rmtree(target_dir, ignore_errors=True)
            print(f"[INFO] 已清理模組目錄：{target_dir}")

        self.config_mgr.remove_installed_module(module_name)
        print(f"[SUCCESS] 模組 '{module_name}' 已成功移除。")
        return True

    def build_module(self, module_name: str) -> bool:
        """將 source/<module> 編譯/建置為 build/<module>"""
        if module_name == "core":
            print("[INFO] 'core' 為基礎庫，無需生成 build 產出物。")
            return True

        src_path = self.root_dir / "source" / module_name
        if not src_path.is_dir():
            raise FileNotFoundError(f"找不到源碼目錄：{src_path}，無法執行 build。")

        dest_path = self.root_dir / "build" / module_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = self.read_manifest(src_path)

        custom_build_script = src_path / "build.py"
        if custom_build_script.is_file():
            print(f"[BUILD] 執行 '{module_name}' 自訂建置腳本：{custom_build_script}...")
            res = subprocess.run([sys.executable, str(custom_build_script), str(src_path), str(dest_path)], cwd=str(src_path))
            if res.returncode != 0:
                raise RuntimeError(f"模組 '{module_name}' 自訂建置失敗 (Exit {res.returncode})。")
        else:
            print(f"[BUILD] 使用標準管線將 '{module_name}' 封裝至 {dest_path}...")
            if dest_path.exists():
                shutil.rmtree(dest_path, ignore_errors=True)
            
            custom_excludes = manifest.get("build_exclude", [])

            def ignore_dev_files(folder, files):
                ignored = []
                for f in files:
                    # 預設排除規則（發布物僅包含最低執行需求，排除開發檔案與運行期設定 config.json）
                    if f in [".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "tests", "scratch", ".vscode", ".idea", "build.py", "config.json"]:
                        ignored.append(f)
                    elif f.endswith(".pyc") or f.endswith(".pyo") or f.endswith(".pyd"):
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


# ── CLI 介面與指令分派 (CLI Interface & Dispatcher) ───────────────────────

def format_help_doc() -> str:
    return f"""
================================================================================
  YS-Codebase 管理工具庫 (yscb_installer.py) v{INSTALLER_VERSION}
================================================================================

【核心定位】
  YS-Codebase 專為個人獨立開發者與中小型專案打造的輕量、模組化工具庫管理系統。
  支援 Source (源碼/開發者) 與 Build (發布物/使用者) 雙軌安裝模式。

【指令一覽 (Commands)】
  1. init
     初始化當前目錄，建立 {CONFIG_FILENAME} 設定檔。
     用法: python yscb_installer.py init [--repo <URL>] [--branch <BRANCH>] [--force]

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

  9. help
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
    init_parser.add_argument("--repo", default=DEFAULT_REPO, help=f"中央遠端倉庫 URL (預設: {DEFAULT_REPO})")
    init_parser.add_argument("--branch", default=DEFAULT_BRANCH, help=f"追蹤分支 (預設: {DEFAULT_BRANCH})")
    init_parser.add_argument("--force", action="store_true", help="強制覆寫既有設定檔")

    # 3. install
    install_parser = subparsers.add_parser("install", help="安裝模組")
    install_parser.add_argument("modules", nargs="*", help="欲安裝的模組名稱（若未指定則安裝設定檔中宣告之模組）")
    install_parser.add_argument("--source", action="store_true", help="以源碼模式 (Source Mode) 安裝（自動連動相依 core）")
    install_parser.add_argument("--force", action="store_true", help="強制重新安裝並覆寫檔案")

    # 4. pull / update
    pull_parser = subparsers.add_parser("pull", help="拉取並更新模組")
    pull_parser.add_argument("modules", nargs="*", help="欲更新的模組名稱（預設為全部已安裝模組）")
    pull_parser.add_argument("--source", action="store_true", help="更新為源碼模式")

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

    # 9. remove
    remove_parser = subparsers.add_parser("remove", help="卸載模組")
    remove_parser.add_argument("module", help="欲移除的模組名稱")
    remove_parser.add_argument("--force", action="store_true", help="忽略相依安全警告強制移除")

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
    cfg = config_mgr.load()
    remote_info = cfg.get("remote", {})
    git_client = GitRemoteClient(
        root_dir=root_dir,
        repo=remote_info.get("repo", DEFAULT_REPO),
        branch=remote_info.get("branch", DEFAULT_BRANCH)
    )
    module_mgr = ModuleManager(root_dir, config_mgr, git_client)

    try:
        if args.subcommand == "init":
            cfg = config_mgr.create_default(repo=args.repo, branch=args.branch, force=args.force)
            print(f"[SUCCESS] 已建立專案設定檔：{root_dir / CONFIG_FILENAME}")
            print(f"  • Repo  : {cfg['remote']['repo']}")
            print(f"  • Branch: {cfg['remote']['branch']}")
            return 0

        elif args.subcommand == "install":
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

            for mod in resolved_modules:
                mod_mode = "source" if (args.source or mod == "core") else mode
                module_mgr.install_module(mod, mode=mod_mode, force=args.force)
            print("[SUCCESS] 所有指定模組已順利安裝完成！")
            return 0

        elif args.subcommand == "pull":
            mode = "source" if args.source else "build"
            git_client.sync_cache(force_refresh=True)
            installed = cfg.get("installed_modules", {})
            target_modules = args.modules or list(installed.keys())

            if not target_modules:
                print("[INFO] 目前無任何已安裝模組需要更新。")
                return 0

            for mod in target_modules:
                m_mode = installed.get(mod, {}).get("mode", mode)
                module_mgr.install_module(mod, mode=m_mode, force=True)
            print("[SUCCESS] 模組更新同步完成！")
            return 0

        elif args.subcommand == "build":
            modules_to_build = args.modules
            if args.all or not modules_to_build:
                source_dir = root_dir / "source"
                if not source_dir.is_dir():
                    print("[WARN] 本地無 source/ 目錄，無模組可供建置。")
                    return 0
                modules_to_build = [d.name for d in source_dir.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name != "core"]

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
                print(f"  {'模組名稱':<20} | {'安裝模式':<10} | {'版本':<10} | {'安裝時間'}")
                print("  " + "-" * 66)
                for mod, info in installed.items():
                    print(f"  {mod:<20} | {info.get('mode', 'build'):<10} | {info.get('version', '1.0.0'):<10} | {info.get('installed_at', '-')}")
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

        elif args.subcommand == "remove":
            module_mgr.remove_module(args.module, force=args.force)
            return 0

    except Exception as e:
        print(f"\n[ERROR] 執行失敗: {e}\n", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
