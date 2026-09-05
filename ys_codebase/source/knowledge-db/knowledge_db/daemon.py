"""
HotReloadServer - Dedicated Indexing & Watcher Daemon for module:knowledge-db.

Monitors project directories, debounces file change events (500ms),
executes incremental hot patches across AST, BM25, Call Graph, and FastEmbed Vector,
and atomically updates binary index snapshots on disk.
Enforces cache:// space isolation, 3-generation rolling logs, version-aware restart,
and inactivity-based auto-shutdown.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .config import KnowledgeDBConfig

logger = logging.getLogger("knowledge_db.daemon")

_SERVER_JIT_NOTIFIED: bool = False


def check_and_notify_hot_reload_server(
    workspace_root: Optional[Union[str, Path]] = None,
) -> Tuple[bool, Optional["DaemonInfo"]]:
    """
    探測後台是否有運行中之 HotReloadServer [FR-12]。
    若有運行，向 stderr 提示 "Hot reload server(pid:<pid>) exist, skip JIT check."，
    並於該進程生命週期內僅提示一次。
    :return: (is_running, DaemonInfo)
    """
    global _SERVER_JIT_NOTIFIED
    is_running, info = HotReloadServer.is_running(workspace_root)
    if is_running and info is not None:
        if not _SERVER_JIT_NOTIFIED:
            print(f"Hot reload server(pid:{info.pid}) exist, skip JIT check.", file=sys.stderr, flush=True)
            _SERVER_JIT_NOTIFIED = True
        return True, info
    return False, None

DEFAULT_VCS_IGNORED_DIRS: Set[str] = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}


def resolve_watch_extensions(
    space_manager: Optional[Any] = None,
    parser_registry: Optional[Any] = None,
) -> Set[str]:
    """
    動態彙整受監聽之檔案副檔名集合 (100% 由 contributes.languages 與 SpaceConfig 動態決定)。
    """
    exts: Set[str] = set()

    # 1. 優先使用真實的 ParserRegistry 提供的動態語言副檔名
    try:
        from .parsers.registry import ParserRegistry
        real_reg = parser_registry if isinstance(parser_registry, ParserRegistry) else ParserRegistry()
        if hasattr(real_reg, "get_supported_extensions"):
            exts.update(real_reg.get_supported_extensions())
    except Exception:
        pass

    # 額外支援 .json（知識庫設定檔/中繼資料）
    exts.add(".json")

    if space_manager is not None:
        try:
            spaces = space_manager.get_union_spaces()
            for sp in spaces:
                patterns = getattr(sp, "file_patterns", None)
                if patterns:
                    for pat in patterns:
                        if pat.startswith("*."):
                            exts.add(pat[1:].lower())
        except Exception:
            pass

    return exts


# 向後相容別名
IGNORED_DIR_NAMES = DEFAULT_VCS_IGNORED_DIRS
SUPPORTED_WATCH_EXTENSIONS = resolve_watch_extensions()


@dataclass
class DaemonInfo:
    pid: int
    start_time: float
    version: str
    workspace_root: str
    log_file: str
    spaces: List[str] = field(default_factory=list)
    spaces_signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DaemonInfo":
        return cls(
            pid=int(data.get("pid", 0)),
            start_time=float(data.get("start_time", 0.0)),
            version=str(data.get("version", "unknown")),
            workspace_root=str(data.get("workspace_root", "")),
            log_file=str(data.get("log_file", "")),
            spaces=list(data.get("spaces", [])),
            spaces_signature=str(data.get("spaces_signature", "")),
        )


class HotReloadServer:
    """知識庫熱重載專屬守護進程，整合檔案系統監聽、防抖熱修補、PID 治理與閒置釋放。"""

    def __init__(
        self,
        workspace_root: Optional[Union[str, Path]] = None,
        config: Optional[KnowledgeDBConfig] = None,
        pipeline: Optional[Any] = None,
        space_manager: Optional[Any] = None,
    ):
        self.workspace_root = Path(workspace_root or self._find_workspace_root()).resolve()
        self.config = config or KnowledgeDBConfig.load(workspace_root=self.workspace_root)
        self.pipeline = pipeline
        self.space_manager = space_manager
        self.version = self.get_module_version()

        self._stop_event = threading.Event()
        self.last_activity_time: float = time.time()
        self._debounce_lock = threading.Lock()
        self._debounce_timer: Optional[threading.Timer] = None
        self._pending_dirty_paths: Set[str] = set()

        self.observer: Optional[Any] = None
        self._inactivity_thread: Optional[threading.Thread] = None
        self.log_file_path: Optional[Path] = None
        self.file_logger: Optional[logging.Logger] = None
        self._supported_extensions: Optional[Set[str]] = None

    @property
    def supported_extensions(self) -> Set[str]:
        """動態取得當前受監聽之副檔名集合 (由 contributes 與 spaces 動態解析)。"""
        if self._supported_extensions is None:
            sm = self._get_space_manager()
            parser_reg = getattr(self.pipeline, "parser_registry", None)
            self._supported_extensions = resolve_watch_extensions(sm, parser_reg)
        return self._supported_extensions

    @classmethod
    def _find_workspace_root(cls) -> Path:
        """向上尋找專案根目錄 (yscb.config.json 所在位置)。"""
        cur = Path(__file__).resolve().parent
        while cur and cur != cur.parent:
            if (cur / "yscb.config.json").is_file():
                return cur
            cur = cur.parent
        return Path.cwd()

    @classmethod
    def get_module_version(cls) -> str:
        """讀取當前 knowledge-db 模組之版本號。"""
        manifest_p = Path(__file__).resolve().parent.parent / "manifest.json"
        if manifest_p.is_file():
            try:
                with open(manifest_p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return str(data.get("version", "1.0.0")).strip()
            except Exception:
                pass
        return "1.0.0"

    @classmethod
    def get_cache_dir(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        """解析 cache://knowledge-db 實體目錄 (yscb://.cache/knowledge-db)。"""
        root = Path(workspace_root or cls._find_workspace_root()).resolve()
        try:
            from core.uri import resolve
            p = resolve("cache://knowledge-db", interactive=False)
            if p:
                cache_path = Path(p).resolve()
                cache_path.mkdir(parents=True, exist_ok=True)
                return cache_path
        except Exception:
            pass

        # 降級備用解析
        for candidate in [root / "ys_codebase" / ".cache" / "knowledge-db", root / ".cache" / "knowledge-db"]:
            if (candidate.parent).exists() or candidate.exists():
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate

        fallback = root / ".cache" / "knowledge-db"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    @classmethod
    def get_pid_file(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        """回傳 cache://knowledge-db/daemon.pid 路徑 [FR-09]。"""
        return cls.get_cache_dir(workspace_root) / "daemon.pid"

    @classmethod
    def get_logs_dir(cls, workspace_root: Optional[Union[str, Path]] = None) -> Path:
        """回傳 cache://knowledge-db/logs 目錄路徑 [FR-10]。"""
        d = cls.get_cache_dir(workspace_root) / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def is_pid_alive(cls, pid: int) -> bool:
        """跨平台探測進程是否存活。"""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @classmethod
    def is_running(cls, workspace_root: Optional[Union[str, Path]] = None) -> Tuple[bool, Optional[DaemonInfo]]:
        """探測守護進程存活狀態，自動清理死進程殭屍 PID [EC-01]。"""
        pid_file = cls.get_pid_file(workspace_root)
        if not pid_file.is_file():
            return False, None

        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            info = DaemonInfo.from_dict(raw_data)
        except Exception:
            # 損壞的 PID 檔案，直接清理
            try:
                pid_file.unlink(missing_ok=True)
            except OSError:
                pass
            return False, None

        if cls.is_pid_alive(info.pid):
            return True, info
        else:
            # 殭屍進程殘留，自動清理
            try:
                pid_file.unlink(missing_ok=True)
            except OSError:
                pass
            return False, None

    @classmethod
    def get_current_spaces_signature(
        cls,
        workspace_root: Optional[Union[str, Path]] = None,
        space_manager: Optional[Any] = None,
    ) -> Tuple[List[str], str]:
        """計算當前注入空間名稱清單與結構化 Hash 簽名 [FR-11, EC-09]。"""
        sm = space_manager
        if sm is None:
            try:
                from .space import SpaceManager
                root = Path(workspace_root or cls._find_workspace_root()).resolve()
                cfg_dir = root / "config" / "knowledge-db"
                sm = SpaceManager(
                    config_dir=cfg_dir if cfg_dir.is_dir() else None,
                )
            except Exception:
                sm = None

        if sm is None:
            return [], ""

        try:
            spaces = sm.get_union_spaces()
            space_names = sorted([sp.name for sp in spaces])
            items = []
            for sp in sorted(spaces, key=lambda s: s.name):
                try:
                    resolved = [str(p.resolve()) for p in sm.resolve_space_include(sp.name)]
                except Exception:
                    resolved = []
                items.append({
                    "name": sp.name,
                    "include": sorted(list(getattr(sp, "include", []))),
                    "exclude": sorted(list(getattr(sp, "exclude", []))),
                    "file_patterns": sorted(list(getattr(sp, "file_patterns", []) or [])),
                    "resolved": sorted(resolved),
                })
            raw = json.dumps(items, sort_keys=True)
            sig = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
            return space_names, sig
        except Exception:
            return [], ""

    def _get_space_manager(self) -> Any:
        """延遲載入或重用 SpaceManager。"""
        if self.space_manager is not None:
            return self.space_manager
        if self.pipeline is not None and hasattr(self.pipeline, "space_manager"):
            self.space_manager = self.pipeline.space_manager
            return self.space_manager
        try:
            from .space import SpaceManager
            cfg_dir = self.workspace_root / "config" / "knowledge-db"
            self.space_manager = SpaceManager(
                config_dir=cfg_dir if cfg_dir.is_dir() else None,
            )
            return self.space_manager
        except Exception:
            return None

    def get_watch_directories(self) -> List[Path]:
        """根據注入之 SpaceManager 空間聯集定義動態解算監聽目錄清單 [FR-03]。"""
        sm = self._get_space_manager()
        watch_dirs: Set[Path] = set()
        if sm is not None:
            try:
                spaces = sm.get_union_spaces()
                for sp in spaces:
                    includes = sm.resolve_space_include(sp.name)
                    for inc in includes:
                        p = Path(inc).resolve()
                        if p.is_dir():
                            watch_dirs.add(p)
                        elif p.is_file():
                            watch_dirs.add(p.parent)
            except Exception as e:
                logger.warning(f"Failed to resolve spaces for watch directories: {e}")

        if not watch_dirs:
            watch_dirs.add(self.workspace_root)

        return sorted(list(watch_dirs))

    @classmethod
    def ensure_running(
        cls,
        workspace_root: Optional[Union[str, Path]] = None,
        space_manager: Optional[Any] = None,
    ) -> bool:
        """
        若未運行則以 Detached 背景進程啟動 Server；
        若已運行但版本或空間定義不一致則強制終止舊進程並重新啟動 [FR-02, FR-11, EC-09]。
        """
        root = Path(workspace_root or cls._find_workspace_root()).resolve()
        current_ver = cls.get_module_version()
        current_spaces, current_sig = cls.get_current_spaces_signature(
            workspace_root=root,
            space_manager=space_manager,
        )

        running, info = cls.is_running(root)
        if running and info is not None:
            need_restart = False
            reason = ""
            if info.version != current_ver:
                need_restart = True
                reason = f"Version mismatch ({info.version} != {current_ver})"
            elif current_sig and info.spaces_signature and info.spaces_signature != current_sig:
                need_restart = True
                reason = f"Spaces mismatch ({info.spaces_signature} != {current_sig})"
            elif current_sig and not info.spaces_signature:
                # 升級未記錄 spaces_signature 之舊 PID
                need_restart = True
                reason = "Legacy PID without spaces_signature"

            if need_restart:
                logger.info(
                    f"[knowledge-db:daemon] {reason} detected, restarting server..."
                )
                cls.stop(root)
                time.sleep(0.3)
            else:
                return True

        # 背景啟動新進程 (Detached)
        yscb_py = root / "yscb.py"
        if yscb_py.is_file():
            cmd = [
                sys.executable,
                str(yscb_py),
                "knowledge-db",
                "daemon",
                "run-foreground",
                f"--workspace-root={root}",
            ]
        else:
            cli_path = Path(__file__).resolve().parent.parent / "scripts" / "cli.py"
            cmd = [
                sys.executable,
                str(cli_path),
                "daemon",
                "run-foreground",
                "--workspace-root",
                str(root),
            ]

        try:
            # 跨平台建立完全分離的背景進程
            popen_kwargs: Dict[str, Any] = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
                "cwd": str(root),
            }
            if sys.platform == "win32":
                # Windows Detached Process
                popen_kwargs["creationflags"] = (
                    getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                )
            else:
                # POSIX start_new_session (setsid)
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(cmd, **popen_kwargs)
            # 稍作等待讓 PID 檔案產生
            for _ in range(20):
                time.sleep(0.05)
                if cls.is_running(root)[0]:
                    return True
            return proc.poll() is None
        except Exception as e:
            logger.warning(f"[knowledge-db:daemon] Failed to start background daemon: {e}")
            return False

    @classmethod
    def stop(cls, workspace_root: Optional[Union[str, Path]] = None) -> bool:
        """發送 SIGTERM/SIGINT 優雅停止守護進程並清除 PID 鎖 [FR-07, EC-05]。"""
        running, info = cls.is_running(workspace_root)
        pid_file = cls.get_pid_file(workspace_root)
        if not running or info is None:
            if pid_file.is_file():
                try:
                    pid_file.unlink(missing_ok=True)
                except OSError:
                    pass
            return True

        target_pid = info.pid
        try:
            # 優先發送 SIGTERM
            sig = getattr(signal, "SIGTERM", signal.SIGINT)
            os.kill(target_pid, sig)
        except OSError:
            pass

        # 等待進程退出，最多 2 秒
        for _ in range(20):
            time.sleep(0.1)
            if not cls.is_pid_alive(target_pid):
                break
        else:
            # 強制 SIGKILL
            try:
                kill_sig = getattr(signal, "SIGKILL", signal.SIGTERM)
                os.kill(target_pid, kill_sig)
            except OSError:
                pass

        if pid_file.is_file():
            try:
                pid_file.unlink(missing_ok=True)
            except OSError:
                pass
        return True

    @classmethod
    def status(
        cls,
        workspace_root: Optional[Union[str, Path]] = None,
        space_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """查詢當前守護進程運作狀態、空間簽名與日誌路徑 [FR-07]。"""
        running, info = cls.is_running(workspace_root)
        current_ver = cls.get_module_version()
        current_spaces, current_sig = cls.get_current_spaces_signature(
            workspace_root=workspace_root,
            space_manager=space_manager,
        )
        res: Dict[str, Any] = {
            "running": running,
            "current_module_version": current_ver,
            "current_spaces": current_spaces,
            "current_spaces_signature": current_sig,
            "pid": info.pid if info else None,
            "start_time": info.start_time if info else None,
            "version": info.version if info else None,
            "spaces": info.spaces if info else None,
            "spaces_signature": info.spaces_signature if info else None,
            "log_file": info.log_file if info else None,
            "workspace_root": info.workspace_root if info else str(workspace_root or cls._find_workspace_root()),
        }
        return res

    def _setup_logger(self) -> logging.Logger:
        """建立即時寫入之日誌輸出器，並觸發 3 世代滾動清理 [FR-10, EC-08]。"""
        logs_dir = self.get_logs_dir(self.workspace_root)
        now_str = time.strftime("%Y%m%d_%H%M%S")
        pid = os.getpid()
        self.log_file_path = logs_dir / f"daemon_{now_str}_{pid}.log"

        srv_logger = logging.getLogger(f"knowledge_db.daemon.{pid}")
        srv_logger.setLevel(logging.INFO)
        srv_logger.propagate = False

        # 清除舊 Handler
        for h in list(srv_logger.handlers):
            srv_logger.removeHandler(h)

        try:
            fh = logging.FileHandler(str(self.log_file_path), encoding="utf-8")
            fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            fh.setFormatter(fmt)
            srv_logger.addHandler(fh)
        except Exception as e:
            logger.warning(f"Failed to attach file logger: {e}")

        self.file_logger = srv_logger

        # 執行滾動清理，最多保留 3 份歷史記錄
        self.rotate_logs(logs_dir, keep=3)
        return srv_logger

    @staticmethod
    def rotate_logs(logs_dir: Path, keep: int = 3) -> None:
        """以每次 PID 生命週期為單位，保留最新 3 份日誌，清理舊日誌 [FR-10]。"""
        try:
            if not logs_dir.is_dir():
                return
            log_files = [p for p in logs_dir.glob("daemon_*.log") if p.is_file()]
            # 依最後修改時間排序（新 -> 舊）
            log_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            if len(log_files) > keep:
                for old_file in log_files[keep:]:
                    try:
                        old_file.unlink(missing_ok=True)
                    except OSError:
                        pass
        except Exception:
            pass

    def _write_pid_file(self) -> None:
        """寫入 PID 檔案至 cache://knowledge-db/daemon.pid。"""
        pid_file = self.get_pid_file(self.workspace_root)
        spaces, spaces_sig = self.get_current_spaces_signature(
            workspace_root=self.workspace_root,
            space_manager=self._get_space_manager(),
        )
        info = DaemonInfo(
            pid=os.getpid(),
            start_time=time.time(),
            version=self.version,
            workspace_root=str(self.workspace_root),
            log_file=str(self.log_file_path or ""),
            spaces=spaces,
            spaces_signature=spaces_sig,
        )
        tmp_pid = pid_file.with_suffix(".pid.tmp")
        try:
            with open(tmp_pid, "w", encoding="utf-8") as f:
                json.dump(info.to_dict(), f, indent=2)
            os.replace(tmp_pid, pid_file)
        except Exception as e:
            if self.file_logger:
                self.file_logger.error(f"Failed writing pid file: {e}")

    def _clean_pid_file(self) -> None:
        """清理 PID 檔案。"""
        pid_file = self.get_pid_file(self.workspace_root)
        try:
            if pid_file.is_file():
                # 只有是當前進程的 PID 檔案時才刪除
                with open(pid_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if int(data.get("pid", 0)) == os.getpid():
                    pid_file.unlink(missing_ok=True)
        except Exception:
            try:
                pid_file.unlink(missing_ok=True)
            except OSError:
                pass

    def _get_pipeline(self) -> Any:
        """延遲載入或重用 IndexingPipeline。"""
        if self.pipeline is not None:
            return self.pipeline
        try:
            from .engine import KnowledgeEngine
            cfg_dir = self.workspace_root / "config" / "knowledge-db"
            engine = KnowledgeEngine(
                config_dir=cfg_dir if cfg_dir.is_dir() else None,
                storage_dir=self.space_manager.storage_dir if (self.space_manager and hasattr(self.space_manager, "storage_dir")) else None,
                contributes_data=self.space_manager._custom_contributes_data if (self.space_manager and hasattr(self.space_manager, "_custom_contributes_data")) else None,
            )
            self.pipeline = engine.pipeline
            return self.pipeline
        except Exception as e:
            if self.file_logger:
                self.file_logger.error(f"Failed initializing IndexingPipeline: {e}")
            raise

    def is_path_watched(self, file_path: Union[str, Path]) -> bool:
        """
        判定給定檔案路徑是否屬於受監聽之有效變更 [FR-03, EC-02]。
        1. 排除底層 VCS/Runtime 預設忽略目錄 (.git, .venv, __pycache__, .pytest_cache)。
        2. 動態檢查副檔名是否屬於 contributes.languages 或 Space 宣告集合。
        3. 動態檢查是否落在任一注入 Space 之 include 範圍，且未被該 Space 之 exclude 排除。
        """
        p = Path(file_path)
        for part in p.parts:
            if part in DEFAULT_VCS_IGNORED_DIRS:
                return False

        if p.suffix.lower() not in self.supported_extensions:
            return False

        sm = self._get_space_manager()
        if sm is None:
            return True

        try:
            spaces = sm.get_union_spaces()
        except Exception:
            return True

        if not spaces:
            return True

        try:
            abs_p = p.resolve()
            abs_p_str = str(abs_p).replace("\\", "/")
        except Exception:
            return True

        for sp in spaces:
            try:
                roots = sm.resolve_space_include(sp.name)
            except Exception:
                continue

            for root in roots:
                root_res = root.resolve()
                root_str = str(root_res).replace("\\", "/")
                matched = False
                rel_path = ""

                if root_res.is_file() and abs_p_str == root_str:
                    matched = True
                    rel_path = root_res.name
                elif root_res.is_dir() and (abs_p_str == root_str or abs_p_str.startswith(root_str + "/")):
                    matched = True
                    try:
                        rel_path = os.path.relpath(abs_p_str, root_str).replace("\\", "/")
                    except ValueError:
                        rel_path = p.name

                if matched:
                    from .scanner import FingerprintScanner
                    if FingerprintScanner._is_excluded(rel_path, sp.exclude):
                        return False
                    if not sp.is_file_included(p.name):
                        return False
                    return True

        # 若未精確匹配到任何已解析之 Space root（例如根目錄兜底監聽或未建立實體目錄之測試路徑）：
        # 只要檔案位於 workspace_root 之下，且未被任何已知 space 的 exclude 模式排除，即允許監聽
        try:
            from .scanner import FingerprintScanner
            ws_root_str = str(self.workspace_root.resolve()).replace("\\", "/")
            if abs_p_str == ws_root_str or abs_p_str.startswith(ws_root_str + "/"):
                try:
                    rel_to_ws = os.path.relpath(abs_p_str, ws_root_str).replace("\\", "/")
                except ValueError:
                    rel_to_ws = p.name

                for sp in spaces:
                    if FingerprintScanner._is_excluded(rel_to_ws, sp.exclude):
                        return False
                return True
        except Exception:
            pass

        return False

    def on_file_changed(self, file_path: str) -> None:
        """監聽回呼：過濾無關副檔名、重設 500ms 防抖計時器 [FR-03, EC-02]。"""
        p = Path(file_path)
        if not self.is_path_watched(p):
            return

        with self._debounce_lock:
            self.last_activity_time = time.time()
            self._pending_dirty_paths.add(str(p.resolve()))

            if self._debounce_timer is not None:
                self._debounce_timer.cancel()

            self._debounce_timer = threading.Timer(0.5, self._execute_debounced_patch)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _execute_debounced_patch(self) -> None:
        """防抖到期：由單工作線程呼叫 pipeline 執行 AST/BM25/Graph/Vector 熱修補 [FR-04, FR-05]。"""
        with self._debounce_lock:
            dirty = list(self._pending_dirty_paths)
            self._pending_dirty_paths.clear()
            self._debounce_timer = None

        if not dirty:
            return

        t0 = time.time()
        if self.file_logger:
            self.file_logger.info(f"Debounce triggered for {len(dirty)} dirty file(s). Starting hot patch...")

        try:
            pipeline = self._get_pipeline()
            indices_dir = pipeline.get_indices_dir()
            meta_file = indices_dir / "unified.meta.bin"

            # 透過 Scanner 比對差異
            _, scanned_count, reason, full_files_map, diff_detail = pipeline.scanner.check_invalidation(
                snapshot_path=meta_file
            )

            if diff_detail.has_changes:
                res = pipeline.hot_patch_unified_index(diff_detail, full_files_map, timeout_seconds=float('inf'))
                elapsed_ms = (time.time() - t0) * 1000
                if self.file_logger:
                    self.file_logger.info(
                        f"Hot patch completed in {elapsed_ms:.1f}ms ({scanned_count} files checked). Patched: {bool(res)}"
                    )
            else:
                elapsed_ms = (time.time() - t0) * 1000
                if self.file_logger:
                    self.file_logger.info(f"No semantic changes found after scan ({elapsed_ms:.1f}ms).")
        except Exception as e:
            if self.file_logger:
                self.file_logger.error(f"Error during debounced hot patch: {e}", exc_info=True)
        finally:
            self.last_activity_time = time.time()

    def _inactivity_check_loop(self) -> None:
        """定時監測線程：每 10 秒檢查一次，超過 inactivity_timer_sec 自動退出 [FR-06]。"""
        timeout_sec = max(10, getattr(self.config, "hot_reload_server_inactivity_timer_sec", 600))
        while not self._stop_event.is_set():
            time.sleep(5)
            if self._stop_event.is_set():
                break

            idle_duration = time.time() - self.last_activity_time
            if idle_duration >= timeout_sec:
                if self.file_logger:
                    self.file_logger.info(
                        f"Inactivity timeout reached ({idle_duration:.1f}s >= {timeout_sec}s). Shutting down server to release memory..."
                    )
                self.stop_server()
                break

    def stop_server(self) -> None:
        """終止本 Server 實例。"""
        self._stop_event.set()
        with self._debounce_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None

        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=2.0)
            except Exception:
                pass
            self.observer = None

        self._clean_pid_file()
        if self.file_logger:
            self.file_logger.info("HotReloadServer stopped cleanly.")

    def _run_startup_check(self) -> None:
        """啟動時先執行一次與 JIT 相同的增量/無效檢查，修補伺服器離線期間的檔案變更 [FR-13]。"""
        t0 = time.time()
        try:
            pipeline = self._get_pipeline()
            indices_dir = pipeline.get_indices_dir()
            meta_file = indices_dir / "unified.meta.bin"
            bin_file = indices_dir / "unified.index.bin.gz"

            if not bin_file.exists() or not meta_file.exists():
                if self.file_logger:
                    self.file_logger.info("Startup check: Unified index missing, building from scratch...")
                pipeline.build_unified_index(force=True)
                if self.file_logger:
                    self.file_logger.info(f"Startup check: Initial build completed in {(time.time() - t0)*1000:.1f}ms.")
                return

            is_dirty, scanned_count, reason, full_files_map, diff_detail = pipeline.scanner.check_invalidation(
                snapshot_path=meta_file
            )
            if is_dirty:
                if self.file_logger:
                    self.file_logger.info(f"Startup check: Detected changes while offline ({reason}), applying hot patch...")
                if diff_detail.has_changes:
                    pipeline.hot_patch_unified_index(diff_detail, full_files_map, timeout_seconds=float('inf'))
                else:
                    pipeline.build_unified_index(force=True)
                if self.file_logger:
                    self.file_logger.info(f"Startup check: Hot patch completed in {(time.time() - t0)*1000:.1f}ms.")
            else:
                if self.file_logger:
                    self.file_logger.info(f"Startup check: Indices up-to-date ({scanned_count} files, {(time.time() - t0)*1000:.1f}ms).")
        except Exception as e:
            if self.file_logger:
                self.file_logger.error(f"Startup check error: {e}", exc_info=True)
        finally:
            self.last_activity_time = time.time()

    def run_foreground(self) -> None:
        """前台阻塞式運行（用於 watch 模式或背景進程主回圈）。"""
        self._setup_logger()
        self._write_pid_file()

        if self.file_logger:
            self.file_logger.info(
                f"HotReloadServer starting (PID: {os.getpid()}, Version: {self.version}, Root: {self.workspace_root})"
            )

        # 啟動時先執行一次與 JIT 相同的檢查，修補離線期間檔案變更 [FR-13]
        self._run_startup_check()

        # 註冊中斷信號
        def _handle_signal(signum, frame):
            if self.file_logger:
                self.file_logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.stop_server()

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except Exception:
            pass

        # 啟動 Inactivity 監控線程
        self._inactivity_thread = threading.Thread(target=self._inactivity_check_loop, daemon=True)
        self._inactivity_thread.start()

        # 啟動 Watchdog 監控
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
            from watchdog.observers.polling import PollingObserver

            class ChangeHandler(FileSystemEventHandler):
                def __init__(self, srv: "HotReloadServer"):
                    self.srv = srv

                def on_any_event(self, event):
                    if getattr(event, "is_directory", False):
                        return
                    src = getattr(event, "src_path", None)
                    if src:
                        self.srv.on_file_changed(src)
                    dst = getattr(event, "dest_path", None)
                    if dst:
                        self.srv.on_file_changed(dst)

            use_polling = os.getenv("KNOWLEDGE_DB_FORCE_POLLING", "0").lower() in ("1", "true", "yes")
            self.observer = PollingObserver() if use_polling else Observer()
            handler = ChangeHandler(self)

            watch_dirs = self.get_watch_directories()
            attached_count = 0
            for d in watch_dirs:
                if d.is_dir():
                    self.observer.schedule(handler, str(d), recursive=True)
                    attached_count += 1
                    if self.file_logger:
                        self.file_logger.info(f"Watching directory (space resolved): {d}")

            if attached_count == 0:
                # 兜底監視根目錄
                self.observer.schedule(handler, str(self.workspace_root), recursive=True)
                if self.file_logger:
                    self.file_logger.info(f"Watching workspace root: {self.workspace_root}")

            self.observer.start()
            if self.file_logger:
                self.file_logger.info("Watchdog observer started successfully. Server ready.")
        except Exception as e:
            if self.file_logger:
                self.file_logger.error(f"Failed to start watchdog observer: {e}", exc_info=True)
            self.stop_server()
            return

        # 主回圈等待退出
        try:
            while not self._stop_event.is_set():
                time.sleep(1.0)
        except (KeyboardInterrupt, SystemExit):
            self.stop_server()
        finally:
            self.stop_server()
