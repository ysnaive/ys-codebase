"""
YS-Codebase Private Virtual Environment (PipManager) SDK.
100% Python Standard Library, Zero Third-Party Dependency.
Manages private venv at yscb.venv:// (yscb://.venv/), version-partitioned per Python version,
enforcing Wheel-Only quiet installation and total isolation from host environment.
"""

import os
import shutil
import sys
import venv
import platform
import subprocess
from contextlib import contextmanager
from typing import Optional, List, Any, Generator
from core import uri, vfs
from core.installer import generate_internal_gitignore
from core.platform.lock import InterProcessLock


def ensure_yscb_gitignore(yscb_dir: str) -> None:
    """
    確保 yscb_dir/.gitignore 存在且包含 YSCB 內部忽略區塊。
    直接委派至 core.installer.generate_internal_gitignore 單一正統實作。
    """
    generate_internal_gitignore(yscb_dir)


class PipInstallError(RuntimeError):
    """當私有微環境調用 pip 安裝失敗時拋出之結構化異常。"""
    def __init__(self, message: str, returncode: int = 1, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class PipManager:
    """YSCB 私有微虛擬環境管理器：管理 yscb.venv://，實施版本分層與 Wheel-Only 剛性安全安裝。"""

    def __init__(self, yscb_dir: Optional[str] = None):
        self.yscb_dir = os.path.abspath(yscb_dir or self._resolve_yscb_root())
        self._held_lock: Optional[InterProcessLock] = None

    def _resolve_yscb_root(self) -> str:
        """解析當前 yscb_root 目錄，統一委派至 core.uri.resolve_yscb_root()。"""
        return uri.resolve_yscb_root()

    @staticmethod
    def parse_pip_dependencies(pip_deps: Any) -> List[str]:
        """
        將 manifest.json 中的 pip_dependencies 宣告正規化為合法的 pip 規格字串清單。
        支援輸入格式：
          1. 字典格式：{"pkg": ">=1.0.0", "pkg2": ""} -> ["pkg>=1.0.0", "pkg2"]
          2. 清單格式：["pkg>=1.0.0", "pkg2"] -> ["pkg>=1.0.0", "pkg2"]
        行為保證：
          - 輸入 None、非字典非清單或空結構時安全回傳 []
          - 自動去除首尾空白，過濾空字串與無效項目
          - 保持首次出現順序之去重 (Order-preserving deduplication)
        """
        if not pip_deps:
            return []

        specs: List[str] = []
        if isinstance(pip_deps, dict):
            for pkg, constraint in pip_deps.items():
                if not pkg or not str(pkg).strip():
                    continue
                pkg_clean = str(pkg).strip()
                if constraint is not None and str(constraint).strip():
                    spec = f"{pkg_clean}{str(constraint).strip()}"
                else:
                    spec = pkg_clean
                specs.append(spec)
        elif isinstance(pip_deps, list):
            for item in pip_deps:
                if item is not None and str(item).strip():
                    specs.append(str(item).strip())

        seen = set()
        deduped: List[str] = []
        for s in specs:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        return deduped

    @staticmethod
    def get_current_py_tag() -> str:
        """回傳當前直譯器的大/小版本標籤，例如 'py310' 或 'py311'。"""
        return f"py{sys.version_info.major}{sys.version_info.minor}"

    def _resolve_py_ver_dirname(self, py_tag: Optional[str] = None) -> str:
        """解析對應 Python 版本目錄名稱（如 'python3.11'）。"""
        tag = py_tag or self.get_current_py_tag()
        if tag.startswith("py") and len(tag) >= 4:
            major = tag[2]
            minor = tag[3:]
            return f"python{major}.{minor}"
        return f"python{sys.version_info.major}.{sys.version_info.minor}"

    def get_venv_dir(self, py_tag: Optional[str] = None) -> str:
        """取得特定 Python 版本標籤之微環境根目錄 (yscb_dir/.venv/py{ver})。"""
        tag = py_tag or self.get_current_py_tag()
        return os.path.join(self.yscb_dir, ".venv", tag)

    def get_python_executable(self, py_tag: Optional[str] = None) -> str:
        """跨平台取得微環境 Python 可執行檔絕對路徑 (POSIX: bin/python, Windows: Scripts/python.exe)。"""
        venv_dir = self.get_venv_dir(py_tag)
        if platform.system() == "Windows":
            return os.path.join(venv_dir, "Scripts", "python.exe")
        return os.path.join(venv_dir, "bin", "python")

    def get_site_packages_dir(self, py_tag: Optional[str] = None) -> str:
        """跨平台取得微環境 site-packages 絕對路徑。"""
        venv_dir = self.get_venv_dir(py_tag)
        if platform.system() == "Windows":
            return os.path.join(venv_dir, "Lib", "site-packages")
        py_ver = self._resolve_py_ver_dirname(py_tag)
        return os.path.join(venv_dir, "lib", py_ver, "site-packages")

    def get_cross_platform_site_packages_dirs(self, py_tag: Optional[str] = None) -> List[str]:
        """跨平台取得微環境 site-packages 雙平台候選路徑集合 (POSIX + Windows)。

        回傳清單順序恆定 (POSIX 優先，次為 Windows)。
        """
        venv_dir = self.get_venv_dir(py_tag)
        py_ver = self._resolve_py_ver_dirname(py_tag)
        posix_path = os.path.join(venv_dir, "lib", py_ver, "site-packages")
        win_path = os.path.join(venv_dir, "Lib", "site-packages")
        return [posix_path, win_path]

    @staticmethod
    def _can_symlink(dir_path: str) -> bool:
        """檢測目標目錄是否支援有效符號連結 (相容 virtiofs / 跨平台掛載環境)。"""
        if platform.system() == "Windows":
            return False
        test_p = os.path.join(dir_path, f".symlink_probe_{os.getpid()}")
        try:
            if os.path.lexists(test_p):
                os.remove(test_p)
            os.symlink(sys.executable, test_p)
            can_resolve = os.path.exists(test_p)
            os.remove(test_p)
            return can_resolve
        except Exception:
            return False

    @staticmethod
    def _try_copy_host_pip_to_site_packages(site_pkg: str) -> bool:
        """
        When offline containers lack `ensurepip` wheels, falls back to copying the host
        system `pip` package directory (and matching `pip-*.dist-info` if present) into `site_pkg`.
        """
        try:
            import importlib.util

            spec = importlib.util.find_spec("pip")
            if spec is None or not spec.submodule_search_locations:
                return False
            host_pip_dir = os.path.abspath(list(spec.submodule_search_locations)[0])
            if not os.path.isdir(host_pip_dir):
                return False
            dst_pip_dir = os.path.join(site_pkg, "pip")
            if os.path.abspath(dst_pip_dir) == host_pip_dir:
                return True
            if os.path.exists(dst_pip_dir):
                shutil.rmtree(dst_pip_dir, ignore_errors=True)
            shutil.copytree(
                host_pip_dir,
                dst_pip_dir,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            parent_site = os.path.dirname(host_pip_dir)
            if os.path.isdir(parent_site):
                for entry in os.listdir(parent_site):
                    if entry.startswith("pip-") and entry.endswith(".dist-info"):
                        src_dist = os.path.join(parent_site, entry)
                        dst_dist = os.path.join(site_pkg, entry)
                        if os.path.isdir(src_dist) and not os.path.exists(dst_dist):
                            shutil.copytree(src_dist, dst_dist)
            return os.path.isdir(dst_pip_dir)
        except Exception:
            return False

    def _bootstrap_pip(self, venv_dir: str, site_pkg: str, py_exec: str) -> None:
        """為微環境就緒 pip 套件：優先自 ensurepip 提取預置 wheel，次之複製宿主環境 pip，最後呼叫 ensurepip。"""
        import zipfile
        os.makedirs(site_pkg, exist_ok=True)
        # 優先方案 1：自 ensurepip._WHEEL_PKG_DIR 提取 pip*.whl，零 subprocess 權限阻礙
        candidate_wheel_dirs = []
        try:
            import ensurepip
            pkg_dir = getattr(ensurepip, "_WHEEL_PKG_DIR", None)
            if isinstance(pkg_dir, str) and pkg_dir:
                candidate_wheel_dirs.append(pkg_dir)
            else:
                bundled_dir = os.path.join(os.path.dirname(ensurepip.__file__), "_bundled")
                candidate_wheel_dirs.append(bundled_dir)
                candidate_wheel_dirs.append("/usr/share/python-wheels")
        except Exception:
            pass

        for wheel_dir in candidate_wheel_dirs:
            try:
                if isinstance(wheel_dir, str) and os.path.isdir(wheel_dir):
                    for fname in sorted(os.listdir(wheel_dir), reverse=True):
                        if fname.startswith("pip-") and fname.endswith(".whl"):
                            whl_path = os.path.join(wheel_dir, fname)
                            with zipfile.ZipFile(whl_path, "r") as zf:
                                zf.extractall(site_pkg)
                            return
            except Exception:
                continue

        # 優先方案 2：若實機微環境已建立 (py_exec 存在) 但離線容器缺少 ensurepip wheel，嘗試複製宿主 pip 套件目錄
        if os.path.isfile(py_exec) and sys.modules.get("ensurepip", True) is not None:
            if self._try_copy_host_pip_to_site_packages(site_pkg):
                return

        # 次選方案 3：呼叫 python -m ensurepip
        try:
            subprocess.run(
                [py_exec, "-m", "ensurepip", "--default-pip"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=300,
            )
        except Exception as e:
            raise PipInstallError(
                f"[PipManager] Failed to bootstrap pip into '{venv_dir}': {e}"
            ) from e

    def get_lock_file(self) -> str:
        """回傳私有微環境跨進程安裝排他鎖檔案路徑 (yscb_dir/.venv/.pip_install.lock)。"""
        venv_root = os.path.join(self.yscb_dir, ".venv")
        os.makedirs(venv_root, exist_ok=True)
        return os.path.join(venv_root, ".pip_install.lock")

    @contextmanager
    def _pip_lock(self) -> Generator[None, None, None]:
        """可重入跨進程微環境排他鎖上下文管理器。"""
        held = getattr(self, "_held_lock", None)
        if held is not None and held.is_locked:
            yield
            return
        lock = InterProcessLock(self.get_lock_file())
        with lock:
            self._held_lock = lock
            try:
                yield
            finally:
                self._held_lock = None

    def ensure_venv(self, py_tag: Optional[str] = None) -> str:
        """
        若微環境不存在則以純 Python 標準庫 venv 建立。
        保證 include-system-site-packages = false，達成 100% 零全域污染。
        相容 virtiofs / 容器掛載磁碟，自動探測 symlink 有效性並安全注入 pip。
        """
        venv_dir = self.get_venv_dir(py_tag)
        py_exec = self.get_python_executable(py_tag)
        site_pkg = self.get_site_packages_dir(py_tag)

        with self._pip_lock():
            pip_ready = False
            if os.path.isfile(py_exec) and os.path.isdir(site_pkg):
                if os.path.isdir(os.path.join(site_pkg, "pip")):
                    pip_ready = True

            if not os.path.isfile(py_exec) or not pip_ready:
                os.makedirs(venv_dir, exist_ok=True)
                try:
                    symlinks_ok = self._can_symlink(venv_dir)
                    if not symlinks_ok and os.name == "posix" and sys.platform != "darwin":
                        lib64_dir = os.path.join(venv_dir, "lib64")
                        if not os.path.exists(lib64_dir):
                            os.makedirs(lib64_dir, exist_ok=True)
                    builder = venv.EnvBuilder(
                        with_pip=False,
                        clear=False,
                        symlinks=symlinks_ok,
                    )
                    builder.create(venv_dir)
                    self._bootstrap_pip(venv_dir, site_pkg, py_exec)
                except Exception as e:
                    if isinstance(e, PipInstallError):
                        raise
                    raise PipInstallError(
                        f"[PipManager] Failed to create private venv at '{venv_dir}'. "
                        f"Please ensure python3-venv / ensurepip is installed. Details: {e}"
                    ) from e

            # 驗證並加固 pyvenv.cfg
            cfg_path = os.path.join(venv_dir, "pyvenv.cfg")
            if vfs.is_file(cfg_path):
                try:
                    content = vfs.read_text(cfg_path)
                    if "include-system-site-packages = true" in content:
                        content = content.replace(
                            "include-system-site-packages = true",
                            "include-system-site-packages = false",
                        )
                        vfs.write_text(cfg_path, content, atomic=True)
                except Exception:
                    pass

            # 確保 yscb_dir/.gitignore 包含 /.venv/ 內部忽略標記
            self._ensure_gitignore()

        return venv_dir

    def _ensure_gitignore(self) -> None:
        """確保 yscb_dir/.gitignore 存在且包含 /.venv/ 內部忽略規則。"""
        ensure_yscb_gitignore(self.yscb_dir)

    def install_packages(self, specs: List[str], py_tag: Optional[str] = None) -> None:
        """
        調用微環境之 python -m pip 執行 Wheel-Only 靜默安裝。
        強制附加參數: ['install', '--only-binary=:all:', '--no-warn-script-location', '--quiet', *specs]
        """
        if not specs:
            return

        with self._pip_lock():
            self.ensure_venv(py_tag)
            py_exec = self.get_python_executable(py_tag)

            cmd = [
                py_exec,
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "--no-warn-script-location",
                "--no-input",
                "--retries=1",
                "--timeout=5",
                "--quiet",
                *specs,
            ]

            try:
                res = subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=300,
                )
            except Exception as e:
                raise PipInstallError(f"Failed to execute pip command: {e}") from e

            if res.returncode != 0:
                err_msg = res.stderr.strip() or res.stdout.strip()
                raise PipInstallError(
                    f"[PipManager] Wheel-Only installation failed for {specs}:\n{err_msg}",
                    returncode=res.returncode,
                    stdout=res.stdout,
                    stderr=res.stderr,
                )
