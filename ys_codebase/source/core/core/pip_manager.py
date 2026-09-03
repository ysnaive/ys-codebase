"""
YS-Codebase Private Virtual Environment (PipManager) SDK.
100% Python Standard Library, Zero Third-Party Dependency.
Manages private venv at yscb.venv:// (yscb://.venv/), version-partitioned per Python version,
enforcing Wheel-Only quiet installation and total isolation from host environment.
"""

import os
import sys
import venv
import platform
import subprocess
from typing import Optional, List, Dict, Any


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

    def _resolve_yscb_root(self) -> str:
        """解析當前 yscb_root 目錄。"""
        # 若當前模組在 ys_codebase/source/core/core/ 下，向上尋找 yscb.config.json 或使用上兩層
        cur = os.path.abspath(os.path.dirname(__file__))
        while cur and cur != os.path.dirname(cur):
            cfg_p = os.path.join(cur, "yscb.config.json")
            if os.path.isfile(cfg_p):
                return cur
            cur = os.path.dirname(cur)
        # 兜底回當前工作目錄
        return os.getcwd()

    @staticmethod
    def get_current_py_tag() -> str:
        """回傳當前直譯器的大/小版本標籤，例如 'py310' 或 'py311'。"""
        return f"py{sys.version_info.major}{sys.version_info.minor}"

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
        
        tag = py_tag or self.get_current_py_tag()
        if tag.startswith("py") and len(tag) >= 4:
            major = tag[2]
            minor = tag[3:]
            py_ver = f"python{major}.{minor}"
        else:
            py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
        return os.path.join(venv_dir, "lib", py_ver, "site-packages")

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

    def _bootstrap_pip(self, venv_dir: str, site_pkg: str, py_exec: str) -> None:
        """為微環境就緒 pip 套件：優先自 ensurepip 提取預置 wheel，次之呼叫 ensurepip。"""
        import zipfile
        os.makedirs(site_pkg, exist_ok=True)
        # 優先方案：自 ensurepip._WHEEL_PKG_DIR 提取 pip*.whl，零 subprocess 權限阻礙
        try:
            import ensurepip
            wheel_dir = getattr(ensurepip, "_WHEEL_PKG_DIR", "/usr/share/python-wheels")
            if os.path.isdir(wheel_dir):
                for fname in os.listdir(wheel_dir):
                    if fname.startswith("pip-") and fname.endswith(".whl"):
                        whl_path = os.path.join(wheel_dir, fname)
                        with zipfile.ZipFile(whl_path, "r") as zf:
                            zf.extractall(site_pkg)
                        return
        except Exception:
            pass

        # 次選方案：呼叫 python -m ensurepip
        try:
            subprocess.run(
                [py_exec, "-m", "ensurepip", "--default-pip"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"[PipManager] Failed to bootstrap pip into '{venv_dir}': {e}"
            ) from e

    def ensure_venv(self, py_tag: Optional[str] = None) -> str:
        """
        若微環境不存在則以純 Python 標準庫 venv 建立。
        保證 include-system-site-packages = false，達成 100% 零全域污染。
        相容 virtiofs / 容器掛載磁碟，自動探測 symlink 有效性並安全注入 pip。
        """
        venv_dir = self.get_venv_dir(py_tag)
        py_exec = self.get_python_executable(py_tag)
        site_pkg = self.get_site_packages_dir(py_tag)

        pip_ready = False
        if os.path.isfile(py_exec) and os.path.isdir(site_pkg):
            if os.path.isdir(os.path.join(site_pkg, "pip")):
                pip_ready = True

        if not os.path.isfile(py_exec) or not pip_ready:
            os.makedirs(venv_dir, exist_ok=True)
            try:
                symlinks_ok = self._can_symlink(venv_dir)
                builder = venv.EnvBuilder(
                    with_pip=False,
                    clear=False,
                    symlinks=symlinks_ok,
                )
                builder.create(venv_dir)
                self._bootstrap_pip(venv_dir, site_pkg, py_exec)
            except Exception as e:
                # 友善診斷與指導提示 (EC-01)
                raise RuntimeError(
                    f"[PipManager] Failed to create private venv at '{venv_dir}'. "
                    f"Please ensure python3-venv / ensurepip is installed. Details: {e}"
                ) from e

        # 驗證並加固 pyvenv.cfg (EC-01 / NFR-01)
        cfg_path = os.path.join(venv_dir, "pyvenv.cfg")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "include-system-site-packages = true" in content:
                    content = content.replace(
                        "include-system-site-packages = true",
                        "include-system-site-packages = false",
                    )
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        f.write(content)
            except Exception:
                pass

        # 確保 yscb_dir/.gitignore 包含 /.venv/ 內部忽略標記
        self._ensure_gitignore()

        return venv_dir

    def _ensure_gitignore(self) -> None:
        """確保 yscb_dir/.gitignore 存在且包含 /.venv/ 內部忽略規則。"""
        gi_path = os.path.join(self.yscb_dir, ".gitignore")
        begin = "# === YSCB INTERNAL IGNORE BEGIN ==="
        end = "# === YSCB INTERNAL IGNORE END ==="
        patterns = [
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
        block_lines = [
            begin,
            "# Auto-managed by YSCB host bootstrapper. Do not edit this block manually.",
            *patterns,
            end,
        ]
        new_block = "\n".join(block_lines)

        content = ""
        if os.path.isfile(gi_path):
            try:
                with open(gi_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                pass

        if begin in content and end in content:
            pre = content.split(begin)[0]
            post = content.split(end)[1]
            final_content = pre.rstrip() + "\n" + new_block + "\n" + post.lstrip()
        else:
            final_content = (content.rstrip() + "\n\n" + new_block + "\n").lstrip()

        if final_content != content:
            try:
                with open(gi_path, "w", encoding="utf-8") as f:
                    f.write(final_content)
            except Exception:
                pass

    def install_packages(self, specs: List[str], py_tag: Optional[str] = None) -> None:
        """
        調用微環境之 python -m pip 執行 Wheel-Only 靜默安裝。
        強制附加參數: ['install', '--only-binary=:all:', '--no-warn-script-location', '--quiet', *specs]
        """
        if not specs:
            return

        self.ensure_venv(py_tag)
        py_exec = self.get_python_executable(py_tag)

        cmd = [
            py_exec,
            "-m",
            "pip",
            "install",
            "--only-binary=:all:",
            "--no-warn-script-location",
            "--quiet",
            *specs,
        ]

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
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
