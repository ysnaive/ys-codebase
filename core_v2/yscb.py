#!/usr/bin/env python3
"""YS-Codebase 2.0 ultra-thin stdlib-only bootstrapper (init, self-update, deterministic core auto-restore, and CLI delegation)."""

from __future__ import annotations

import ast
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
from http.client import HTTPConnection, HTTPException, HTTPMessage, HTTPSConnection
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import time
from typing import IO, Callable, Final, Iterator, Mapping, NoReturn, Optional, Sequence

if os.name == "nt":
    import ctypes
    import msvcrt
else:
    import fcntl
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
import urllib.request
import uuid
import zipfile
import zlib

DEFAULT_PROVIDER_URL = "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases"
DEFAULT_SELF_UPDATE_URL = "https://raw.githubusercontent.com/ysnaive/ys-codebase/releases/yscb.py"
DEFAULT_YSCB_ROOT_REL = ".yscb"
HOST_CONFIG_FILENAME = "yscb.config.json"
HOST_LOCAL_CONFIG_FILENAME = "yscb.config.local.json"
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_ZIP_BYTES = 128 * 1024 * 1024
_MAX_ZIP_SINGLE_BYTES = 32 * 1024 * 1024
_MAX_ZIP_TOTAL_BYTES = _MAX_ZIP_BYTES * 2
_ZIP_RATIO_CHECK_MIN_BYTES = 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 200
_MAX_ZIP_ENTRIES = 4096
_MAX_HTTP_REDIRECTS = 5
_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_IO_REPARSE_TAG_SYMLINK = 0xA000000C
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
_DISALLOWED_REPARSE_TAGS = frozenset({_IO_REPARSE_TAG_SYMLINK, _IO_REPARSE_TAG_MOUNT_POINT})
_BOOT_FALSY_ENV_TOKENS = frozenset({"", "0", "false", "no", "off"})
_BOOT_CI_ENV_KEYS = frozenset(
    {
        "CI",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "TF_BUILD",
        "BUILDKITE",
        "CIRCLECI",
        "TRAVIS",
        "JENKINS_URL",
        "BITBUCKET_BUILD_NUMBER",
    }
)
_BOOT_AGENT_ENV_KEYS = frozenset(
    {
        "ANTIGRAVITY_AGENT",
        "ANTIGRAVITY_CONVERSATION_ID",
        "ANTIGRAVITY_TRAJECTORY_ID",
        "ANTIGRAVITY_SESSION",
        "AGY_AGENT",
        "AGY_SESSION",
        "CLAUDECODE",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_SSE_PORT",
        "CODEX_SANDBOX",
        "CODEX_THREAD_ID",
        "CODEX_CI",
        "AIDER_SESSION",
        "CURSOR_AGENT",
        "WINDSURF_AGENT",
        "GEMINI_CLI",
        "OPENCODE",
    }
)
_POSIX_SYS_ROOT_LINKS = frozenset({"tmp", "var", "etc", "run"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_WIN_ILLEGAL_ZIP_CHARS = frozenset('<>:"|?*\x00')
_NON_FSYNCABLE_ERRNOS = frozenset(
    {
        errno.EINVAL,
        errno.EROFS,
        errno.EBADF,
        errno.EPERM,
        errno.EACCES,
        errno.ENOTSUP,
        errno.EOPNOTSUPP,
    }
)
_TRUTHY_OFFLINE_VALUES = frozenset({"1", "true", "yes", "on"})
_WIN_RESERVED_STEMS = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "clock$",
        "conin$",
        "conout$",
        *(f"com{s}" for s in (*range(1, 10), "\u00b9", "\u00b2", "\u00b3")),
        *(f"lpt{s}" for s in (*range(1, 10), "\u00b9", "\u00b2", "\u00b3")),
    }
)
_GLOBAL_LAUNCHER_FLAGS = frozenset({"-h", "--help", "--json", "--cold", "--profile", "--profile-mem"})
_NOFOLLOW_READ_FLAGS = os.O_RDONLY | (
    os.O_BINARY if os.name == "nt" else (os.O_NOFOLLOW | os.O_NONBLOCK)
)
_NOFOLLOW_EXCL_WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | (
    os.O_BINARY if os.name == "nt" else os.O_NOFOLLOW
)


class _BootstrapPayloadFormatError(ValueError):
    """Raised when fetched index.json or sidecar bytes are non-UTF8, malformed JSON, or non-object JSON."""


class _BootstrapNonFallbackError(RuntimeError):
    """Security, integrity, or explicit yank violation that must never silently fallback to stale mirror."""


class _BootstrapSecurityError(_BootstrapNonFallbackError):
    """Local symlink/UNC/traversal or remote SSRF/downgrade violation mapping to security_gated (exit 4)."""


class _BootstrapConfigTypeError(ValueError):
    """Raised when a host configuration string field contains a non-string, non-null value."""



def _reconfigure_utf8_standard_streams() -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    if isinstance(sys.stderr, io.TextIOWrapper):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _write_err(msg: str) -> None:
    sys.stderr.write(msg if msg.endswith("\n") else f"{msg}\n")
    sys.stderr.flush()


def _write_out(msg: str) -> None:
    sys.stdout.write(msg if msg.endswith("\n") else f"{msg}\n")
    sys.stdout.flush()


def _has_cli_json_flag(args: Sequence[str]) -> bool:
    raw = list(args)
    dd_idx = raw.index("--") if "--" in raw else len(raw)
    return "--json" in raw[:dd_idx]


def _reject_nonfinite_json_constant(token: str) -> NoReturn:
    raise ValueError(f"Non-standard JSON constant {token!r} is forbidden.")


def _loads_strict_json(text: str) -> object:
    return json.loads(text, parse_constant=_reject_nonfinite_json_constant)


def _dumps_strict_json(obj: object, *, indent: Optional[int] = None) -> str:
    return json.dumps(obj, indent=indent, ensure_ascii=False, allow_nan=False)


def _emit_bootstrap_result(
    *,
    json_mode: bool,
    ok: bool,
    human_msg: str,
    value: object = None,
    error_code: str = "business_failure",
    remediation: Optional[str] = None,
    exit_code: int = 0,
) -> int:
    if json_mode:
        if ok:
            doc: dict[str, object] = {
                "ok": True,
                "value": value,
                "error": None,
                "event_diagnostics": [],
                "teardown_diagnostics": [],
                "coalesced": False,
                "executed_hot": False,
            }
        else:
            doc = {
                "ok": False,
                "value": None,
                "error": {
                    "code": error_code,
                    "message": human_msg,
                    "remediation": remediation,
                    "source_task": None,
                },
                "event_diagnostics": [],
                "teardown_diagnostics": [],
                "coalesced": False,
                "executed_hot": False,
            }
        _write_out(_dumps_strict_json(doc))
        return exit_code
    if ok:
        _write_out(human_msg)
    else:
        _write_err(human_msg)
    return exit_code


def _emit_bootstrap_help(help_txt: str, command_path: list[str], *, json_mode: bool) -> int:
    if json_mode:
        return _emit_bootstrap_result(
            json_mode=True,
            ok=True,
            human_msg="",
            value={"help": help_txt, "command_path": command_path},
            exit_code=0,
        )
    _write_out(help_txt)
    return 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_BOOT_INT64_MAX = (1 << 63) - 1
_BOOT_MODULE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_BOOT_RESERVED_NON_MODULE_IDS = frozenset({"locks", "wheels", "daemon", "project"})
_BOOT_SEMVER4_RE = re.compile(
    r"^(?:v|V)?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:\.(?P<rev>0|[1-9]\d*|build))?"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _compare_boot_prerelease(left: str, right: str) -> int:
    l_parts = left.split(".")
    r_parts = right.split(".")
    for l_seg, r_seg in zip(l_parts, r_parts):
        if l_seg == r_seg:
            continue
        l_num = l_seg.isdigit()
        r_num = r_seg.isdigit()
        if l_num and r_num:
            return 1 if int(l_seg) > int(r_seg) else -1
        if l_num and not r_num:
            return -1
        if not l_num and r_num:
            return 1
        return 1 if l_seg > r_seg else -1
    if len(l_parts) == len(r_parts):
        return 0
    return 1 if len(l_parts) > len(r_parts) else -1


@dataclass(frozen=True, slots=True)
class _BootSemVer4:
    major: int
    minor: int
    patch: int
    revision: int
    is_build: bool
    prerelease: str

    @property
    def triple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def compare_precedence(self, other: _BootSemVer4) -> int:
        if self.triple != other.triple:
            return 1 if self.triple > other.triple else -1
        if not self.prerelease and other.prerelease:
            return 1
        if self.prerelease and not other.prerelease:
            return -1
        if self.prerelease and other.prerelease:
            pre_cmp = _compare_boot_prerelease(self.prerelease, other.prerelease)
            if pre_cmp != 0:
                return pre_cmp
        if not self.is_build and other.is_build:
            return 1
        if self.is_build and not other.is_build:
            return -1
        if self.revision != other.revision:
            return 1 if self.revision > other.revision else -1
        return 0

    def __lt__(self, other: _BootSemVer4) -> bool:
        return self.compare_precedence(other) < 0

    def __le__(self, other: _BootSemVer4) -> bool:
        return self.compare_precedence(other) <= 0

    def canonical_str(self) -> str:
        if self.is_build:
            return f"{self.major}.{self.minor}.{self.patch}.build"
        if self.prerelease:
            rev_part = f".{self.revision}" if self.revision != 0 else ""
            return f"{self.major}.{self.minor}.{self.patch}{rev_part}-{self.prerelease}"
        return f"{self.major}.{self.minor}.{self.patch}.{self.revision}"


def _parse_semver4(ver_str: str) -> _BootSemVer4:
    clean = ver_str.strip()
    m = _BOOT_SEMVER4_RE.fullmatch(clean)
    if m is None:
        raise ValueError(f"Invalid SemVer4 version string: {ver_str!r}")
    major = int(m.group("major"))
    minor = int(m.group("minor"))
    patch = int(m.group("patch"))
    raw_rev = m.group("rev")
    prerelease = m.group("pre") or ""
    is_build = raw_rev == "build"
    revision = 0 if (raw_rev is None or is_build) else int(raw_rev)
    if is_build and prerelease:
        raise ValueError(f"SemVer4 build version cannot have prerelease: {ver_str!r}")
    if any(v > _BOOT_INT64_MAX for v in (major, minor, patch, revision)):
        raise ValueError(f"SemVer4 component exceeds int64: {ver_str!r}")
    if prerelease and any(
        seg.isdigit() and len(seg) > 1 and seg.startswith("0") for seg in prerelease.split(".")
    ):
        raise ValueError(f"Leading zero forbidden in SemVer4 prerelease: {ver_str!r}")
    return _BootSemVer4(major, minor, patch, revision, is_build, prerelease)


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if os.name == "nt":
        return bool(st.st_file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT) and (
            st.st_reparse_tag in _DISALLOWED_REPARSE_TAGS
        )
    return False


def _safe_stream_isatty(stream: Optional[IO[str]]) -> bool:
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _is_boot_env_truthy(val: Optional[str]) -> bool:
    return val is not None and val.strip().lower() not in _BOOT_FALSY_ENV_TOKENS


def _detect_bootstrap_nonhuman_reason() -> Optional[str]:
    env_items = tuple(os.environ.items())
    explicit_modes = {
        v.strip().lower()
        for k, v in env_items
        if isinstance(k, str) and isinstance(v, str) and k.upper() == "YSCB_CALLER_MODE"
    }
    if "agent" in explicit_modes:
        return "agent"
    if "ci" in explicit_modes or "ci_pipeline" in explicit_modes:
        return "ci_pipeline"
    if "non_tty" in explicit_modes:
        return "non_tty"
    for k, v in env_items:
        if isinstance(k, str) and isinstance(v, str) and k.upper() in _BOOT_AGENT_ENV_KEYS and _is_boot_env_truthy(v):
            return "agent"
    for k, v in env_items:
        if isinstance(k, str) and isinstance(v, str) and k.upper() in _BOOT_CI_ENV_KEYS and _is_boot_env_truthy(v):
            return "ci_pipeline"
    for k, v in env_items:
        if isinstance(k, str) and isinstance(v, str) and k.upper() == "TERM" and v.strip().lower() == "dumb":
            return "non_tty"
    if not (_safe_stream_isatty(sys.stdin) and _safe_stream_isatty(sys.stdout)):
        return "non_tty"
    return None


def _check_bootstrap_mutation_gate(
    cmd_label: str,
    *,
    allow_mutation: bool,
    json_mode: bool,
) -> Optional[int]:
    if allow_mutation:
        return None
    nonhuman = _detect_bootstrap_nonhuman_reason()
    if nonhuman is None:
        return None
    return _emit_bootstrap_result(
        json_mode=json_mode,
        ok=False,
        human_msg=(
            f"Refusing '{cmd_label}' in non-interactive or automated caller mode ({nonhuman}) "
            "without explicit '--allow-bootstrap-mutation'."
        ),
        error_code="security_gated",
        remediation=(
            f"Run '{cmd_label}' interactively from a human TTY, or re-run with "
            "'--allow-bootstrap-mutation' after explicit human approval."
        ),
        exit_code=4,
    )


def _is_allowed_posix_root_symlink(cur: Path) -> bool:
    if os.name == "nt" or cur.parent != Path("/") or cur.name not in _POSIX_SYS_ROOT_LINKS:
        return False
    try:
        lst = os.lstat(cur)
        rst = os.stat(cur)
    except OSError:
        return False
    return lst.st_uid == 0 and stat.S_ISDIR(rst.st_mode)


def _split_raw_tail_segments(raw_tail: str) -> list[str]:
    norm = raw_tail.replace("\\", "/") if os.name == "nt" else raw_tail
    return [seg for seg in norm.split("/") if seg]


def _assert_safe_local_path(path: Path, *, allow_missing_leaf: bool = False) -> None:
    raw_str = str(path)
    if "\x00" in raw_str:
        raise _BootstrapSecurityError(f"Refusing NUL character in bootstrapper path: {path!r}")
    if raw_str.startswith(("\\\\", "//")) or path.drive.startswith("\\\\"):
        raise _BootstrapSecurityError(f"Refusing remote UNC path in bootstrapper: {path}")
    if (path.drive or path.anchor) and not path.is_absolute():
        raise _BootstrapSecurityError(f"Refusing half-qualified drive or root-relative path in bootstrapper: {path}")

    if path.is_absolute():
        anchor_str = path.anchor
        if not anchor_str:
            raise ValueError(f"Empty path: {path}")
        cur = Path(anchor_str)
        raw_segs = _split_raw_tail_segments(raw_str[len(anchor_str) :])
    else:
        cwd = Path.cwd()
        _assert_safe_local_path(cwd, allow_missing_leaf=False)
        cur = cwd
        raw_segs = _split_raw_tail_segments(raw_str)

    for idx, seg in enumerate(raw_segs):
        if ":" in seg or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in seg):
            raise _BootstrapSecurityError(f"Refusing unsafe segment {seg!r} in bootstrapper path: {path}")
        is_leaf = idx == len(raw_segs) - 1
        if seg == ".":
            if _is_reparse_or_symlink(cur) and not _is_allowed_posix_root_symlink(cur):
                raise _BootstrapSecurityError(f"Refusing symlink or reparse point in path: {cur}")
            if os.path.lexists(cur) and not cur.is_dir():
                raise _BootstrapSecurityError(f"Refusing dot traversal across non-directory in path: {cur}")
            continue
        if seg == "..":
            if not os.path.lexists(cur):
                raise _BootstrapSecurityError(f"Refusing parent traversal across non-existent directory '{cur}' in path: {path}")
            if _is_reparse_or_symlink(cur):
                if _is_allowed_posix_root_symlink(cur):
                    cur = cur.resolve()
                else:
                    raise _BootstrapSecurityError(f"Refusing parent traversal across symlink or reparse point: {cur}")
            if not cur.is_dir():
                raise _BootstrapSecurityError(f"Refusing parent traversal across non-directory: {cur}")
            parent = cur.parent
            if _is_reparse_or_symlink(parent) and not _is_allowed_posix_root_symlink(parent):
                raise _BootstrapSecurityError(f"Refusing symlink or reparse parent directory in path: {parent}")
            cur = parent
            continue

        if os.path.lexists(cur) and not cur.is_dir():
            raise _BootstrapSecurityError(f"Refusing child traversal across non-directory in path: {cur}")
        nxt = cur / seg
        if not os.path.lexists(nxt):
            cur = nxt
            if allow_missing_leaf or not is_leaf:
                continue
            break
        if _is_reparse_or_symlink(nxt):
            if _is_allowed_posix_root_symlink(nxt):
                cur = nxt
                continue
            raise _BootstrapSecurityError(f"Refusing symlink or reparse point in path: {nxt}")
        if not is_leaf and not nxt.is_dir():
            raise _BootstrapSecurityError(f"Refusing child traversal across non-directory in path: {nxt}")
        cur = nxt


def _read_nofollow_regular_bytes(path: Path, max_bytes: int) -> bytes:
    _assert_safe_local_path(path, allow_missing_leaf=False)
    if _is_reparse_or_symlink(path):
        raise _BootstrapSecurityError(f"Refusing symlink or reparse point file: {path}")
    try:
        lst = os.lstat(path)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError(f"Unable to stat file '{path}': {exc}") from exc
    if not stat.S_ISREG(lst.st_mode):
        raise _BootstrapSecurityError(f"Refusing non-regular file: {path}")
    if lst.st_size > max_bytes:
        raise RuntimeError(f"Payload exceeded {max_bytes} bytes: {path}")

    fd = os.open(str(path), _NOFOLLOW_READ_FLAGS)
    try:
        os.set_inheritable(fd, False)
        if os.name == "nt":
            _assert_safe_local_path(path, allow_missing_leaf=False)
            if _is_reparse_or_symlink(path):
                raise _BootstrapSecurityError(f"Refusing symlink or reparse point file: {path}")
        fst = os.fstat(fd)
        if not stat.S_ISREG(fst.st_mode):
            raise _BootstrapSecurityError(f"Refusing non-regular file descriptor: {path}")
        if fst.st_size > max_bytes:
            raise RuntimeError(f"Payload exceeded {max_bytes} bytes: {path}")
        if (lst.st_ino and fst.st_ino and lst.st_ino != fst.st_ino) or (
            lst.st_dev and fst.st_dev and lst.st_dev != fst.st_dev
        ):
            raise _BootstrapSecurityError(f"File identity changed during open: {path}")
        if os.name != "nt":
            os.set_blocking(fd, True)
        chunks: list[bytes] = []
        total = 0
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
            total += len(buf)
            if total > max_bytes:
                raise RuntimeError(f"Payload exceeded {max_bytes} bytes: {path}")
            chunks.append(buf)
        if os.name == "nt":
            _assert_safe_local_path(path, allow_missing_leaf=False)
            if _is_reparse_or_symlink(path):
                raise _BootstrapSecurityError(f"Refusing symlink or reparse point file after read: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


@contextmanager
def _bootstrap_exclusive_lock(yscb_root: Path, timeout_sec: float = 30.0) -> Iterator[None]:
    _assert_safe_local_path(yscb_root, allow_missing_leaf=True)
    lock_dir = yscb_root / ".cache" / "locks"
    _assert_safe_local_path(lock_dir, allow_missing_leaf=True)
    lock_dir.mkdir(parents=True, exist_ok=True)
    _assert_safe_local_path(lock_dir, allow_missing_leaf=False)
    lock_names = ("bootstrap.lock", "installer.lock", "tx_orchestrator.lock", "package_engine.lock")
    open_flags = os.O_RDWR | os.O_CREAT | (os.O_BINARY if os.name == "nt" else os.O_NOFOLLOW)
    deadline = time.monotonic() + max(0.5, timeout_sec)
    acquired_fds: list[tuple[int, bool]] = []
    try:
        for lock_name in lock_names:
            lock_file = lock_dir / lock_name
            _assert_safe_local_path(lock_file, allow_missing_leaf=True)
            if _is_reparse_or_symlink(lock_file):
                raise _BootstrapSecurityError(f"Refusing symlinked lock file: {lock_file}")
            try:
                lst = os.lstat(lock_file)
            except FileNotFoundError:
                lst = None
            except OSError as exc:
                raise RuntimeError(f"Failed to inspect lock file '{lock_file}': {exc}") from exc
            if lst is not None and (stat.S_ISLNK(lst.st_mode) or not stat.S_ISREG(lst.st_mode)):
                raise _BootstrapSecurityError(f"Refusing non-regular lock file: {lock_file}")
            try:
                fd = os.open(str(lock_file), open_flags, 0o600)
            except OSError as exc:
                if exc.errno == errno.ELOOP or _is_reparse_or_symlink(lock_file):
                    raise _BootstrapSecurityError(f"Refusing symlinked lock file: {lock_file}") from exc
                raise
            acquired_fds.append((fd, False))
            os.set_inheritable(fd, False)
            fst = os.fstat(fd)
            if not stat.S_ISREG(fst.st_mode):
                raise _BootstrapSecurityError(f"Refusing non-regular lock file: {lock_file}")
            if os.name == "nt" and _is_reparse_or_symlink(lock_file):
                raise _BootstrapSecurityError(f"Refusing symlinked lock file: {lock_file}")
            while True:
                try:
                    if os.name == "nt":
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired_fds[-1] = (fd, True)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Timed out acquiring lock '{lock_file}': {exc}") from exc
                    time.sleep(0.02)
        yield
    finally:
        for fd, is_locked in reversed(acquired_fds):
            try:
                if is_locked:
                    if os.name == "nt":
                        try:
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                        except OSError:
                            pass
                    else:
                        try:
                            fcntl.flock(fd, fcntl.LOCK_UN)
                        except OSError:
                            pass
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass


def _replace_with_nt_retry(src: Path, dst: Path) -> None:
    for attempt in range(6):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if dst.exists() and not _is_reparse_or_symlink(dst) and dst.is_file():
                try:
                    os.chmod(dst, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
            if attempt >= 5:
                raise
            time.sleep(0.015 * (2**attempt))


def _grant_owner_writable_nonsymlink(target: Path) -> None:
    if _is_reparse_or_symlink(target):
        return
    try:
        st = os.lstat(target)
    except OSError:
        return
    mode = stat.S_IMODE(st.st_mode)
    desired = (mode | stat.S_IRWXU) if stat.S_ISDIR(st.st_mode) else (mode | stat.S_IRUSR | stat.S_IWUSR)
    try:
        os.chmod(target, desired)
    except OSError:
        pass


def _rmtree_safe(target: Path, *, ignore_errors: bool = False) -> None:
    if not target.exists() and not _is_reparse_or_symlink(target):
        return
    if _is_reparse_or_symlink(target):
        try:
            target.unlink()
        except OSError:
            try:
                os.rmdir(target)
            except OSError:
                if not ignore_errors:
                    raise
        return

    _grant_owner_writable_nonsymlink(target)

    def _on_rm_error(func: Callable[[str], object], fpath: str, _exc_info: object) -> None:
        fp = Path(fpath)
        if not _is_reparse_or_symlink(fp):
            _grant_owner_writable_nonsymlink(fp.parent)
            _grant_owner_writable_nonsymlink(fp)
            try:
                func(fpath)
                return
            except OSError:
                pass
        if not ignore_errors:
            raise PermissionError(f"Unable to remove locked or protected path: {fpath}")

    shutil.rmtree(target, onerror=_on_rm_error)


def _atomic_write_bytes(dest: Path, data: bytes, *, preserve_mode: bool = True) -> None:
    _assert_safe_local_path(dest, allow_missing_leaf=True)
    if _is_reparse_or_symlink(dest):
        raise _BootstrapSecurityError(f"Refusing atomic write onto symlink or reparse target: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    orig_mode: Optional[int] = None
    if preserve_mode and os.name != "nt":
        try:
            st_dest = os.lstat(dest)
            if stat.S_ISREG(st_dest.st_mode):
                orig_mode = stat.S_IMODE(st_dest.st_mode)
        except OSError:
            orig_mode = None

    tmp = dest.parent / f".{dest.name}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    try:
        fd = os.open(str(tmp), _NOFOLLOW_EXCL_WRITE_FLAGS, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError as fsync_exc:
                if fsync_exc.errno not in _NON_FSYNCABLE_ERRNOS:
                    raise
        if os.name != "nt":
            target_mode = orig_mode if orig_mode is not None else 0o644
            try:
                os.chmod(tmp, target_mode)
            except OSError:
                pass
        _replace_with_nt_retry(tmp, dest)
    finally:
        if os.path.lexists(tmp):
            try:
                tmp.unlink()
            except OSError:
                pass


def _atomic_write_json(dest: Path, payload: Mapping[str, object]) -> None:
    encoded = (_dumps_strict_json(payload, indent=2) + "\n").encode("utf-8")
    _atomic_write_bytes(dest, encoded)


def _read_json_file(path: Path) -> Optional[dict[str, object]]:
    _assert_safe_local_path(path, allow_missing_leaf=True)
    if not os.path.lexists(path):
        return None
    if _is_reparse_or_symlink(path):
        raise _BootstrapSecurityError(f"Refusing symlink or reparse configuration file: {path}")
    raw = _read_nofollow_regular_bytes(path, _MAX_JSON_BYTES)
    parsed = _loads_strict_json(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return parsed


def _classify_ip_tier(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    if isinstance(ip_obj, ipaddress.IPv6Address):
        if ip_obj.ipv4_mapped is not None:
            return _classify_ip_tier(ip_obj.ipv4_mapped)
        if ip_obj.sixtofour is not None:
            return _classify_ip_tier(ip_obj.sixtofour)
        if ip_obj.teredo is not None:
            srv_tier = _classify_ip_tier(ip_obj.teredo[0])
            cli_tier = _classify_ip_tier(ip_obj.teredo[1])
            if "forbidden" in (srv_tier, cli_tier) or {srv_tier, cli_tier} == {"loopback", "private_lan"}:
                return "forbidden"
            if "loopback" in (srv_tier, cli_tier):
                return "loopback"
            if "private_lan" in (srv_tier, cli_tier):
                return "private_lan"
            return "public"
    if ip_obj.is_link_local or ip_obj.is_unspecified or ip_obj.is_multicast:
        return "forbidden"
    if ip_obj.is_loopback:
        return "loopback"
    if ip_obj.is_reserved:
        return "forbidden"
    if ip_obj.is_global:
        return "public"
    return "private_lan"


def _allowed_dest_tiers_for_origin(origin_tier: str) -> frozenset[str]:
    if origin_tier == "loopback":
        return frozenset({"loopback", "public"})
    if origin_tier == "private_lan":
        return frozenset({"private_lan", "public"})
    if origin_tier == "public":
        return frozenset({"public"})
    return frozenset()


def _is_loopback_http_host(raw_host: str) -> bool:
    clean = raw_host.strip().lower().strip("[]")
    if not clean:
        return False
    if clean == "localhost" or clean.endswith(".localhost"):
        return True
    try:
        ip_obj = ipaddress.ip_address(clean.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        return False
    return ip_obj.is_loopback


def _classify_host_origin_tier(hostname: str) -> str:
    clean = hostname.strip().lower().strip("[]")
    if not clean:
        return "forbidden"
    if clean in _LOOPBACK_HOSTS or clean.endswith(".localhost"):
        return "loopback"
    try:
        ip_lit = ipaddress.ip_address(clean.split("%", 1)[0])
        if isinstance(ip_lit, ipaddress.IPv6Address) and ip_lit.ipv4_mapped is not None:
            mapped_tier = _classify_ip_tier(ip_lit.ipv4_mapped)
            return "forbidden" if mapped_tier == "loopback" else mapped_tier
        return _classify_ip_tier(ip_lit)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(clean, None, type=socket.SOCK_STREAM)
    except OSError:
        return "public"
    if not infos:
        return "public"
    tiers: set[str] = set()
    for info in infos:
        addr_raw = info[4][0]
        if not isinstance(addr_raw, str):
            return "forbidden"
        try:
            tiers.add(_classify_ip_tier(ipaddress.ip_address(addr_raw.split("%", 1)[0])))
        except ValueError:
            return "forbidden"
    if "forbidden" in tiers or "loopback" in tiers or len(tiers) > 1:
        return "forbidden"
    if "private_lan" in tiers:
        return "private_lan"
    return "public"


def _resolve_and_verify_endpoints(
    host: str,
    port: int,
    allowed_tiers: frozenset[str],
) -> list[tuple[int, int, int, tuple[object, ...], str]]:
    clean = host.strip().lower().strip("[]")
    if not clean:
        raise RuntimeError("Empty target host in HTTP(S) connection.")
    infos = socket.getaddrinfo(clean, port, 0, socket.SOCK_STREAM)
    if not infos:
        raise RuntimeError(f"Unable to resolve host '{host}'.")
    verified: list[tuple[int, int, int, tuple[object, ...], str]] = []
    for af, socktype, proto, _canon, sa in infos:
        addr_raw = sa[0]
        if not isinstance(addr_raw, str):
            raise RuntimeError(f"Unsupported socket address for host '{host}'.")
        try:
            ip_obj = ipaddress.ip_address(addr_raw.split("%", 1)[0])
        except ValueError as exc:
            raise RuntimeError(f"Invalid resolved IP '{addr_raw}' for host '{host}'.") from exc
        tier = _classify_ip_tier(ip_obj)
        if tier not in allowed_tiers:
            raise _BootstrapSecurityError(
                f"Refusing connection to '{host}' ({addr_raw}, tier={tier}); allowed tiers={sorted(allowed_tiers)}."
            )
        verified.append((af, socktype, proto, sa, tier))
    return verified


def _open_verified_tcp_socket(
    host: str,
    port: int,
    timeout: Optional[float],
    source_address: Optional[tuple[str, int]],
    allowed_tiers: frozenset[str],
) -> tuple[socket.socket, str]:
    endpoints = _resolve_and_verify_endpoints(host, port, allowed_tiers)
    last_err: Optional[OSError] = None
    for af, socktype, proto, sa, conn_tier in endpoints:
        sock: Optional[socket.socket] = None
        try:
            sock = socket.socket(af, socktype, proto)
            if timeout is not None:
                sock.settimeout(timeout)
            if source_address is not None:
                sock.bind(source_address)
            sock.connect(sa)
            return (sock, conn_tier)
        except OSError as exc:
            last_err = exc
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    if last_err is not None:
        raise last_err
    raise OSError(f"Failed to connect to '{host}:{port}'.")


class _HttpTierBudget:
    __slots__ = ("_allowed_tiers",)

    def __init__(self, initial_tiers: frozenset[str]) -> None:
        self._allowed_tiers = initial_tiers

    @property
    def allowed_tiers(self) -> frozenset[str]:
        return self._allowed_tiers

    def narrow(self, next_tiers: frozenset[str]) -> None:
        self._allowed_tiers = self._allowed_tiers & next_tiers


class _PinnedHttpConnection(HTTPConnection):
    def __init__(self, host: str, *, tier_budget: _HttpTierBudget, **kwargs: object) -> None:
        super().__init__(host, **kwargs)  # type: ignore[arg-type]
        self._tier_budget = tier_budget
        self._pinned_tunnel_host: Optional[str] = None

    def set_tunnel(self, host: str, port: Optional[int] = None, headers: Optional[Mapping[str, str]] = None) -> None:
        self._pinned_tunnel_host = host
        super().set_tunnel(host, port=port, headers=headers)

    def connect(self) -> None:
        if self._pinned_tunnel_host is not None:
            raise _BootstrapSecurityError("HTTP CONNECT proxy tunneling is forbidden in bootstrapper.")
        sock, conn_tier = _open_verified_tcp_socket(
            self.host,
            self.port,
            self.timeout,
            self.source_address,
            self._tier_budget.allowed_tiers & frozenset({"loopback"}),
        )
        self._tier_budget.narrow(_allowed_dest_tiers_for_origin(conn_tier))
        self.sock = sock


class _PinnedHttpsConnection(HTTPSConnection):
    def __init__(
        self,
        host: str,
        *,
        tier_budget: _HttpTierBudget,
        context: Optional[ssl.SSLContext] = None,
        **kwargs: object,
    ) -> None:
        eff_ctx = context if context is not None else ssl.create_default_context()
        super().__init__(host, context=eff_ctx, **kwargs)  # type: ignore[arg-type]
        self._tier_budget = tier_budget
        self._ssl_ctx = eff_ctx
        self._pinned_tunnel_host: Optional[str] = None

    def set_tunnel(self, host: str, port: Optional[int] = None, headers: Optional[Mapping[str, str]] = None) -> None:
        self._pinned_tunnel_host = host
        super().set_tunnel(host, port=port, headers=headers)

    def connect(self) -> None:
        if self._pinned_tunnel_host is not None:
            raise _BootstrapSecurityError("HTTP CONNECT proxy tunneling is forbidden in bootstrapper.")
        raw_sock, conn_tier = _open_verified_tcp_socket(
            self.host,
            self.port,
            self.timeout,
            self.source_address,
            self._tier_budget.allowed_tiers,
        )
        self._tier_budget.narrow(_allowed_dest_tiers_for_origin(conn_tier))
        try:
            sni_host = self.host.strip("[]")
            self.sock = self._ssl_ctx.wrap_socket(raw_sock, server_hostname=sni_host)
        except BaseException:
            try:
                raw_sock.close()
            except OSError:
                pass
            raise


class _PinnedHttpHandler(urllib.request.HTTPHandler):
    def __init__(self, tier_budget: _HttpTierBudget) -> None:
        super().__init__()
        self._tier_budget = tier_budget

    def http_open(self, req: urllib.request.Request) -> object:
        return self.do_open(
            lambda host, **kw: _PinnedHttpConnection(host, tier_budget=self._tier_budget, **kw),
            req,
        )


class _PinnedHttpsHandler(urllib.request.HTTPSHandler):
    def __init__(self, tier_budget: _HttpTierBudget) -> None:
        super().__init__()
        self._tier_budget = tier_budget

    def https_open(self, req: urllib.request.Request) -> object:
        return self.do_open(
            lambda host, **kw: _PinnedHttpsConnection(host, tier_budget=self._tier_budget, **kw),
            req,
        )


def _validate_http_url(url: str) -> None:
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        raise _BootstrapSecurityError(f"Control characters forbidden in remote URL: {url!r}")
    parsed = urlparse(url)
    _ = parsed.port
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme not in ("https", "http") or not host:
        raise _BootstrapNonFallbackError(f"Unsupported or malformed remote URL: {url}")
    if scheme == "http" and not _is_loopback_http_host(host):
        raise _BootstrapSecurityError(f"Refusing insecure non-HTTPS URL: {url}")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, *, tier_budget: _HttpTierBudget) -> None:
        super().__init__()
        self._tier_budget = tier_budget
        self._redirect_count = 0

    @staticmethod
    def _close_redirect_fp(fp: Optional[IO[bytes]]) -> None:
        if fp is not None:
            try:
                fp.close()
            except OSError:
                pass

    @classmethod
    def _reject_redirect(cls, message: str, fp: Optional[IO[bytes]] = None) -> NoReturn:
        cls._close_redirect_fp(fp)
        raise _BootstrapNonFallbackError(message)

    @classmethod
    def _reject_security_redirect(cls, message: str, fp: Optional[IO[bytes]] = None) -> NoReturn:
        cls._close_redirect_fp(fp)
        raise _BootstrapSecurityError(message)

    def _precheck_redirect_headers(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        headers: HTTPMessage,
    ) -> None:
        raw_loc = headers.get("location")
        if raw_loc is None:
            raw_loc = headers.get("uri")
        if raw_loc is None:
            return
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_loc):
            self._reject_security_redirect("Control characters forbidden in HTTP redirect Location header.", fp=fp)
        target_raw = raw_loc.strip()
        try:
            raw_parsed = urlparse(target_raw)
            _ = raw_parsed.port
            joined_url = urljoin(req.full_url, target_raw)
            dst_parsed = urlparse(joined_url)
            _ = dst_parsed.port
        except ValueError as exc:
            self._reject_redirect(f"Malformed redirect target URL '{target_raw}': {exc}", fp=fp)
        if raw_parsed.scheme and raw_parsed.scheme.lower() not in ("http", "https"):
            self._reject_security_redirect(f"Unsupported HTTP redirect scheme in '{target_raw}'.", fp=fp)
        dst_scheme = dst_parsed.scheme.lower()
        dst_host = (dst_parsed.hostname or "").lower()
        if dst_scheme not in ("http", "https") or not dst_host:
            self._reject_redirect(f"Unsupported HTTP redirect scheme or host in '{joined_url}'.", fp=fp)

    def http_error_301(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_301(req, fp, code, msg, headers)

    def http_error_302(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_302(req, fp, code, msg, headers)

    def http_error_303(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_303(req, fp, code, msg, headers)

    def http_error_307(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_307(req, fp, code, msg, headers)

    def http_error_308(self, req: urllib.request.Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage) -> Optional[IO[bytes]]:
        self._precheck_redirect_headers(req, fp, headers)
        return super().http_error_308(req, fp, code, msg, headers)

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Optional[urllib.request.Request]:
        self._redirect_count += 1
        if self._redirect_count > _MAX_HTTP_REDIRECTS:
            self._close_redirect_fp(fp)
            raise URLError(f"Exceeded maximum HTTP redirects ({_MAX_HTTP_REDIRECTS}) at '{newurl}'.")
        try:
            _validate_http_url(newurl)
            src_parsed = urlparse(req.full_url)
            dst_parsed = urlparse(newurl)
        except _BootstrapSecurityError as exc:
            self._reject_security_redirect(str(exc), fp=fp)
        except (ValueError, RuntimeError) as exc:
            self._reject_redirect(str(exc), fp=fp)
        if src_parsed.scheme.lower() == "https" and dst_parsed.scheme.lower() != "https":
            self._reject_security_redirect(f"Refusing HTTPS-to-HTTP redirect downgrade: {newurl}", fp=fp)
        dst_host = (dst_parsed.hostname or "").lower()
        dst_tier = _classify_host_origin_tier(dst_host)
        if dst_tier not in self._tier_budget.allowed_tiers:
            self._reject_security_redirect(
                f"Refusing insecure redirect to disallowed host '{dst_host}' (tier={dst_tier}).",
                fp=fp,
            )
        self._tier_budget.narrow(_allowed_dest_tiers_for_origin(dst_tier))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_safe_http_opener(initial_url: str) -> urllib.request.OpenerDirector:
    parsed = urlparse(initial_url)
    host_only = (parsed.hostname or "").lower()
    origin_tier = _classify_host_origin_tier(host_only)
    allowed_tiers = _allowed_dest_tiers_for_origin(origin_tier)
    if not allowed_tiers:
        raise _BootstrapSecurityError(f"Refusing connection to forbidden host '{host_only}'.")
    budget = _HttpTierBudget(allowed_tiers)
    http_h = _PinnedHttpHandler(budget)
    https_h = _PinnedHttpsHandler(budget)
    redirect_handler = _SafeRedirectHandler(tier_budget=budget)
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), http_h, https_h, redirect_handler)


def _fetch_bytes_from_source(source: str, host_dir: Path, max_bytes: int) -> bytes:
    clean = source.strip()
    lower = clean.lower()
    if lower.startswith(("http://", "https://")):
        _validate_http_url(clean)
        opener = _build_safe_http_opener(clean)
        req = urllib.request.Request(clean, headers={"User-Agent": "yscb-bootstrap/2.0"})
        try:
            with opener.open(req, timeout=15.0) as resp:
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError(f"Remote payload exceeded {max_bytes} bytes: {clean}")
                    chunks.append(chunk)
                return b"".join(chunks)
        except HTTPException as exc:
            raise URLError(f"HTTP protocol error fetching '{clean}': {exc}") from exc
    if lower.startswith("file://"):
        parsed_u = urlparse(clean)
        if (parsed_u.netloc or "").lower() not in ("", "localhost", "127.0.0.1", "[::1]"):
            raise _BootstrapSecurityError(f"Refusing non-local file:// authority '{parsed_u.netloc}': {clean}")
        if parsed_u.params or parsed_u.query or parsed_u.fragment:
            raise _BootstrapNonFallbackError(f"Malformed file:// URL with query/fragment: {clean}")
        raw_u_path = parsed_u.path
        if os.name == "nt":
            if raw_u_path.startswith("//"):
                raise _BootstrapSecurityError(f"Refusing UNC file:// path in bootstrapper: {clean}")
            dec_u_path = unquote(raw_u_path)
            if (
                "\x00" in dec_u_path
                or "|" in dec_u_path
                or re.match(r"^/[A-Za-z]:/", dec_u_path) is None
                or ":" in dec_u_path[3:]
            ):
                raise _BootstrapSecurityError(f"Invalid Windows drive file:// path in bootstrapper: {clean}")
        elif raw_u_path.startswith("//"):
            raw_u_path = "/" + raw_u_path.lstrip("/")
        local_p = Path(urllib.request.url2pathname(raw_u_path))
        if not local_p.is_absolute():
            raise _BootstrapSecurityError(f"Refusing non-absolute file:// URL path: {clean}")
    else:
        cand = Path(clean)
        if (cand.drive or cand.anchor) and not cand.is_absolute():
            raise _BootstrapSecurityError(f"Refusing half-qualified drive or root-relative bootstrap source: {clean}")
        local_p = cand if cand.is_absolute() else (host_dir / cand)
    _assert_safe_local_path(local_p)
    resolved_p = local_p.resolve()
    return _read_nofollow_regular_bytes(resolved_p, max_bytes)


def _validate_safe_archive_name(raw_name: str) -> str:
    clean = raw_name.strip()
    if (
        not clean
        or len(clean) > 255
        or not clean.lower().endswith(".zip")
        or clean.startswith(".")
        or clean.endswith((".", " "))
        or any(ch in _WIN_ILLEGAL_ZIP_CHARS or ch in ("/", "\\", "?", "#") or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in clean)
    ):
        raise _BootstrapNonFallbackError(f"Unsafe archive filename in core/index.json: {raw_name!r}")
    stem = clean[:-4].split(".", 1)[0].rstrip(". ").lower()
    if not stem or stem in _WIN_RESERVED_STEMS:
        raise _BootstrapNonFallbackError(f"Invalid or reserved archive filename in core/index.json: {raw_name!r}")
    return clean


def _join_provider_subpath(provider: str, *parts: str) -> str:
    raw_clean = provider.strip()
    safe_parts: list[str] = []
    for part in parts:
        seg = part.strip()
        if (
            not seg
            or seg in (".", "..")
            or "/" in seg
            or "\\" in seg
            or ":" in seg
            or "?" in seg
            or "#" in seg
            or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in seg)
        ):
            raise _BootstrapNonFallbackError(f"Unsafe provider subpath segment: {part!r}")
        safe_parts.append(seg)
    lower = raw_clean.lower()
    if lower.startswith(("http://", "https://", "file://")):
        url_base = raw_clean.rstrip("/\\")
        rel = "/".join(safe_parts)
        return f"{url_base}/{rel}"
    return str(Path(raw_clean).joinpath(*safe_parts))


def _select_core_release_from_index(
    idx_doc: Mapping[str, object],
    pinned_version: Optional[str],
) -> tuple[str, Optional[str], tuple[str, ...]]:
    raw_releases = idx_doc.get("releases")
    releases = raw_releases if isinstance(raw_releases, Mapping) else {}
    raw_versions = idx_doc.get("versions")
    ver_list: list[str] = []
    if isinstance(raw_versions, list):
        ver_list.extend(str(v) for v in raw_versions if isinstance(v, str))
    for k in releases.keys():
        if isinstance(k, str) and k not in ver_list:
            ver_list.append(k)

    def _entry_info(ver_s: str, sv_obj: _BootSemVer4) -> tuple[str, bool, Optional[str], tuple[str, ...]]:
        rec = releases.get(ver_s)
        if not isinstance(rec, Mapping):
            rec = releases.get(sv_obj.canonical_str())
        default_names: list[str] = []
        for cand_stem in (ver_s.lstrip("vV"), sv_obj.canonical_str(), f"{sv_obj.major}.{sv_obj.minor}.{sv_obj.patch}" if (not sv_obj.is_build and not sv_obj.prerelease and sv_obj.revision == 0) else ""):
            if cand_stem:
                cand_zip = _validate_safe_archive_name(f"{cand_stem}.zip")
                if cand_zip not in default_names:
                    default_names.append(cand_zip)
        if not isinstance(rec, Mapping):
            return ("active", False, None, tuple(default_names))
        status = str(rec.get("status", "active"))
        yanked = bool(rec.get("yanked", False))
        sha = str(rec["sha256"]).lower() if isinstance(rec.get("sha256"), str) and rec.get("sha256") else None
        explicit_fn = rec.get("filename") or rec.get("archive")
        if explicit_fn:
            fnames = (_validate_safe_archive_name(str(explicit_fn)),)
        else:
            fnames = tuple(default_names)
        return (status, yanked, sha, fnames)

    if pinned_version is None:
        stable_cands: list[tuple[_BootSemVer4, str, Optional[str], tuple[str, ...]]] = []
        pre_cands: list[tuple[_BootSemVer4, str, Optional[str], tuple[str, ...]]] = []
        for v_str in ver_list:
            try:
                sv = _parse_semver4(v_str)
            except ValueError:
                continue
            if sv.is_build:
                continue
            status, yanked, sha, fnames = _entry_info(v_str, sv)
            if status == "active" and not yanked:
                if sv.prerelease:
                    pre_cands.append((sv, sv.canonical_str(), sha, fnames))
                else:
                    stable_cands.append((sv, sv.canonical_str(), sha, fnames))
        chosen_pool = stable_cands if stable_cands else pre_cands
        if not chosen_pool:
            raise RuntimeError("No active non-yanked 'core' release found in provider index.json.")
        chosen_pool.sort(key=lambda item: item[0])
        _sv, best_ver, best_sha, best_fnames = chosen_pool[-1]
        return (best_ver, best_sha, best_fnames)

    pin_sv = _parse_semver4(pinned_version)
    explicitly_pruned = False
    for v_str in ver_list:
        try:
            cand_sv = _parse_semver4(v_str)
        except ValueError:
            continue
        if cand_sv != pin_sv:
            continue
        status, yanked, sha, fnames = _entry_info(v_str, cand_sv)
        if status == "active" and not yanked:
            return (cand_sv.canonical_str(), sha, fnames)
        if yanked:
            raise _BootstrapNonFallbackError(f"Pinned core version '{pinned_version}' is yanked; refusing blind downgrade.")
        if status == "pruned":
            explicitly_pruned = True
    if pin_sv.is_build:
        raise _BootstrapNonFallbackError(
            f"Pinned development build core version '{pinned_version}' is unavailable and cannot fallback to release versions."
        )

    same_triplet: list[tuple[_BootSemVer4, str, Optional[str], tuple[str, ...]]] = []
    for v_str in ver_list:
        try:
            sv = _parse_semver4(v_str)
        except ValueError:
            continue
        if sv.is_build or sv.prerelease != pin_sv.prerelease or sv.triple != pin_sv.triple:
            continue
        if not explicitly_pruned and sv <= pin_sv:
            continue
        status, yanked, sha, fnames = _entry_info(v_str, sv)
        if status == "active" and not yanked:
            same_triplet.append((sv, sv.canonical_str(), sha, fnames))
    if same_triplet:
        same_triplet.sort(key=lambda item: item[0])
        _sv, fb_ver, fb_sha, fb_fnames = same_triplet[-1]
        return (fb_ver, fb_sha, fb_fnames)

    raise RuntimeError(
        f"Pinned core version '{pinned_version}' is unavailable and no active same-triplet release exists."
    )


class _BootstrapZipCollisionTracker:
    """Case-folding ancestor directory consistency and file/directory collision guard."""

    def __init__(self) -> None:
        self._dirs_by_folded: dict[str, tuple[str, str]] = {}
        self._files_by_folded: dict[str, str] = {}

    def register(self, parts: list[str], *, is_dir: bool, raw_name: str) -> None:
        dir_depth_end = len(parts) + 1 if is_dir else len(parts)
        for depth in range(1, dir_depth_end):
            dir_slice = parts[:depth]
            exact_dir = "/".join(dir_slice)
            folded_dir = "/".join(seg.casefold() for seg in dir_slice)
            prev_file = self._files_by_folded.get(folded_dir)
            if prev_file is not None:
                raise _BootstrapNonFallbackError(f"Archive file/directory path collision between {prev_file!r} and {raw_name!r}.")
            prev_dir = self._dirs_by_folded.get(folded_dir)
            if prev_dir is not None:
                prev_exact, prev_raw = prev_dir
                if prev_exact != exact_dir:
                    raise _BootstrapNonFallbackError(f"Case-inconsistent directory path between {prev_raw!r} and {raw_name!r}.")
            else:
                self._dirs_by_folded[folded_dir] = (exact_dir, raw_name)

        if not is_dir:
            folded_file = "/".join(seg.casefold() for seg in parts)
            if folded_file in self._files_by_folded:
                raise _BootstrapNonFallbackError(f"Duplicate or case-colliding archive entry: {raw_name!r}.")
            if folded_file in self._dirs_by_folded:
                raise _BootstrapNonFallbackError(f"Directory/file path collision on archive entry: {raw_name!r}.")
            self._files_by_folded[folded_file] = raw_name


def _validate_zip_member_segments(raw_filename: str) -> list[str]:
    if not raw_filename or any(ch in _WIN_ILLEGAL_ZIP_CHARS or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_filename):
        raise _BootstrapNonFallbackError(f"Illegal character or NTFS stream ':' in archive entry: {raw_filename!r}")
    if "\\" in raw_filename or raw_filename.startswith("/"):
        raise _BootstrapNonFallbackError(f"Absolute or backslash archive entry rejected: {raw_filename!r}")
    trimmed = raw_filename[:-1] if raw_filename.endswith("/") else raw_filename
    if not trimmed:
        raise _BootstrapNonFallbackError(f"Invalid root-only directory entry in archive: {raw_filename!r}")
    parts = trimmed.split("/")
    for seg in parts:
        if not seg or seg in (".", "..") or seg.endswith((".", " ")):
            raise _BootstrapNonFallbackError(f"Unsafe archive path segment rejected: {raw_filename!r}")
        stem = seg.split(".", 1)[0].rstrip(". ").lower()
        if stem in _WIN_RESERVED_STEMS:
            raise _BootstrapNonFallbackError(f"Reserved Windows device name in archive entry: {raw_filename!r}")
    return parts


def _validate_and_extract_zip(zip_bytes: bytes, staging_dir: Path) -> None:
    _assert_safe_local_path(staging_dir, allow_missing_leaf=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    tmp_zip = staging_dir.parent / f".core_dl_{os.getpid()}_{uuid.uuid4().hex[:8]}.zip"
    try:
        _atomic_write_bytes(tmp_zip, zip_bytes)
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_ZIP_ENTRIES:
                raise _BootstrapNonFallbackError(f"Archive entry count exceeds limit ({_MAX_ZIP_ENTRIES}).")
            collision_tracker = _BootstrapZipCollisionTracker()
            declared_total = 0
            for info in infos:
                if info.flag_bits & 0x1:
                    raise _BootstrapNonFallbackError(f"Encrypted archive entry rejected: {info.filename!r}")
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise _BootstrapNonFallbackError(f"Unsupported compression method {info.compress_type} on {info.filename!r}")
                parts = _validate_zip_member_segments(info.filename)
                is_dir_entry = info.is_dir() or info.filename.endswith("/")
                if not is_dir_entry and info.compress_type == zipfile.ZIP_STORED and info.file_size != info.compress_size:
                    raise _BootstrapNonFallbackError(f"Mismatched stored archive size on {info.filename!r}")
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(unix_mode) or stat.S_ISFIFO(unix_mode) or stat.S_ISCHR(unix_mode) or stat.S_ISBLK(unix_mode) or stat.S_ISSOCK(unix_mode):
                    raise _BootstrapNonFallbackError(f"Special or symlink archive entry rejected: {info.filename!r}")
                if info.create_system == 0 and (info.external_attr & _FILE_ATTRIBUTE_REPARSE_POINT) != 0:
                    raise _BootstrapNonFallbackError(f"Windows reparse point archive entry rejected: {info.filename!r}")
                collision_tracker.register(parts, is_dir=is_dir_entry, raw_name=info.filename)
                if not is_dir_entry:
                    if info.file_size > _MAX_ZIP_SINGLE_BYTES:
                        raise _BootstrapNonFallbackError(f"Archive entry {info.filename!r} exceeds single-file size limit.")
                    declared_total += max(0, info.file_size)
                    if declared_total > _MAX_ZIP_TOTAL_BYTES:
                        raise _BootstrapNonFallbackError("Archive uncompressed size exceeds safety ceiling.")

            resolved_root = staging_dir.resolve()
            actual_total_bytes = 0
            for info in infos:
                parts = _validate_zip_member_segments(info.filename)
                if not parts:
                    continue
                is_dir_entry = info.is_dir() or info.filename.endswith("/")
                raw_target = staging_dir.joinpath(*parts)
                _assert_safe_local_path(raw_target, allow_missing_leaf=True)
                target_p = raw_target.resolve()
                if resolved_root not in target_p.parents and target_p != resolved_root:
                    raise _BootstrapNonFallbackError(f"Archive member escaped staging root: {info.filename!r}")
                if is_dir_entry:
                    target_p.mkdir(parents=True, exist_ok=True)
                    continue
                target_p.parent.mkdir(parents=True, exist_ok=True)
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                file_mode = 0o755 if (os.name != "nt" and bool(unix_mode & 0o111)) else 0o644
                fd = os.open(str(target_p), _NOFOLLOW_EXCL_WRITE_FLAGS, file_mode)
                try:
                    if os.name != "nt" and file_mode == 0o755:
                        try:
                            os.fchmod(fd, 0o755)
                        except OSError:
                            pass
                    dst_f = os.fdopen(fd, "wb")
                except BaseException:
                    os.close(fd)
                    raise
                entry_bytes = 0
                with dst_f, zf.open(info, "r") as src_f:
                    while True:
                        chunk = src_f.read(65536)
                        if not chunk:
                            break
                        entry_bytes += len(chunk)
                        actual_total_bytes += len(chunk)
                        if entry_bytes > _MAX_ZIP_SINGLE_BYTES:
                            raise _BootstrapNonFallbackError(f"Decompressed archive entry {info.filename!r} exceeded {_MAX_ZIP_SINGLE_BYTES} bytes.")
                        if actual_total_bytes > _MAX_ZIP_TOTAL_BYTES:
                            raise _BootstrapNonFallbackError(f"Decompressed archive exceeded {_MAX_ZIP_TOTAL_BYTES} total bytes.")
                        if entry_bytes >= _ZIP_RATIO_CHECK_MIN_BYTES and (
                            info.compress_size <= 0
                            or entry_bytes > info.compress_size * _MAX_ZIP_COMPRESSION_RATIO
                        ):
                            raise _BootstrapNonFallbackError(f"Archive entry {info.filename!r} exceeded {_MAX_ZIP_COMPRESSION_RATIO}:1 compression ratio.")
                        dst_f.write(chunk)
    except (zlib.error, EOFError, NotImplementedError) as exc:
        raise _BootstrapNonFallbackError(f"Corrupted archive stream: {exc}") from exc
    finally:
        if tmp_zip.exists():
            try:
                tmp_zip.unlink()
            except OSError:
                pass


def _deploy_configurable_templates(staging_dir: Path, yscb_root: Path) -> None:
    cfg_src = staging_dir / "configurable"
    if cfg_src.is_dir() and not _is_reparse_or_symlink(cfg_src):
        cfg_dst_root = yscb_root / "config" / "core"
        _assert_safe_local_path(cfg_dst_root, allow_missing_leaf=True)
        for tmpl_file in sorted(cfg_src.rglob("*")):
            if not tmpl_file.is_file() or _is_reparse_or_symlink(tmpl_file):
                continue
            rel_p = tmpl_file.relative_to(cfg_src).as_posix()
            out_rel = rel_p[:-5] if rel_p.endswith(".tmpl") else rel_p
            if not out_rel or out_rel.endswith("/"):
                raise _BootstrapNonFallbackError(
                    f"Invalid configurable template target derived from '{rel_p}'."
                )
            out_parts = _validate_zip_member_segments(out_rel)
            if not out_parts:
                raise _BootstrapNonFallbackError(
                    f"Invalid configurable template target derived from '{rel_p}'."
                )
            dest_p = cfg_dst_root.joinpath(*out_parts)
            _assert_safe_local_path(dest_p, allow_missing_leaf=True)
            if not dest_p.exists():
                _atomic_write_bytes(dest_p, _read_nofollow_regular_bytes(tmpl_file, _MAX_JSON_BYTES))
        _rmtree_safe(cfg_src)

    ignore_marker = staging_dir / ".yscbignore"
    if os.path.lexists(ignore_marker):
        _rmtree_safe(ignore_marker, ignore_errors=True)
    for stray_tmpl in sorted(staging_dir.rglob("*.tmpl")):
        if stray_tmpl.is_file() and not _is_reparse_or_symlink(stray_tmpl):
            stray_tmpl.unlink(missing_ok=True)


def _has_cached_mirror_archive(
    mirror_core_dir: Path,
    canon_ver: str,
    rec_obj: Optional[Mapping[str, object]],
) -> bool:
    cand_names: list[str] = []
    if isinstance(rec_obj, Mapping):
        raw_fn = rec_obj.get("filename") or rec_obj.get("archive")
        if type(raw_fn) is str and raw_fn.strip():
            try:
                cand_names.append(_validate_safe_archive_name(raw_fn))
            except RuntimeError:
                return False
    try:
        std_fn = _validate_safe_archive_name(f"{canon_ver}.zip")
        if std_fn not in cand_names:
            cand_names.append(std_fn)
    except RuntimeError:
        pass
    for fn in cand_names:
        zp = mirror_core_dir / fn
        if zp.is_file() and not _is_reparse_or_symlink(zp):
            return True
    return False


def _persist_verified_core_mirror(
    mirror_core_dir: Path,
    idx_doc: Mapping[str, object],
    selected_ver: str,
    archive_name: str,
    zip_bytes: bytes,
    actual_sha: str,
) -> None:
    mirror_core_dir.mkdir(parents=True, exist_ok=True)
    std_zip_name = f"{selected_ver}.zip"
    _atomic_write_bytes(mirror_core_dir / std_zip_name, zip_bytes)
    _atomic_write_bytes(
        mirror_core_dir / f"{std_zip_name}.sha256",
        f"{actual_sha}  {std_zip_name}\n".encode("utf-8"),
    )
    if archive_name != std_zip_name:
        _atomic_write_bytes(mirror_core_dir / archive_name, zip_bytes)
        _atomic_write_bytes(
            mirror_core_dir / f"{archive_name}.sha256",
            f"{actual_sha}  {archive_name}\n".encode("utf-8"),
        )

    try:
        prev_idx = _read_json_file(mirror_core_dir / "index.json")
    except (OSError, ValueError, RuntimeError):
        prev_idx = None

    merged_rels: dict[str, object] = {}
    version_map: dict[str, _BootSemVer4] = {}
    if isinstance(prev_idx, Mapping):
        prev_rels = prev_idx.get("releases")
        if isinstance(prev_rels, Mapping):
            for raw_k, raw_v in prev_rels.items():
                if type(raw_k) is not str or not isinstance(raw_v, Mapping):
                    continue
                try:
                    sv_k = _parse_semver4(raw_k)
                except ValueError:
                    continue
                canon_k = sv_k.canonical_str()
                if canon_k != selected_ver and _has_cached_mirror_archive(mirror_core_dir, canon_k, raw_v):
                    kept_rec = dict(raw_v)
                    kept_rec["version"] = canon_k
                    merged_rels[canon_k] = kept_rec
                    version_map[canon_k] = sv_k
        prev_vers = prev_idx.get("versions")
        if isinstance(prev_vers, list):
            for item_v in prev_vers:
                if type(item_v) is not str:
                    continue
                try:
                    sv_v = _parse_semver4(item_v)
                except ValueError:
                    continue
                canon_v = sv_v.canonical_str()
                if canon_v != selected_ver and (
                    canon_v in merged_rels or _has_cached_mirror_archive(mirror_core_dir, canon_v, None)
                ):
                    version_map[canon_v] = sv_v

    remote_rels = idx_doc.get("releases")
    remote_src: Optional[Mapping[str, object]] = None
    if isinstance(remote_rels, Mapping):
        cand_direct = remote_rels.get(selected_ver)
        if isinstance(cand_direct, Mapping):
            remote_src = cand_direct
        else:
            for rk, rv in remote_rels.items():
                if type(rk) is not str or not isinstance(rv, Mapping):
                    continue
                try:
                    if _parse_semver4(rk).canonical_str() == selected_ver:
                        remote_src = rv
                        break
                except ValueError:
                    continue

    cur_rec: dict[str, object] = {}
    if isinstance(remote_src, Mapping):
        for allowed_k in ("dependencies", "urgency", "type", "summary"):
            if allowed_k in remote_src:
                cur_rec[allowed_k] = remote_src[allowed_k]
    cur_rec["version"] = selected_ver
    cur_rec["sha256"] = actual_sha
    cur_rec["filename"] = std_zip_name
    cur_rec["status"] = "active"
    cur_rec["yanked"] = False
    merged_rels[selected_ver] = cur_rec
    version_map[selected_ver] = _parse_semver4(selected_ver)

    sorted_vers = [k for k, _sv in sorted(version_map.items(), key=lambda item: item[1])]
    mirror_idx: dict[str, object] = {
        "module_id": "core",
        "versions": sorted_vers,
        "releases": merged_rels,
    }
    _atomic_write_json(mirror_core_dir / "index.json", mirror_idx)


def _deploy_core_from_provider(
    host_dir: Path,
    yscb_root: Path,
    provider: str,
    *,
    pinned_version: Optional[str],
    ignore_sha256: bool = False,
) -> str:
    _assert_safe_local_path(yscb_root, allow_missing_leaf=True)
    idx_loc = _join_provider_subpath(provider, "core", "index.json")
    idx_bytes = _fetch_bytes_from_source(idx_loc, host_dir, _MAX_JSON_BYTES)
    try:
        idx_doc = _loads_strict_json(idx_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _BootstrapPayloadFormatError(f"Malformed core/index.json payload: {exc}") from exc
    if not isinstance(idx_doc, dict):
        raise _BootstrapPayloadFormatError("Invalid core/index.json: root must be a JSON object.")

    selected_ver, expected_sha, archive_names = _select_core_release_from_index(idx_doc, pinned_version)
    zip_bytes: Optional[bytes] = None
    archive_name = archive_names[0]
    zip_loc = _join_provider_subpath(provider, "core", archive_name)
    last_fetch_exc: Optional[BaseException] = None
    for cand_arc in archive_names:
        cand_loc = _join_provider_subpath(provider, "core", cand_arc)
        try:
            zip_bytes = _fetch_bytes_from_source(cand_loc, host_dir, _MAX_ZIP_BYTES)
            archive_name = cand_arc
            zip_loc = cand_loc
            break
        except (FileNotFoundError, HTTPError) as exc:
            if isinstance(exc, HTTPError) and exc.code != 404:
                raise
            last_fetch_exc = exc
            continue
    if zip_bytes is None:
        if last_fetch_exc is not None:
            raise last_fetch_exc
        raise RuntimeError(f"Core archive not found for version {selected_ver}.")
    actual_sha = hashlib.sha256(zip_bytes).hexdigest().lower()

    if not ignore_sha256:
        if expected_sha is None:
            sha_loc = f"{zip_loc}.sha256"
            try:
                sha_raw = _fetch_bytes_from_source(sha_loc, host_dir, 4096).decode("utf-8").strip()
            except UnicodeDecodeError as exc:
                raise _BootstrapPayloadFormatError(f"Malformed core sha256 sidecar: {exc}") from exc
            expected_sha = sha_raw.split()[0].lower() if sha_raw else ""
        if not expected_sha or actual_sha != expected_sha.lower():
            raise _BootstrapNonFallbackError(
                f"SHA-256 mismatch for core {selected_ver}: expected {expected_sha!r}, got {actual_sha!r}"
            )

    modules_dir = yscb_root / ".modules"
    _assert_safe_local_path(modules_dir, allow_missing_leaf=True)
    modules_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = modules_dir / f".staging_core_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    backup_dir = modules_dir / f".backup_core_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    target_dir = modules_dir / "core"
    inner_tmp: Optional[Path] = None

    try:
        _validate_and_extract_zip(zip_bytes, staging_dir)
        mf_path = staging_dir / "manifest.json"
        if not mf_path.is_file():
            nested_core = staging_dir / "core"
            if (nested_core / "manifest.json").is_file():
                inner_tmp = modules_dir / f".inner_core_{os.getpid()}_{uuid.uuid4().hex[:8]}"
                _replace_with_nt_retry(nested_core, inner_tmp)
                _rmtree_safe(staging_dir)
                _replace_with_nt_retry(inner_tmp, staging_dir)
                inner_tmp = None
                mf_path = staging_dir / "manifest.json"
        if not mf_path.is_file():
            raise _BootstrapNonFallbackError("Extracted core archive is missing manifest.json.")
        if not _is_installed_core_healthy(staging_dir, selected_ver):
            raise _BootstrapNonFallbackError(f"Extracted core archive failed health or version check for {selected_ver}.")

        _deploy_configurable_templates(staging_dir, yscb_root)

        mirror_root = yscb_root / ".mirror"
        mirror_core_dir = mirror_root / "core"
        _assert_safe_local_path(mirror_core_dir, allow_missing_leaf=True)
        is_from_same_mirror = False
        if not provider.strip().lower().startswith(("http://", "https://", "file://")):
            prov_cand = Path(provider.strip())
            prov_resolved = (prov_cand if prov_cand.is_absolute() else (host_dir / prov_cand)).resolve()
            is_from_same_mirror = prov_resolved == mirror_root.resolve()
        if not is_from_same_mirror:
            _persist_verified_core_mirror(
                mirror_core_dir,
                idx_doc,
                selected_ver,
                archive_name,
                zip_bytes,
                actual_sha,
            )

        ep_probe = yscb_root / ".cache" / "daemon" / "daemon.json"
        _assert_safe_local_path(ep_probe, allow_missing_leaf=True)
        if ep_probe.is_file() and not _is_reparse_or_symlink(ep_probe):
            _try_stop_online_daemon_after_core_fix(yscb_root, staging_dir)

        if _is_reparse_or_symlink(target_dir):
            _rmtree_safe(target_dir)
        elif target_dir.exists():
            _assert_safe_local_path(target_dir)
            _replace_with_nt_retry(target_dir, backup_dir)
        try:
            _replace_with_nt_retry(staging_dir, target_dir)
        except BaseException:
            if backup_dir.exists() and not target_dir.exists():
                _replace_with_nt_retry(backup_dir, target_dir)
            raise
        if backup_dir.exists():
            _rmtree_safe(backup_dir, ignore_errors=True)
    finally:
        if inner_tmp is not None and inner_tmp.exists():
            _rmtree_safe(inner_tmp, ignore_errors=True)
        if staging_dir.exists():
            _rmtree_safe(staging_dir, ignore_errors=True)

    return selected_ver


def _load_host_configs(
    host_dir: Path,
    *,
    tolerate_corrupt: bool = False,
) -> tuple[Optional[dict[str, object]], Optional[dict[str, object]]]:
    try:
        base_cfg = _read_json_file(host_dir / HOST_CONFIG_FILENAME)
    except ValueError as exc:
        if not tolerate_corrupt:
            msg = str(exc)
            raise ValueError(msg if HOST_CONFIG_FILENAME in msg else f"{HOST_CONFIG_FILENAME}: {msg}") from exc
        base_cfg = None
    try:
        local_cfg = _read_json_file(host_dir / HOST_LOCAL_CONFIG_FILENAME)
    except ValueError as exc:
        if not tolerate_corrupt:
            msg = str(exc)
            raise ValueError(msg if HOST_LOCAL_CONFIG_FILENAME in msg else f"{HOST_LOCAL_CONFIG_FILENAME}: {msg}") from exc
        local_cfg = None
    return (base_cfg, local_cfg)


def _try_extract_safe_yscb_root_rel(
    cfg_doc: Optional[Mapping[str, object]],
    host_dir: Path,
    *,
    tolerate_invalid: bool,
) -> Optional[str]:
    if not isinstance(cfg_doc, Mapping) or "yscb_root" not in cfg_doc:
        return None
    raw_v = cfg_doc.get("yscb_root")
    if type(raw_v) is not str:
        return None
    cand = raw_v.strip()
    if not cand:
        return None
    if not tolerate_invalid:
        return cand
    try:
        _ = _resolve_yscb_root_path(host_dir, cand)
        return cand
    except (OSError, ValueError, RuntimeError):
        return None


def _sanitize_local_host_config_for_fix(
    latest_local: Optional[dict[str, object]],
    host_dir: Path,
    *,
    explicit_yscb_root_rel: Optional[str],
    explicit_provider: Optional[str] = None,
) -> dict[str, object]:
    if latest_local is None:
        return {}
    cleaned: dict[str, object] = {
        k: v for k, v in latest_local.items() if k in ("yscb_root", "default_provider")
    }
    if "yscb_root" in cleaned:
        if explicit_yscb_root_rel is not None or _try_extract_safe_yscb_root_rel(cleaned, host_dir, tolerate_invalid=True) is None:
            cleaned.pop("yscb_root", None)
    if "default_provider" in cleaned:
        raw_lp = cleaned["default_provider"]
        if (
            explicit_provider is not None
            or type(raw_lp) is not str
            or not raw_lp.strip()
            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw_lp)
        ):
            cleaned.pop("default_provider", None)
        else:
            try:
                cleaned["default_provider"] = _normalize_bootstrap_local_source(raw_lp, host_dir, host_dir)
            except (OSError, ValueError, RuntimeError):
                cleaned.pop("default_provider", None)
    return cleaned


def _extract_config_str_field(
    cfg_doc: Optional[Mapping[str, object]],
    key: str,
    *,
    label: str,
    tolerate_invalid: bool = False,
) -> str:
    if not isinstance(cfg_doc, Mapping) or key not in cfg_doc:
        return ""
    raw_v = cfg_doc[key]
    if raw_v is None:
        return ""
    if type(raw_v) is str:
        return raw_v.strip()
    if tolerate_invalid:
        return ""
    raise _BootstrapConfigTypeError(
        f"Configuration field '{label}' must be a string or null, got {type(raw_v).__name__}."
    )


def _extract_core_install_record(
    base_cfg: Optional[Mapping[str, object]],
    *,
    tolerate_invalid: bool = False,
) -> Optional[Mapping[str, object]]:
    if not isinstance(base_cfg, Mapping) or "installed_modules" not in base_cfg:
        return None
    raw_im = base_cfg["installed_modules"]
    if raw_im is None:
        return None
    if not isinstance(raw_im, Mapping):
        if tolerate_invalid:
            return None
        raise _BootstrapConfigTypeError("Configuration field 'installed_modules' must be a JSON object.")
    if "core" not in raw_im or raw_im["core"] is None:
        return None
    raw_core = raw_im["core"]
    if not isinstance(raw_core, Mapping):
        if tolerate_invalid:
            return None
        raise _BootstrapConfigTypeError("Configuration field 'installed_modules.core' must be a JSON object.")
    return raw_core


def _extract_strict_yscb_root_rel(
    base_cfg: Optional[Mapping[str, object]],
    local_cfg: Optional[Mapping[str, object]],
) -> str:
    for cfg_src in (local_cfg, base_cfg):
        if isinstance(cfg_src, Mapping) and "yscb_root" in cfg_src:
            raw_v = cfg_src["yscb_root"]
            if type(raw_v) is not str or not raw_v.strip():
                raise ValueError("Configuration field 'yscb_root' must be a non-empty string.")
            return raw_v.strip()
    return DEFAULT_YSCB_ROOT_REL


def _resolve_yscb_root_path(host_dir: Path, raw_yscb_root: str) -> Path:
    cand = Path(raw_yscb_root.strip() or DEFAULT_YSCB_ROOT_REL)
    if (cand.drive or cand.anchor) and not cand.is_absolute():
        raise _BootstrapSecurityError(f"Refusing half-qualified drive or root-relative yscb_root: {raw_yscb_root!r}")
    if not cand.is_absolute() and any(seg == ".." or ":" in seg for seg in cand.parts):
        raise _BootstrapSecurityError(f"Refusing parent-traversing relative yscb_root: {raw_yscb_root!r}")
    raw_target = cand if cand.is_absolute() else (host_dir / cand)
    _assert_safe_local_path(raw_target, allow_missing_leaf=True)
    resolved = raw_target.resolve()
    _assert_safe_local_path(resolved, allow_missing_leaf=True)
    return resolved


def _normalize_bootstrap_local_source(raw_source: str, host_dir: Path, caller_cwd: Path) -> str:
    clean = raw_source.strip()
    if not clean:
        return ""
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in clean):
        raise _BootstrapSecurityError(f"Control characters forbidden in bootstrap source: {raw_source!r}")
    lower = clean.lower()
    if lower.startswith(("http://", "https://")):
        _validate_http_url(clean)
        return clean
    if lower.startswith("file://"):
        parsed_u = urlparse(clean)
        if (parsed_u.netloc or "").lower() not in ("", "localhost", "127.0.0.1", "[::1]"):
            raise _BootstrapSecurityError(f"Refusing non-local file:// authority '{parsed_u.netloc}': {clean}")
        if parsed_u.params or parsed_u.query or parsed_u.fragment:
            raise _BootstrapNonFallbackError(f"Malformed file:// URL with query/fragment: {clean}")
        raw_u_path = parsed_u.path
        if os.name == "nt":
            if raw_u_path.startswith("//"):
                raise _BootstrapSecurityError(f"Refusing UNC file:// path in bootstrapper: {clean}")
            dec_u_path = unquote(raw_u_path)
            if (
                "\x00" in dec_u_path
                or "|" in dec_u_path
                or re.match(r"^/[A-Za-z]:/", dec_u_path) is None
                or ":" in dec_u_path[3:]
            ):
                raise _BootstrapSecurityError(f"Invalid Windows drive file:// path in bootstrapper: {clean}")
        elif raw_u_path.startswith("//"):
            raw_u_path = "/" + raw_u_path.lstrip("/")
        local_u_p = Path(urllib.request.url2pathname(raw_u_path))
        if not local_u_p.is_absolute():
            raise _BootstrapSecurityError(f"Refusing non-absolute file:// URL path: {clean}")
        _assert_safe_local_path(local_u_p, allow_missing_leaf=True)
        _assert_safe_local_path(local_u_p.resolve(), allow_missing_leaf=True)
        return clean
    cand = Path(clean)
    if (cand.drive or cand.anchor) and not cand.is_absolute():
        raise _BootstrapSecurityError(f"Refusing half-qualified drive or root-relative bootstrap source: {clean}")
    if cand.is_absolute():
        _assert_safe_local_path(cand, allow_missing_leaf=True)
        _assert_safe_local_path(cand.resolve(), allow_missing_leaf=True)
        return clean
    if caller_cwd == host_dir:
        cand_from_host = host_dir / cand
        _assert_safe_local_path(cand_from_host, allow_missing_leaf=True)
        _assert_safe_local_path(cand_from_host.resolve(), allow_missing_leaf=True)
        return clean
    cand_from_cwd = caller_cwd / cand
    _assert_safe_local_path(cand_from_cwd, allow_missing_leaf=True)
    resolved_src = cand_from_cwd.resolve()
    _assert_safe_local_path(resolved_src, allow_missing_leaf=True)
    try:
        rel_inside = resolved_src.relative_to(host_dir).as_posix()
        return f"./{rel_inside}" if rel_inside != "." else "./"
    except ValueError:
        return str(resolved_src)


_ISOLATED_DAEMON_STOP_SNIPPET: Final[str] = (
    "from pathlib import Path; import sys; "
    "from core.execution.daemon import DaemonStopControl, query_daemon_control; "
    "from core.execution.rpc import FrameKind, probe_daemon_endpoint; "
    "from core.foundation import DataclassCodec, HostPath; "
    "r = HostPath(Path(sys.argv[1])); c = HostPath(Path(sys.argv[1]) / '.cache'); "
    "p = DataclassCodec.encode_object(DaemonStopControl(force=False, core_handoff=False)); "
    "(query_daemon_control(c, r, FrameKind.CONTROL_STOP, p, timeout_ms=3000) "
    "if probe_daemon_endpoint(c, r) is not None else None)"
)


def _is_pid_alive_bootstrap(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_proc = kernel32.OpenProcess
        open_proc.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_proc.restype = wintypes.HANDLE
        wait_single = kernel32.WaitForSingleObject
        wait_single.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait_single.restype = wintypes.DWORD
        close_h = kernel32.CloseHandle
        close_h.argtypes = (wintypes.HANDLE,)
        close_h.restype = wintypes.BOOL
        handle = open_proc(0x00100000 | 0x00001000, False, pid)
        if not handle:
            return int(ctypes.get_last_error()) == 5
        try:
            wait_rc = wait_single(handle, 0)
            return int(wait_rc) == 0x00000102
        finally:
            close_h(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _remove_stale_daemon_endpoint_if_safe(ep_file: Path) -> None:
    _assert_safe_local_path(ep_file, allow_missing_leaf=True)
    if os.path.lexists(ep_file) and not _is_reparse_or_symlink(ep_file):
        try:
            ep_file.unlink(missing_ok=True)
        except OSError:
            pass


def _try_stop_online_daemon_after_core_fix(yscb_root: Path, verified_core_dir: Optional[Path] = None) -> None:
    ep_file = yscb_root / ".cache" / "daemon" / "daemon.json"
    _assert_safe_local_path(ep_file, allow_missing_leaf=True)
    if not ep_file.is_file() or _is_reparse_or_symlink(ep_file):
        return
    old_pid = 0
    try:
        ep_doc = _read_json_file(ep_file)
        if isinstance(ep_doc, Mapping) and type(ep_doc.get("pid")) is int:
            old_pid = int(ep_doc["pid"])
    except _BootstrapNonFallbackError:
        raise
    except (OSError, ValueError, RuntimeError):
        old_pid = 0
    if old_pid <= 0 or not _is_pid_alive_bootstrap(old_pid):
        _remove_stale_daemon_endpoint_if_safe(ep_file)
        return
    eff_core = verified_core_dir if verified_core_dir is not None else (yscb_root / ".modules" / "core")
    if not eff_core.is_dir() or _is_reparse_or_symlink(eff_core):
        return
    sub_env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    sub_env["PYTHONPATH"] = str(eff_core.resolve())
    sub_env["PYTHONUTF8"] = "1"
    sub_env["PYTHONIOENCODING"] = "utf-8"
    sub_env["PYTHONDONTWRITEBYTECODE"] = "1"
    sub_env["PYTHONNOUSERSITE"] = "1"
    sub_env["PYTHONSAFEPATH"] = "1"
    safe_path_flags = ("-P",) if sys.version_info >= (3, 11) else ()
    win_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        _ = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                "-s",
                *safe_path_flags,
                "-c",
                _ISOLATED_DAEMON_STOP_SNIPPET,
                str(yscb_root),
            ],
            cwd=str(yscb_root),
            stdin=subprocess.DEVNULL,
            env=sub_env,
            capture_output=True,
            timeout=5.0,
            check=False,
            creationflags=win_flags,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    wait_deadline = time.monotonic() + 4.0
    while time.monotonic() < wait_deadline:
        ep_gone = not os.path.lexists(ep_file)
        pid_gone = old_pid <= 0 or not _is_pid_alive_bootstrap(old_pid)
        if pid_gone:
            if not ep_gone:
                _remove_stale_daemon_endpoint_if_safe(ep_file)
            break
        time.sleep(0.025)


def _handle_init(
    argv: Sequence[str],
    host_dir: Path,
    caller_cwd: Path,
    *,
    json_mode: bool = False,
) -> int:
    provider_arg: Optional[str] = None
    yscb_root_rel: Optional[str] = None
    fix_mode = False
    ignore_sha = False
    allow_mutation = False

    idx = 0
    while idx < len(argv):
        tok = argv[idx]
        if tok == "--":
            if idx + 1 < len(argv):
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg=f"Unexpected positional argument for 'yscb init': {argv[idx + 1]}",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            break
        if tok in ("-h", "--help"):
            return _emit_bootstrap_help(
                "Usage: yscb init [--provider=<url_or_path>] [--yscb-root=<rel>] [--fix] [--ignore-sha256] [--allow-bootstrap-mutation]\n",
                ["init"],
                json_mode=json_mode,
            )
        if tok in ("--json", "--cold"):
            idx += 1
            continue
        if tok == "--fix":
            fix_mode = True
            idx += 1
            continue
        if tok == "--ignore-sha256":
            ignore_sha = True
            idx += 1
            continue
        if tok == "--allow-bootstrap-mutation":
            allow_mutation = True
            idx += 1
            continue
        if tok.startswith("--provider="):
            val = tok.split("=", 1)[1].strip()
            if not val:
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--provider' requires a non-empty value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            provider_arg = val
            idx += 1
            continue
        if tok == "--provider":
            if idx + 1 >= len(argv) or not argv[idx + 1].strip() or argv[idx + 1].strip().startswith("-"):
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--provider' requires a non-empty value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            provider_arg = argv[idx + 1].strip()
            idx += 2
            continue
        if tok.startswith("--yscb-root="):
            val = tok.split("=", 1)[1].strip()
            if not val:
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--yscb-root' requires a non-empty value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            yscb_root_rel = val
            idx += 1
            continue
        if tok == "--yscb-root":
            if idx + 1 >= len(argv) or not argv[idx + 1].strip() or argv[idx + 1].strip().startswith("-"):
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--yscb-root' requires a non-empty value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            yscb_root_rel = argv[idx + 1].strip()
            idx += 2
            continue
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Unknown option for 'yscb init': {tok}",
            error_code="codec_validation_failed",
            exit_code=2,
        )

    if fix_mode:
        gate_rc = _check_bootstrap_mutation_gate(
            "yscb init --fix",
            allow_mutation=allow_mutation,
            json_mode=json_mode,
        )
        if gate_rc is not None:
            return gate_rc

    cfg_path = host_dir / HOST_CONFIG_FILENAME
    try:
        existing, local_cfg = _load_host_configs(host_dir, tolerate_corrupt=fix_mode)
    except _BootstrapSecurityError as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Unsafe host configuration path: {exc}",
            error_code="security_gated",
            exit_code=4,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Error reading host configuration: {exc}",
            error_code="config_invalid",
            exit_code=1,
        )

    if existing is not None and not fix_mode and (
        provider_arg is not None or yscb_root_rel is not None or ignore_sha
    ):
        gate_rc = _check_bootstrap_mutation_gate(
            "yscb init (overwrite existing workspace)",
            allow_mutation=allow_mutation,
            json_mode=json_mode,
        )
        if gate_rc is not None:
            return gate_rc

    if not fix_mode and (existing is not None or local_cfg is not None):
        try:
            if yscb_root_rel is None:
                _ = _extract_strict_yscb_root_rel(existing, local_cfg)
            _ = _extract_config_str_field(existing, "default_provider", label="default_provider")
            _ = _extract_config_str_field(local_cfg, "default_provider", label="local.default_provider")
            chk_core_rec = _extract_core_install_record(existing)
            _ = _extract_config_str_field(chk_core_rec, "version", label="installed_modules.core.version")
            _ = _extract_config_str_field(chk_core_rec, "provider", label="installed_modules.core.provider")
        except ValueError as exc:
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=f"Invalid host configuration: {exc}",
                error_code="config_invalid",
                exit_code=1,
            )

    if existing is not None and not fix_mode and provider_arg is None and yscb_root_rel is None:
        try:
            raw_root = _extract_strict_yscb_root_rel(existing, local_cfg)
            yscb_root = _resolve_yscb_root_path(host_dir, raw_root)
            core_rec_chk = _extract_core_install_record(existing)
            pinned_chk = _extract_config_str_field(core_rec_chk, "version", label="installed_modules.core.version")
            local_prov_chk = _extract_config_str_field(local_cfg, "default_provider", label="local.default_provider")
            core_prov_chk = _extract_config_str_field(core_rec_chk, "provider", label="installed_modules.core.provider")
            base_prov_chk = _extract_config_str_field(existing, "default_provider", label="default_provider")
        except _BootstrapSecurityError as exc:
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=f"Unsafe workspace root: {exc}",
                error_code="security_gated",
                exit_code=4,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=f"Unsafe workspace root: {exc}",
                error_code="config_invalid",
                exit_code=1,
            )
        prov_chk = local_prov_chk or core_prov_chk or base_prov_chk
        existing_core_dir = yscb_root / ".modules" / "core"
        if pinned_chk and prov_chk and _is_installed_core_healthy(existing_core_dir, pinned_chk):
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=True,
                human_msg=f"Workspace already initialized at {yscb_root} (pass --fix to repair).",
                value={"yscb_root": str(yscb_root), "already_initialized": True},
                exit_code=0,
            )
        if not prov_chk:
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=(
                    f"Existing {HOST_CONFIG_FILENAME} is missing a valid provider for 'core'. "
                    "Pass '--fix' or '--provider=<url_or_path>' to repair."
                ),
                error_code="config_invalid",
                remediation="Run 'python yscb.py init --fix --provider=<url_or_path>'.",
                exit_code=1,
            )

    persisted_root_rel = (
        yscb_root_rel
        or _try_extract_safe_yscb_root_rel(existing, host_dir, tolerate_invalid=fix_mode)
        or DEFAULT_YSCB_ROOT_REL
    )
    eff_root_rel = (
        yscb_root_rel
        or _try_extract_safe_yscb_root_rel(local_cfg, host_dir, tolerate_invalid=fix_mode)
        or persisted_root_rel
    )
    norm_provider_arg: Optional[str] = None
    if provider_arg is not None:
        try:
            norm_provider_arg = _normalize_bootstrap_local_source(provider_arg, host_dir, caller_cwd)
        except _BootstrapSecurityError as exc:
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=f"Unsafe provider path '{provider_arg}': {exc}",
                error_code="security_gated",
                exit_code=4,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=f"Invalid provider '{provider_arg}': {exc}",
                error_code="package_integrity_error",
                exit_code=1,
            )
    offline_active = os.environ.get("YSCB_OFFLINE", "").strip().lower() in _TRUTHY_OFFLINE_VALUES

    def _sanitize_provider_for_fix(raw_prov: str) -> str:
        if not raw_prov:
            return ""
        if not fix_mode:
            return raw_prov
        try:
            return _normalize_bootstrap_local_source(raw_prov, host_dir, host_dir)
        except (OSError, ValueError, RuntimeError):
            return ""

    def _compute_init_providers(
        base_doc: Optional[Mapping[str, object]],
        loc_doc: Optional[Mapping[str, object]],
    ) -> tuple[str, str, str]:
        base_dflt = _sanitize_provider_for_fix(
            _extract_config_str_field(
                base_doc,
                "default_provider",
                label="default_provider",
                tolerate_invalid=fix_mode,
            )
        )
        raw_c_d = _extract_core_install_record(base_doc, tolerate_invalid=fix_mode)
        core_prov = _sanitize_provider_for_fix(
            _extract_config_str_field(
                raw_c_d,
                "provider",
                label="installed_modules.core.provider",
                tolerate_invalid=fix_mode,
            )
        )
        loc_dflt = _sanitize_provider_for_fix(
            _extract_config_str_field(
                loc_doc,
                "default_provider",
                label="local.default_provider",
                tolerate_invalid=fix_mode,
            )
        )
        allow_fallback = (base_doc is None) or fix_mode
        fallback_url = DEFAULT_PROVIDER_URL if allow_fallback else ""
        top_persisted = norm_provider_arg or base_dflt or core_prov or fallback_url
        core_persisted = norm_provider_arg or core_prov or base_dflt or fallback_url
        fetch_eff = norm_provider_arg or loc_dflt or core_prov or base_dflt or fallback_url
        return (top_persisted, core_persisted, fetch_eff)

    try:
        yscb_root = _resolve_yscb_root_path(host_dir, eff_root_rel)
        for _lock_attempt in range(3):
            with _bootstrap_exclusive_lock(yscb_root):
                latest_existing, latest_local = _load_host_configs(host_dir, tolerate_corrupt=fix_mode)
                sanitized_local: dict[str, object] = {}
                eff_local_for_init: Optional[Mapping[str, object]] = latest_local
                if fix_mode:
                    sanitized_local = _sanitize_local_host_config_for_fix(
                        latest_local,
                        host_dir,
                        explicit_yscb_root_rel=yscb_root_rel,
                        explicit_provider=norm_provider_arg,
                    )
                    eff_local_for_init = sanitized_local
                persisted_root_rel = (
                    yscb_root_rel
                    or _try_extract_safe_yscb_root_rel(latest_existing, host_dir, tolerate_invalid=fix_mode)
                    or DEFAULT_YSCB_ROOT_REL
                )
                locked_eff_root_rel = (
                    yscb_root_rel
                    or _try_extract_safe_yscb_root_rel(eff_local_for_init, host_dir, tolerate_invalid=fix_mode)
                    or persisted_root_rel
                )
                locked_yscb_root = _resolve_yscb_root_path(host_dir, locked_eff_root_rel)
                if locked_yscb_root != yscb_root:
                    if _lock_attempt < 2:
                        yscb_root = locked_yscb_root
                        continue
                    raise RuntimeError(
                        "Workspace yscb_root changed concurrently during bootstrap lock acquisition; retry command."
                    )
                persisted_provider, persisted_core_provider, eff_provider = _compute_init_providers(
                    latest_existing,
                    eff_local_for_init,
                )
                pinned_core_ver: Optional[str] = None
                if not fix_mode and latest_existing is not None:
                    raw_inst_lk = latest_existing.get("installed_modules")
                    raw_core_lk = raw_inst_lk.get("core") if isinstance(raw_inst_lk, Mapping) else None
                    if isinstance(raw_core_lk, Mapping) and type(raw_core_lk.get("version")) is str:
                        cand_ver = str(raw_core_lk["version"]).strip()
                        if cand_ver:
                            pinned_core_ver = cand_ver
                    if not eff_provider:
                        return _emit_bootstrap_result(
                            json_mode=json_mode,
                            ok=False,
                            human_msg=(
                                f"Existing {HOST_CONFIG_FILENAME} is missing a valid provider for 'core'. "
                                "Pass '--fix' or '--provider=<url_or_path>' to repair."
                            ),
                            error_code="config_invalid",
                            remediation="Run 'python yscb.py init --fix --provider=<url_or_path>'.",
                            exit_code=1,
                        )
                    if (
                        provider_arg is None
                        and yscb_root_rel is None
                        and pinned_core_ver is not None
                        and _is_installed_core_healthy(yscb_root / ".modules" / "core", pinned_core_ver)
                    ):
                        return _emit_bootstrap_result(
                            json_mode=json_mode,
                            ok=True,
                            human_msg=f"Workspace already initialized at {yscb_root} (pass --fix to repair).",
                            value={"yscb_root": str(yscb_root), "already_initialized": True},
                            exit_code=0,
                        )
                deploy_provider = eff_provider
                if offline_active and eff_provider.lower().startswith(("http://", "https://")):
                    mirror_root = yscb_root / ".mirror"
                    if provider_arg is None and (mirror_root / "core" / "index.json").is_file():
                        deploy_provider = str(mirror_root)
                    else:
                        return _emit_bootstrap_result(
                            json_mode=json_mode,
                            ok=False,
                            human_msg=f"Offline mode is active; refusing remote provider '{eff_provider}'.",
                            error_code="transport_lost",
                            exit_code=1,
                        )
                deployed_ver = _deploy_core_from_provider(
                    host_dir,
                    yscb_root,
                    deploy_provider,
                    pinned_version=(None if fix_mode else pinned_core_ver),
                    ignore_sha256=ignore_sha,
                )
                core_proj_cfg = yscb_root / "config" / "core" / "config.project.json"
                rewrite_core_proj = not core_proj_cfg.exists()
                if not rewrite_core_proj and fix_mode:
                    try:
                        proj_doc = _read_json_file(core_proj_cfg)
                    except ValueError:
                        proj_doc = None
                    if not isinstance(proj_doc, dict) or "project_root" not in proj_doc:
                        rewrite_core_proj = True
                    else:
                        raw_pr = proj_doc["project_root"]
                        if raw_pr is not None and (
                            type(raw_pr) is not str
                            or not raw_pr.strip()
                            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw_pr)
                        ):
                            rewrite_core_proj = True
                if rewrite_core_proj:
                    _atomic_write_json(core_proj_cfg, {"project_root": "./"})
                if latest_existing is not None and fix_mode:
                    out_doc: dict[str, object] = {
                        k: v
                        for k, v in latest_existing.items()
                        if k in ("yscb_root", "default_provider", "installed_modules")
                    }
                else:
                    out_doc = dict(latest_existing) if latest_existing is not None else {}
                out_doc["yscb_root"] = persisted_root_rel
                out_doc["default_provider"] = persisted_provider
                inst_raw = out_doc.get("installed_modules")
                inst_map: dict[str, object] = {}
                if isinstance(inst_raw, dict):
                    for mod_k, mod_v in inst_raw.items():
                        if not fix_mode:
                            inst_map[mod_k] = mod_v
                        elif (
                            type(mod_k) is str
                            and mod_k == mod_k.strip()
                            and mod_k != "core"
                            and mod_k not in _BOOT_RESERVED_NON_MODULE_IDS
                            and _BOOT_MODULE_ID_RE.fullmatch(mod_k) is not None
                            and isinstance(mod_v, dict)
                            and all(
                                type(mod_v.get(req_f)) is str
                                and str(mod_v[req_f]).strip()
                                and not any(ord(c) < 0x20 or ord(c) == 0x7F for c in str(mod_v[req_f]))
                                for req_f in ("version", "provider", "installed_at")
                            )
                        ):
                            try:
                                parsed_mv = _parse_semver4(str(mod_v["version"]).strip())
                            except ValueError:
                                continue
                            clean_mod_prov = _sanitize_provider_for_fix(str(mod_v["provider"]).strip())
                            if not clean_mod_prov:
                                continue
                            inst_map[mod_k] = {
                                "version": parsed_mv.canonical_str(),
                                "provider": clean_mod_prov,
                                "installed_at": str(mod_v["installed_at"]).strip(),
                            }
                inst_map["core"] = {
                    "version": deployed_ver,
                    "provider": persisted_core_provider,
                    "installed_at": _utc_now_iso(),
                }
                out_doc["installed_modules"] = inst_map
                _atomic_write_json(cfg_path, out_doc)
                local_cfg_path = host_dir / HOST_LOCAL_CONFIG_FILENAME
                if fix_mode and os.path.lexists(local_cfg_path):
                    _assert_safe_local_path(local_cfg_path)
                    if latest_local is None or sanitized_local != latest_local:
                        _atomic_write_json(local_cfg_path, sanitized_local)
                break
    except _BootstrapSecurityError as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Security violation initializing workspace: {exc}",
            error_code="security_gated",
            exit_code=4,
        )
    except _BootstrapConfigTypeError as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Invalid host configuration: {exc}",
            error_code="config_invalid",
            exit_code=1,
        )
    except (HTTPError, URLError, HTTPException, TimeoutError, ConnectionError) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Network transport error initializing workspace: {exc}",
            error_code="transport_lost",
            exit_code=1,
        )
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Error initializing workspace: {exc}",
            error_code="package_integrity_error",
            exit_code=1,
        )

    return _emit_bootstrap_result(
        json_mode=json_mode,
        ok=True,
        human_msg=f"Initialized YS-Codebase workspace at {yscb_root} with core {deployed_ver}.",
        value={
            "yscb_root": str(yscb_root),
            "core_version": deployed_ver,
            "already_initialized": False,
        },
        exit_code=0,
    )


def _handle_self_update(
    argv: Sequence[str],
    host_dir: Path,
    caller_cwd: Path,
    script_path: Path,
    *,
    json_mode: bool = False,
) -> int:
    target_url = DEFAULT_SELF_UPDATE_URL
    expected_sha: Optional[str] = None
    ignore_sha = False
    allow_mutation = False

    idx = 0
    while idx < len(argv):
        tok = argv[idx]
        if tok == "--":
            if idx + 1 < len(argv):
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg=f"Unexpected positional argument for 'yscb self-update': {argv[idx + 1]}",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            break
        if tok in ("-h", "--help"):
            return _emit_bootstrap_help(
                "Usage: yscb self-update [--url=<url_or_path>] [--sha256=<hex>] [--ignore-sha256] [--allow-bootstrap-mutation]\n",
                ["self-update"],
                json_mode=json_mode,
            )
        if tok in ("--json", "--cold"):
            idx += 1
            continue
        if tok == "--ignore-sha256":
            ignore_sha = True
            idx += 1
            continue
        if tok == "--allow-bootstrap-mutation":
            allow_mutation = True
            idx += 1
            continue
        if tok.startswith("--url="):
            val = tok.split("=", 1)[1].strip()
            if not val:
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--url' requires a non-empty value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            target_url = val
            idx += 1
            continue
        if tok == "--url":
            if idx + 1 >= len(argv) or not argv[idx + 1].strip() or argv[idx + 1].strip().startswith("-"):
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--url' requires a non-empty value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            target_url = argv[idx + 1].strip()
            idx += 2
            continue
        if tok.startswith("--sha256="):
            val = tok.split("=", 1)[1].strip().lower()
            if not val:
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--sha256' requires a non-empty hex value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            expected_sha = val
            idx += 1
            continue
        if tok == "--sha256":
            if idx + 1 >= len(argv) or not argv[idx + 1].strip() or argv[idx + 1].strip().startswith("-"):
                return _emit_bootstrap_result(
                    json_mode=json_mode,
                    ok=False,
                    human_msg="Option '--sha256' requires a non-empty hex value.",
                    error_code="codec_validation_failed",
                    exit_code=2,
                )
            expected_sha = argv[idx + 1].strip().lower()
            idx += 2
            continue
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Unknown option for 'yscb self-update': {tok}",
            error_code="codec_validation_failed",
            exit_code=2,
        )

    gate_rc = _check_bootstrap_mutation_gate(
        "yscb self-update",
        allow_mutation=allow_mutation,
        json_mode=json_mode,
    )
    if gate_rc is not None:
        return gate_rc

    offline_active = os.environ.get("YSCB_OFFLINE", "").strip().lower() in _TRUTHY_OFFLINE_VALUES
    try:
        eff_target_url = _normalize_bootstrap_local_source(target_url, host_dir, caller_cwd)
        if offline_active and eff_target_url.lower().startswith(("http://", "https://")):
            return _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=f"Offline mode is active; refusing remote self-update URL '{eff_target_url}'.",
                error_code="transport_lost",
                exit_code=1,
            )
        script_bytes = _fetch_bytes_from_source(eff_target_url, host_dir, 4 * 1024 * 1024)
        if not ignore_sha:
            if expected_sha is None:
                sha_raw = _fetch_bytes_from_source(f"{eff_target_url}.sha256", host_dir, 4096).decode("utf-8").strip()
                expected_sha = sha_raw.split()[0].lower() if sha_raw else ""
            actual_sha = hashlib.sha256(script_bytes).hexdigest().lower()
            if not expected_sha or actual_sha != expected_sha:
                raise RuntimeError(
                    f"SHA-256 verification failed for yscb.py: expected {expected_sha!r}, got {actual_sha!r}"
                )
        src_text = script_bytes.decode("utf-8")
        parsed_ast = ast.parse(src_text, filename="yscb.py")
        has_main = any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in parsed_ast.body)
        if not has_main:
            raise RuntimeError("Downloaded yscb.py failed structural AST validation (missing main()).")
        _atomic_write_bytes(script_path, script_bytes)
    except _BootstrapSecurityError as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Self-update blocked by security policy: {exc}",
            error_code="security_gated",
            exit_code=4,
        )
    except (HTTPError, URLError, HTTPException, TimeoutError, ConnectionError) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Self-update network error: {exc}",
            error_code="transport_lost",
            exit_code=1,
        )
    except (OSError, ValueError, SyntaxError, RuntimeError) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Self-update failed: {exc}",
            error_code="package_integrity_error",
            exit_code=1,
        )

    return _emit_bootstrap_result(
        json_mode=json_mode,
        ok=True,
        human_msg=f"Updated launcher script at {script_path}.",
        value={"script_path": str(script_path), "updated": True},
        exit_code=0,
    )


def _is_installed_core_healthy(core_dir: Path, expected_ver: str) -> bool:
    try:
        _assert_safe_local_path(core_dir, allow_missing_leaf=True)
    except RuntimeError:
        return False
    if _is_reparse_or_symlink(core_dir):
        return False
    mf_path = core_dir / "manifest.json"
    pkg_dir = core_dir / "core"
    pkg_init = pkg_dir / "__init__.py"
    idx_path = core_dir / "tasks.index.json"
    required_sub_dirs = (
        pkg_dir / "foundation",
        pkg_dir / "surface",
        pkg_dir / "surface" / "cli",
        pkg_dir / "surface" / "bootstrap",
    )
    required_sub_inits = tuple(d / "__init__.py" for d in required_sub_dirs)
    if (
        _is_reparse_or_symlink(mf_path)
        or _is_reparse_or_symlink(pkg_dir)
        or _is_reparse_or_symlink(pkg_init)
        or any(_is_reparse_or_symlink(d) for d in required_sub_dirs)
        or any(_is_reparse_or_symlink(f) for f in required_sub_inits)
        or (os.path.lexists(idx_path) and _is_reparse_or_symlink(idx_path))
    ):
        return False
    if not mf_path.is_file() or not pkg_init.is_file() or not all(f.is_file() for f in required_sub_inits):
        return False
    try:
        mf_doc = _read_json_file(mf_path)
    except (OSError, ValueError, RuntimeError):
        return False
    if mf_doc is None:
        return False
    raw_mf_id = mf_doc.get("id")
    raw_mf_ver = mf_doc.get("version")
    if type(raw_mf_id) is not str or raw_mf_id.strip() != "core":
        return False
    if type(raw_mf_ver) is not str or not raw_mf_ver.strip():
        return False
    disk_ver = raw_mf_ver.strip()
    try:
        exp_sv = _parse_semver4(expected_ver)
        dsk_sv = _parse_semver4(disk_ver)
    except ValueError:
        return False
    if exp_sv == dsk_sv:
        return True
    if exp_sv.is_build and dsk_sv.is_build and exp_sv.triple == dsk_sv.triple:
        return True
    return False


def _is_truthy_offline_cli_token(tok: str) -> bool:
    if tok == "--offline":
        return True
    if tok.lower().startswith("--offline="):
        return tok.split("=", 1)[1].strip().lower() in _TRUTHY_OFFLINE_VALUES
    return False


def _has_cli_offline_flag(args: Sequence[str]) -> bool:
    dd_idx = list(args).index("--") if "--" in args else len(args)
    return any(_is_truthy_offline_cli_token(tok) for tok in args[:dd_idx])


def _ensure_deterministic_core_present(
    host_dir: Path,
    base_cfg: Mapping[str, object],
    local_cfg: Optional[Mapping[str, object]],
    yscb_root: Path,
    *,
    cli_offline: bool = False,
    json_mode: bool = False,
) -> tuple[Optional[Path], int]:
    try:
        core_rec = _extract_core_install_record(base_cfg)
        if core_rec is None:
            rc = _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=(
                    "Error: yscb.config.json is missing installed_modules['core']. "
                    "Refusing to guess core version; run 'python yscb.py init --fix'."
                ),
                error_code="config_invalid",
                remediation="Run 'python yscb.py init --fix'.",
                exit_code=1,
            )
            return (None, rc)
        pinned_ver = _extract_config_str_field(core_rec, "version", label="installed_modules.core.version")
        local_provider = _extract_config_str_field(local_cfg, "default_provider", label="local.default_provider")
        persisted_provider = (
            _extract_config_str_field(core_rec, "provider", label="installed_modules.core.provider")
            or _extract_config_str_field(base_cfg, "default_provider", label="default_provider")
        )
    except _BootstrapConfigTypeError as exc:
        rc = _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Invalid host configuration: {exc}",
            error_code="config_invalid",
            remediation="Run 'python yscb.py init --fix'.",
            exit_code=1,
        )
        return (None, rc)
    eff_provider = local_provider or persisted_provider

    core_dir = yscb_root / ".modules" / "core"
    if pinned_ver and _is_installed_core_healthy(core_dir, pinned_ver):
        return (yscb_root, 0)

    mirror_root = yscb_root / ".mirror"
    has_mirror_index = (mirror_root / "core" / "index.json").is_file()
    offline_active = cli_offline or (os.environ.get("YSCB_OFFLINE", "").strip().lower() in _TRUTHY_OFFLINE_VALUES)
    if offline_active and eff_provider.strip().lower().startswith(("http://", "https://")):
        if has_mirror_index:
            eff_provider = str(mirror_root)
        else:
            rc = _emit_bootstrap_result(
                json_mode=json_mode,
                ok=False,
                human_msg=(
                    f"Error: Offline mode is active and '.mirror/core/index.json' is missing; "
                    f"refusing remote provider '{eff_provider}'."
                ),
                error_code="transport_lost",
                remediation="Disable offline mode or populate '.mirror/core/'.",
                exit_code=1,
            )
            return (None, rc)

    if not pinned_ver or not eff_provider:
        rc = _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=(
                "Error: Missing deterministic 'version' or 'provider' for 'core' in yscb.config.json. "
                "Run 'python yscb.py init --fix --provider=<url_or_path>' to repair."
            ),
            error_code="config_invalid",
            remediation="Run 'python yscb.py init --fix --provider=<url_or_path>'.",
            exit_code=1,
        )
        return (None, rc)

    try:
        for _lock_attempt in range(3):
            with _bootstrap_exclusive_lock(yscb_root):
                refreshed_base, refreshed_local = _load_host_configs(host_dir)
                if refreshed_base is None:
                    rc = _emit_bootstrap_result(
                        json_mode=json_mode,
                        ok=False,
                        human_msg=(
                            f"Workspace configuration {HOST_CONFIG_FILENAME} was removed during bootstrap; "
                            "run 'python yscb.py init' first."
                        ),
                        error_code="config_invalid",
                        remediation="Run 'python yscb.py init' first.",
                        exit_code=1,
                    )
                    return (None, rc)
                locked_root_rel = _extract_strict_yscb_root_rel(refreshed_base, refreshed_local)
                locked_yscb_root = _resolve_yscb_root_path(host_dir, locked_root_rel)
                if locked_yscb_root != yscb_root:
                    if _lock_attempt < 2:
                        yscb_root = locked_yscb_root
                        core_dir = yscb_root / ".modules" / "core"
                        mirror_root = yscb_root / ".mirror"
                        continue
                    raise RuntimeError(
                        "Workspace yscb_root changed concurrently during bootstrap lock acquisition; retry command."
                    )
                core_dir = yscb_root / ".modules" / "core"
                mirror_root = yscb_root / ".mirror"

                ref_core = _extract_core_install_record(refreshed_base)
                if ref_core is None:
                    rc = _emit_bootstrap_result(
                        json_mode=json_mode,
                        ok=False,
                        human_msg=(
                            "Error: yscb.config.json is missing installed_modules['core']. "
                            "Refusing to guess core version; run 'python yscb.py init --fix'."
                        ),
                        error_code="config_invalid",
                        remediation="Run 'python yscb.py init --fix'.",
                        exit_code=1,
                    )
                    return (None, rc)
                pinned_ver = _extract_config_str_field(ref_core, "version", label="installed_modules.core.version")
                persisted_provider = (
                    _extract_config_str_field(ref_core, "provider", label="installed_modules.core.provider")
                    or _extract_config_str_field(refreshed_base, "default_provider", label="default_provider")
                )
                ref_local_prov = _extract_config_str_field(
                    refreshed_local,
                    "default_provider",
                    label="local.default_provider",
                )
                eff_provider = ref_local_prov or persisted_provider
                if pinned_ver and _is_installed_core_healthy(core_dir, pinned_ver):
                    return (yscb_root, 0)
                has_mirror_now = (mirror_root / "core" / "index.json").is_file()
                if offline_active and eff_provider.strip().lower().startswith(("http://", "https://")):
                    if has_mirror_now:
                        eff_provider = str(mirror_root)
                    else:
                        rc = _emit_bootstrap_result(
                            json_mode=json_mode,
                            ok=False,
                            human_msg=(
                                f"Error: Offline mode is active and '.mirror/core/index.json' is missing; "
                                f"refusing remote provider '{eff_provider}'."
                            ),
                            error_code="transport_lost",
                            remediation="Disable offline mode or populate '.mirror/core/'.",
                            exit_code=1,
                        )
                        return (None, rc)
                if not pinned_ver or not eff_provider:
                    rc = _emit_bootstrap_result(
                        json_mode=json_mode,
                        ok=False,
                        human_msg=(
                            "Error: Missing deterministic 'version' or 'provider' for 'core' in yscb.config.json. "
                            "Run 'python yscb.py init --fix --provider=<url_or_path>' to repair."
                        ),
                        error_code="config_invalid",
                        remediation="Run 'python yscb.py init --fix --provider=<url_or_path>'.",
                        exit_code=1,
                    )
                    return (None, rc)
                try:
                    restored_ver = _deploy_core_from_provider(
                        host_dir,
                        yscb_root,
                        eff_provider,
                        pinned_version=pinned_ver,
                        ignore_sha256=False,
                    )
                except (_BootstrapNonFallbackError, zipfile.BadZipFile):
                    raise
                except _BootstrapPayloadFormatError as fmt_exc:
                    is_remote_http = eff_provider.strip().lower().startswith(("http://", "https://"))
                    if is_remote_http and has_mirror_now and eff_provider != str(mirror_root):
                        restored_ver = _deploy_core_from_provider(
                            host_dir,
                            yscb_root,
                            str(mirror_root),
                            pinned_version=pinned_ver,
                            ignore_sha256=False,
                        )
                    else:
                        raise fmt_exc
                except (OSError, RuntimeError, HTTPError, URLError, HTTPException) as primary_exc:
                    if has_mirror_now and eff_provider != str(mirror_root):
                        restored_ver = _deploy_core_from_provider(
                            host_dir,
                            yscb_root,
                            str(mirror_root),
                            pinned_version=pinned_ver,
                            ignore_sha256=False,
                        )
                    else:
                        raise primary_exc
                if _parse_semver4(restored_ver) != _parse_semver4(pinned_ver):
                    cfg_path = host_dir / HOST_CONFIG_FILENAME
                    base_doc = _read_json_file(cfg_path)
                    if not isinstance(base_doc, dict):
                        raise _BootstrapConfigTypeError(f"Missing or invalid {HOST_CONFIG_FILENAME} during version pin update.")
                    raw_im = base_doc.get("installed_modules")
                    im_dict: dict[str, object] = dict(raw_im) if isinstance(raw_im, dict) else {}
                    prev_core = im_dict.get("core")
                    updated_core: dict[str, object] = dict(prev_core) if isinstance(prev_core, dict) else {}
                    updated_core["version"] = restored_ver
                    if persisted_provider and "provider" not in updated_core:
                        updated_core["provider"] = persisted_provider
                    updated_core["installed_at"] = _utc_now_iso()
                    im_dict["core"] = updated_core
                    base_doc["installed_modules"] = im_dict
                    _atomic_write_json(cfg_path, base_doc)
                break
        return (yscb_root, 0)
    except _BootstrapSecurityError as exc:
        rc = _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Security violation restoring '.modules/core': {exc}",
            error_code="security_gated",
            remediation="Inspect workspace symlinks and provider URL security.",
            exit_code=4,
        )
        return (None, rc)
    except _BootstrapConfigTypeError as exc:
        rc = _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Invalid host configuration: {exc}",
            error_code="config_invalid",
            remediation="Run 'python yscb.py init --fix'.",
            exit_code=1,
        )
        return (None, rc)
    except (HTTPError, URLError, HTTPException, TimeoutError, ConnectionError) as exc:
        rc = _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=(
                f"Network error restoring missing '.modules/core' ({pinned_ver}) from configured provider '{eff_provider}': {exc}\n"
                "Remediation: Check network/mirror availability or run 'python yscb.py init --fix'."
            ),
            error_code="transport_lost",
            remediation="Check network/mirror availability or run 'python yscb.py init --fix'.",
            exit_code=1,
        )
        return (None, rc)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        rc = _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=(
                f"Error restoring missing '.modules/core' ({pinned_ver}) from configured provider '{eff_provider}': {exc}\n"
                "Remediation: Check network/mirror availability or run 'python yscb.py init --fix'."
            ),
            error_code="package_integrity_error",
            remediation="Check network/mirror availability or run 'python yscb.py init --fix'.",
            exit_code=1,
        )
        return (None, rc)


def _delegate_to_microkernel(
    argv: Sequence[str],
    host_dir: Path,
    yscb_root: Path,
    caller_cwd: Path,
    script_path: Path,
    *,
    json_mode: bool = False,
    boot_start_ns: Optional[int] = None,
) -> int:
    core_dir = yscb_root / ".modules" / "core"
    try:
        init_py = core_dir / "core" / "__init__.py"
        _assert_safe_local_path(init_py, allow_missing_leaf=False)
        if not init_py.is_file() or _is_reparse_or_symlink(init_py):
            raise _BootstrapNonFallbackError(f"Missing or non-regular microkernel __init__.py: {init_py}")
        idx_file = core_dir / "tasks.index.json"
        if os.path.lexists(idx_file) and _is_reparse_or_symlink(idx_file):
            raise _BootstrapSecurityError(f"Refusing symlinked tasks.index.json: {idx_file}")

        core_mod_root = str(core_dir.resolve())
        if sys.path[:1] != [core_mod_root]:
            if core_mod_root in sys.path:
                sys.path.remove(core_mod_root)
            sys.path.insert(0, core_mod_root)

        from core.foundation import HostPath
        from core.surface.cli import main as microkernel_cli_main, register_cli_kernel_factory

        script_hp = HostPath(script_path)
        host_hp = HostPath(host_dir)
        root_hp = HostPath(yscb_root)
        cwd_hp = HostPath(caller_cwd)
    except _BootstrapSecurityError as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Unsafe microkernel path in '{core_dir}': {exc}",
            error_code="security_gated",
            remediation="Run 'python yscb.py init --fix' to repair.",
            exit_code=4,
        )
    except (OSError, ValueError, RuntimeError, ImportError, SyntaxError) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=(
                f"Corrupted or unsafe microkernel installation in '{core_dir}': {exc}\n"
                "Run 'python yscb.py init --fix' to repair."
            ),
            error_code="package_integrity_error",
            remediation="Run 'python yscb.py init --fix' to repair.",
            exit_code=1,
        )

    def _lazy_open_kernel_session(h_dir: HostPath, y_root: HostPath, force_cold: bool):
        from core.surface.bootstrap import WorkspaceKernelFactory

        return WorkspaceKernelFactory.open_cli_session(
            h_dir,
            y_root,
            force_cold,
            yscb_script_path=script_hp,
        )

    def _lazy_builtin_indices():
        from core.surface.bootstrap import WorkspaceKernelFactory

        return WorkspaceKernelFactory.builtin_cli_indices()

    register_cli_kernel_factory(
        _lazy_open_kernel_session,
        builtin_indices_fn=_lazy_builtin_indices,
    )

    return int(
        microkernel_cli_main(
            list(argv),
            host_dir=host_hp,
            yscb_root=root_hp,
            caller_cwd=cwd_hp,
            kernel_factory=_lazy_open_kernel_session,
            boot_start_ns=boot_start_ns,
        )
    )


def _extract_host_dir_flag(args: Sequence[str]) -> tuple[Optional[str], list[str]]:
    raw_list = list(args)
    dd_idx = raw_list.index("--") if "--" in raw_list else len(raw_list)
    pre_dd = raw_list[:dd_idx]
    post_dd = raw_list[dd_idx:]
    found_host: Optional[str] = None
    cleaned: list[str] = []
    idx = 0
    while idx < len(pre_dd):
        tok = pre_dd[idx]
        if tok.startswith("--host-dir="):
            val = tok.split("=", 1)[1].strip()
            if not val:
                raise RuntimeError("Global '--host-dir' option requires a non-empty directory path.")
            found_host = val
            idx += 1
            continue
        if tok == "--host-dir":
            if idx + 1 >= len(pre_dd) or not pre_dd[idx + 1].strip() or pre_dd[idx + 1].strip().startswith("-"):
                raise RuntimeError("Missing or empty value for global '--host-dir' option.")
            found_host = pre_dd[idx + 1].strip()
            idx += 2
            continue
        cleaned.append(tok)
        idx += 1
    return (found_host, [*cleaned, *post_dd])


def _extract_bootstrap_primitive(args: Sequence[str]) -> tuple[Optional[str], list[str]]:
    dd_idx = list(args).index("--") if "--" in args else len(args)
    pre_dd = list(args[:dd_idx])
    i = 0
    while i < len(pre_dd):
        tok = pre_dd[i]
        if tok == "--approve":
            if i + 1 < len(pre_dd) and not pre_dd[i + 1].startswith("-"):
                i += 2
                continue
            i += 1
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if tok in ("init", "self-update"):
            sub_args = [*pre_dd[:i], *pre_dd[i + 1 :], *list(args[dd_idx:])]
            return (tok, sub_args)
        return (None, [])
    return (None, [])


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    host_dir_override: Optional[Path] = None,
) -> int:
    """Thin stdlib entrypoint handling init, self-update, deterministic core auto-restore, and microkernel handoff."""
    boot_start_ns = time.perf_counter_ns()
    _reconfigure_utf8_standard_streams()
    raw_args = list(argv if argv is not None else sys.argv[1:])
    json_mode = _has_cli_json_flag(raw_args)
    try:
        cli_host_dir, args = _extract_host_dir_flag(raw_args)
    except RuntimeError as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Error: {exc}",
            error_code="codec_validation_failed",
            exit_code=2,
        )

    raw_script = Path(__file__)
    try:
        _assert_safe_local_path(raw_script, allow_missing_leaf=False)
        script_path = raw_script.resolve()
        raw_cwd = Path.cwd()
        _assert_safe_local_path(raw_cwd, allow_missing_leaf=False)
        caller_cwd = raw_cwd.resolve()

        env_internal_host = os.environ.get("_YSCB_HOST_DIR", "").strip()
        if host_dir_override is not None:
            raw_host_dir = host_dir_override
        elif cli_host_dir is not None:
            raw_host_dir = Path(cli_host_dir)
        elif env_internal_host:
            raw_host_dir = Path(env_internal_host)
        else:
            raw_host_dir = script_path.parent
        _assert_safe_local_path(raw_host_dir, allow_missing_leaf=False)
        host_dir = raw_host_dir.resolve()
        _assert_safe_local_path(host_dir, allow_missing_leaf=False)
        if os.path.lexists(host_dir) and not host_dir.is_dir():
            raise _BootstrapNonFallbackError(f"Host workspace path exists and is not a directory: {host_dir}")
    except (OSError, ValueError, RuntimeError) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Unsafe host or script path: {exc}",
            error_code="security_gated",
            exit_code=4,
        )

    prim_cmd, prim_args = _extract_bootstrap_primitive(args)
    if prim_cmd == "init":
        return _handle_init(prim_args, host_dir, caller_cwd, json_mode=json_mode)
    if prim_cmd == "self-update":
        return _handle_self_update(prim_args, host_dir, caller_cwd, script_path, json_mode=json_mode)

    try:
        base_cfg, local_cfg = _load_host_configs(host_dir)
    except _BootstrapSecurityError as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Unsafe host configuration file: {exc}",
            error_code="security_gated",
            exit_code=4,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Error reading host configuration ({exc})\nRun 'python yscb.py init --fix' to repair.",
            error_code="config_invalid",
            remediation="Run 'python yscb.py init --fix' to repair.",
            exit_code=1,
        )

    dd_idx_args = args.index("--") if "--" in args else len(args)
    pre_dd_args = args[:dd_idx_args]
    if base_cfg is None:
        if not pre_dd_args or any(a in ("-h", "--help") for a in pre_dd_args) or all(
            a in _GLOBAL_LAUNCHER_FLAGS for a in pre_dd_args
        ):
            return _emit_bootstrap_help(
                "YS-Codebase 2.0 Launcher (uninitialized workspace)\n\n"
                "Bootstrap Commands:\n"
                "  yscb init [--provider=<url_or_path>] [--yscb-root=<rel>] [--fix]\n"
                "  yscb self-update [--url=<url_or_path>] [--sha256=<hex>]\n",
                [],
                json_mode=json_mode,
            )
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=(
                f"Workspace is not initialized in '{host_dir}' (missing {HOST_CONFIG_FILENAME}).\n"
                "Run 'python yscb.py init' first."
            ),
            error_code="config_invalid",
            remediation="Run 'python yscb.py init' first.",
            exit_code=1,
        )

    raw_root: Optional[str] = None
    try:
        raw_root = _extract_strict_yscb_root_rel(base_cfg, local_cfg)
        yscb_root = _resolve_yscb_root_path(host_dir, raw_root)
    except _BootstrapSecurityError as exc:
        root_hint = f" '{raw_root}'" if raw_root is not None else ""
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Unsafe workspace root{root_hint}: {exc}",
            error_code="security_gated",
            exit_code=4,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        root_hint = f" '{raw_root}'" if raw_root is not None else ""
        return _emit_bootstrap_result(
            json_mode=json_mode,
            ok=False,
            human_msg=f"Invalid workspace root{root_hint}: {exc}",
            error_code="config_invalid",
            exit_code=1,
        )

    verified_root, restore_rc = _ensure_deterministic_core_present(
        host_dir,
        base_cfg,
        local_cfg,
        yscb_root,
        cli_offline=_has_cli_offline_flag(args),
        json_mode=json_mode,
    )
    if verified_root is None:
        return restore_rc

    return _delegate_to_microkernel(
        args,
        host_dir,
        verified_root,
        caller_cwd,
        script_path,
        json_mode=json_mode,
        boot_start_ns=boot_start_ns,
    )


if __name__ == "__main__":
    raise SystemExit(main())
