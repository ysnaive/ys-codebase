"""Immutable, construction-normalized domain value objects and JSON type aliases for Core 2.0."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import threading
from typing import (
    Callable,
    Final,
    ForwardRef,
    Iterable,
    Mapping,
    Optional,
    Sequence,
    TypeAlias,
    TypeVar,
    get_args,
    get_origin,
)

JsonPrimitive: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonPrimitive | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
JsonObject: TypeAlias = Mapping[str, JsonValue]
IS_WINDOWS: Final[bool] = sys.platform == "win32"
IO_REPARSE_TAG_MOUNT_POINT: Final[int] = 0xA0000003
IO_REPARSE_TAG_SYMLINK: Final[int] = 0xA000000C
PRIVATE_ENV_PREFIX: Final[str] = "_YSCB_"
TREE_ID_ENV_KEY: Final[str] = "_YSCB_TREE_ID"
TEST_SANDBOX_ENV_KEY: Final[str] = "_YSCB_TEST_SANDBOX"
FORCE_FLIGHT_LOGS_ENV_KEY: Final[str] = "_YSCB_FORCE_FLIGHT_LOGS"
HOST_DIR_ENV_KEY: Final[str] = "_YSCB_HOST_DIR"
ROOT_DIR_ENV_KEY: Final[str] = "_YSCB_ROOT_DIR"
PUBLIC_ENV_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "YSCB_NO_DAEMON",
        "YSCB_FORCE_DAEMON",
        "YSCB_LOG_LEVEL",
        "YSCB_NO_UPDATE_CHECK",
        "YSCB_LOCALE",
        "YSCB_OFFLINE",
        "YSCB_CALLER_MODE",
        "YSCB_CI_APPROVE_GATED",
        "YSCB_PROFILE_MEM",
    }
)
TOOLCHAIN_ENV_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
        "SSH_AUTH_SOCK",
        "GIT_SSH_COMMAND",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "CARGO_HOME",
        "RUSTUP_HOME",
        "GOPATH",
        "GOMODCACHE",
        "NPM_CONFIG_REGISTRY",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
    }
)
PYTHON_LAUNCHER_HIJACK_ENV_KEYS: Final[tuple[str, ...]] = (
    "__PYVENV_LAUNCHER__",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
)


def extract_toolchain_env(raw_env: Mapping[str, str]) -> dict[str, str]:
    """Filter a raw environment mapping to non-credential developer toolchain, proxy, CA, and SSH agent keys."""
    if not isinstance(raw_env, Mapping):
        raise ValueError(f"extract_toolchain_env requires a Mapping[str, str], got {type(raw_env).__name__}")
    hijack_upper = {k.upper() for k in PYTHON_LAUNCHER_HIJACK_ENV_KEYS}
    out: dict[str, str] = {}
    for k, v in raw_env.items():
        if type(k) is not str or type(v) is not str or not k or "=" in k or "\x00" in k or "\x00" in v:
            continue
        try:
            k.encode("utf-8")
            v.encode("utf-8")
        except UnicodeEncodeError:
            continue
        ku = k.upper()
        if (
            ku in hijack_upper
            or ku.startswith(("PYTHON", "PIP_", PRIVATE_ENV_PREFIX, "YSCB_"))
            or ku == "VIRTUAL_ENV"
        ):
            continue
        if ku in TOOLCHAIN_ENV_ALLOWLIST:
            out[k] = v
    return out
MutableJsonObject: TypeAlias = dict[str, JsonValue]
MAX_USER_JSON_DEPTH: Final[int] = 128
MAX_ENVELOPE_JSON_DEPTH: Final[int] = MAX_USER_JSON_DEPTH + 6
MAX_PARSE_JSON_DEPTH: Final[int] = MAX_ENVELOPE_JSON_DEPTH + 2
_T = TypeVar("_T")


for _json_branch in get_args(JsonValue):
    for _json_arg in get_args(_json_branch):
        if isinstance(_json_arg, ForwardRef):
            object.__setattr__(_json_arg, "__forward_module__", __name__)

_WIN_RESERVED_DEVICE_STEMS: Final[frozenset[str]] = frozenset(
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


_WIN_ILLEGAL_SEGMENT_CHARS: Final[frozenset[str]] = frozenset("<>:\"/\\|?*")
_WIN_DEVICE_NS_RE: Final[re.Pattern[str]] = re.compile(r"^[\\/]{2,}[.?](?:[\\/]|$)")


def is_valid_relative_segment(segment: str) -> bool:
    """Return True iff segment is a single non-traversing cross-platform safe path component."""
    if type(segment) is not str or not segment or segment in (".", ".."):
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch in _WIN_ILLEGAL_SEGMENT_CHARS for ch in segment):
        return False
    if segment.endswith((".", " ")):
        return False
    try:
        segment.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    stem = segment.split(".", 1)[0].rstrip(". ").lower()
    return stem not in _WIN_RESERVED_DEVICE_STEMS


def validate_relative_segment(segment: str, *, label: str = "path segment") -> str:
    """Validate and return a single non-traversing cross-platform safe path segment."""
    require_pure_str(segment, label)
    if not is_valid_relative_segment(segment):
        raise ValueError(f"Invalid {label}: {segment!r}")
    return segment


def is_disallowed_reparse_tag(reparse_tag: int) -> bool:
    """Return True iff ``reparse_tag`` is a Windows symlink or mount-point/junction reparse tag."""
    clean_tag = require_pure_int(reparse_tag, "reparse_tag", min_val=0)
    return clean_tag in (IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT)


_MODULE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_QUALIFIED_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")
_URI_SCHEME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)*$")
_SEMVER4_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:v|V)?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:\.(?P<rev>0|[1-9]\d*|build))?"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_PRERELEASE_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*$")
_NON_NEG_INT_SEG_RE: Final[re.Pattern[str]] = re.compile(r"^(?:0|[1-9]\d*)$")
_ENV_HASH_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{16,64}$")
_CONSTRAINT_OPS: Final[tuple[str, ...]] = (">=", "<=", "!=", "==", "~=", "^=", "^", ">", "<", "=")


@dataclass(frozen=True, slots=True)
class ModuleId:
    """Validated module identifier (e.g., 'core', 'knowledge-db')."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise ValueError(f"ModuleId requires a plain str, got {self.value!r}")
        cleaned = self.value.strip()
        if not cleaned or not _MODULE_ID_RE.match(cleaned):
            raise ValueError(f"Invalid ModuleId: {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TaskId:
    """Validated qualified task identifier '<module>.<task_name>'."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise ValueError(f"TaskId requires a plain str, got {self.value!r}")
        cleaned = self.value.strip()
        if not cleaned or not _QUALIFIED_ID_RE.match(cleaned):
            raise ValueError(f"Invalid TaskId (expected '<module>.<name>'): {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    @property
    def module_id(self) -> ModuleId:
        return ModuleId(self.value.split(".", 1)[0])

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EventId:
    """Validated qualified event identifier '<module>.<event_name>'."""

    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise ValueError(f"EventId requires a plain str, got {self.value!r}")
        cleaned = self.value.strip()
        if not cleaned or not _QUALIFIED_ID_RE.match(cleaned):
            raise ValueError(f"Invalid EventId (expected '<module>.<name>'): {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    @property
    def module_id(self) -> ModuleId:
        return ModuleId(self.value.split(".", 1)[0])

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class HostPath:
    """Canonicalized absolute real host filesystem path free of implicit process cwd coupling."""

    path: Path
    comparison_key: str

    def __init__(self, raw: str | os.PathLike[str] | Path) -> None:
        if isinstance(raw, (bytes, bytearray, Enum)) or (isinstance(raw, str) and type(raw) is not str):
            raise ValueError(f"HostPath requires a plain str or PathLike[str], got {raw!r}")
        try:
            raw_str = os.fspath(raw)
        except TypeError as exc:
            raise ValueError(f"HostPath requires a plain str or PathLike[str], got {raw!r}") from exc
        if type(raw_str) is not str or not raw_str or "\x00" in raw_str or not Path(raw_str).is_absolute():
            raise ValueError(f"HostPath requires a non-empty absolute path: {raw!r}")
        try:
            raw_str.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"HostPath requires valid UTF-8 path without lone surrogates: {raw!r}") from exc
        _validate_host_path_segments(raw_str)
        resolved = _resolve_canonical_host_path(raw_str)
        resolved_str = str(resolved)
        _validate_host_path_segments(resolved_str)
        try:
            resolved_str.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"Resolved HostPath contains non-UTF-8 surrogates: {resolved_str!r}") from exc
        norm_key = os.path.normcase(resolved_str)
        object.__setattr__(self, "path", resolved)
        object.__setattr__(self, "comparison_key", norm_key)

    def join(self, *parts: str) -> HostPath:
        if not parts:
            return self
        seps = "/\\" if IS_WINDOWS else "/"
        cleaned: list[str] = []
        for idx, part in enumerate(parts):
            require_pure_str(part, "HostPath.join part")
            cand_p = Path(part)
            if not part or "\x00" in part or ":" in part or cand_p.is_absolute() or bool(cand_p.anchor):
                raise ValueError(f"HostPath.join requires relative non-traversing segments, got {part!r}")
            sub_segs = [s for s in re.split(r"[\\/]+", part) if s]
            if not sub_segs or any(not is_valid_relative_segment(s) for s in sub_segs):
                raise ValueError(f"HostPath.join requires relative non-traversing segments, got {part!r}")
            trailing = os.sep if (idx == len(parts) - 1 and part.endswith(tuple(seps))) else ""
            cleaned.append(os.sep.join(sub_segs) + trailing)
        base = str(self.path).rstrip(seps) or str(self.path)
        prefix = base if base.endswith(tuple(seps)) else f"{base}{os.sep}"
        return HostPath(prefix + os.sep.join(cleaned))

    def resolve_caller_relative(self, target: str | os.PathLike[str]) -> HostPath:
        if isinstance(target, (bytes, bytearray, Enum)) or (isinstance(target, str) and type(target) is not str):
            raise ValueError(f"resolve_caller_relative requires plain str or PathLike[str], got {target!r}")
        try:
            raw_t = os.fspath(target)
        except TypeError as exc:
            raise ValueError(f"resolve_caller_relative requires plain str or PathLike[str], got {target!r}") from exc
        require_pure_str(raw_t, "resolve_caller_relative target")
        if not raw_t or "\x00" in raw_t:
            raise ValueError(f"resolve_caller_relative requires non-empty path: {target!r}")
        cand = Path(raw_t)
        if cand.is_absolute():
            return HostPath(raw_t)
        if bool(cand.anchor) or raw_t.startswith(("/", "\\")) or ":" in raw_t:
            raise ValueError(f"Anchor-relative or stream path forbidden in resolve_caller_relative: {target!r}")
        raw_segs = [s for s in re.split(r"[\\/]+", raw_t) if s]
        if not raw_segs:
            raise ValueError(f"resolve_caller_relative requires non-empty relative segments: {target!r}")
        for seg in raw_segs:
            if seg not in (".", ".."):
                validate_relative_segment(seg, label="resolve_caller_relative segment")
        trailing = os.sep if raw_t.endswith(("/", "\\")) else ""
        norm_rel = os.sep.join(raw_segs) + trailing
        seps = "/\\" if IS_WINDOWS else "/"
        base = str(self.path).rstrip(seps) or str(self.path)
        prefix = base if base.endswith(tuple(seps)) else f"{base}{os.sep}"
        return HostPath(f"{prefix}{norm_rel}")

    def __str__(self) -> str:
        return str(self.path)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HostPath):
            return NotImplemented
        return self.comparison_key == other.comparison_key

    def __hash__(self) -> int:
        return hash(self.comparison_key)


def _compare_prerelease_tags(left_pre: str, right_pre: str) -> int:
    if left_pre == right_pre:
        return 0
    left_parts = left_pre.split(".")
    right_parts = right_pre.split(".")
    for left_tok, right_tok in zip(left_parts, right_parts):
        if left_tok == right_tok:
            continue
        left_num = left_tok.isdigit()
        right_num = right_tok.isdigit()
        if left_num and right_num:
            left_i = int(left_tok)
            right_i = int(right_tok)
            if left_i != right_i:
                return 1 if left_i > right_i else -1
            continue
        if left_num and not right_num:
            return -1
        if not left_num and right_num:
            return 1
        return 1 if left_tok > right_tok else -1
    if len(left_parts) == len(right_parts):
        return 0
    return 1 if len(left_parts) > len(right_parts) else -1


@dataclass(frozen=True, slots=True)
class SemVer4:
    """Four-segment semantic version: major.minor.patch.revision[-prerelease] or major.minor.patch.build."""

    major: int
    minor: int
    patch: int
    revision: int = 0
    is_build: bool = False
    prerelease: str = ""

    def __post_init__(self) -> None:
        require_pure_int(self.major, "SemVer4.major", min_val=0, max_val=INT64_MAX)
        require_pure_int(self.minor, "SemVer4.minor", min_val=0, max_val=INT64_MAX)
        require_pure_int(self.patch, "SemVer4.patch", min_val=0, max_val=INT64_MAX)
        require_pure_int(self.revision, "SemVer4.revision", min_val=0, max_val=INT64_MAX)
        require_pure_bool(self.is_build, "SemVer4.is_build")
        require_pure_str(self.prerelease, "SemVer4.prerelease")
        if self.is_build and self.revision != 0:
            raise ValueError("SemVer4 with is_build=True requires revision=0.")
        if self.is_build and self.prerelease:
            raise ValueError("SemVer4 with is_build=True cannot carry a prerelease tag.")
        if self.prerelease:
            if _PRERELEASE_RE.fullmatch(self.prerelease) is None:
                raise ValueError(f"Invalid SemVer4 prerelease tag: {self.prerelease!r}")
            if any(seg.isdigit() and len(seg) > 1 and seg.startswith("0") for seg in self.prerelease.split(".")):
                raise ValueError(f"Leading zero forbidden in numeric SemVer4 prerelease identifier: {self.prerelease!r}")

    @classmethod
    def parse(cls, raw: str) -> SemVer4:
        require_pure_str(raw, "SemVer4", non_empty=True)
        cleaned = raw.strip()
        m = _SEMVER4_RE.fullmatch(cleaned)
        if m is None:
            raise ValueError(f"Invalid SemVer4 string: {raw!r}")
        major = int(m.group("major"))
        minor = int(m.group("minor"))
        patch = int(m.group("patch"))
        raw_rev = m.group("rev")
        prerelease = m.group("pre") or ""
        if raw_rev == "build":
            return cls(major=major, minor=minor, patch=patch, revision=0, is_build=True, prerelease=prerelease)
        revision = int(raw_rev) if raw_rev is not None else 0
        return cls(major=major, minor=minor, patch=patch, revision=revision, is_build=False, prerelease=prerelease)

    def triple(self) -> tuple[int, ...]:
        return (self.major, self.minor, self.patch)

    def compare_precedence(self, other: SemVer4) -> int:
        if not isinstance(other, SemVer4):
            raise ValueError(f"SemVer4.compare_precedence requires SemVer4, got {other!r}")
        self_trip = (self.major, self.minor, self.patch)
        other_trip = (other.major, other.minor, other.patch)
        if self_trip > other_trip:
            return 1
        if self_trip < other_trip:
            return -1
        if not self.prerelease and other.prerelease:
            return 1
        if self.prerelease and not other.prerelease:
            return -1
        if self.prerelease and other.prerelease:
            pre_cmp = _compare_prerelease_tags(self.prerelease, other.prerelease)
            if pre_cmp != 0:
                return pre_cmp
        if not self.is_build and other.is_build:
            return 1
        if self.is_build and not other.is_build:
            return -1
        if self.revision > other.revision:
            return 1
        if self.revision < other.revision:
            return -1
        return 0

    def __lt__(self, other: SemVer4) -> bool:
        if not isinstance(other, SemVer4):
            return NotImplemented
        return self.compare_precedence(other) < 0

    def __le__(self, other: SemVer4) -> bool:
        if not isinstance(other, SemVer4):
            return NotImplemented
        return self.compare_precedence(other) <= 0

    def __gt__(self, other: SemVer4) -> bool:
        if not isinstance(other, SemVer4):
            return NotImplemented
        return self.compare_precedence(other) > 0

    def __ge__(self, other: SemVer4) -> bool:
        if not isinstance(other, SemVer4):
            return NotImplemented
        return self.compare_precedence(other) >= 0

    def __str__(self) -> str:
        if self.is_build:
            return f"{self.major}.{self.minor}.{self.patch}.build"
        if self.prerelease:
            rev_part = f".{self.revision}" if self.revision != 0 else ""
            return f"{self.major}.{self.minor}.{self.patch}{rev_part}-{self.prerelease}"
        return f"{self.major}.{self.minor}.{self.patch}.{self.revision}"


@dataclass(frozen=True, slots=True)
class _FndConstraintClause:
    op: str
    wildcard_prefix: Optional[tuple[int, ...]] = None
    target: Optional[SemVer4] = None
    explicit_fourth: bool = False


def _parse_single_constraint_clause(raw_clause: str) -> _FndConstraintClause:
    clause = raw_clause.strip()
    if not clause:
        raise ValueError("Empty VersionConstraint clause.")
    if clause == "*":
        return _FndConstraintClause(op="*")
    op = "=="
    target_text = clause
    for cand_op in _CONSTRAINT_OPS:
        if clause.startswith(cand_op):
            op = "==" if cand_op == "=" else ("^=" if cand_op == "^" else cand_op)
            target_text = clause[len(cand_op) :].strip()
            break
    if not target_text:
        raise ValueError(f"Missing target version in VersionConstraint clause: {raw_clause!r}")
    if target_text == "*":
        if op == "==":
            return _FndConstraintClause(op="*")
        raise ValueError(f"Wildcard '*' cannot combine with operator {op!r}: {raw_clause!r}")
    if target_text == "build":
        if op in ("==", "!="):
            return _FndConstraintClause(op="build_eq" if op == "==" else "build_ne")
        raise ValueError(f"Tag 'build' only supports equality operators, got {raw_clause!r}")
    if target_text.endswith(".*"):
        if op not in ("==", "!="):
            raise ValueError(f"Wildcard prefix {target_text!r} only supports == or !=, got {raw_clause!r}")
        raw_segs = target_text[:-2].lstrip("vV").split(".")
        if not (1 <= len(raw_segs) <= 3) or any(_NON_NEG_INT_SEG_RE.fullmatch(s) is None for s in raw_segs):
            raise ValueError(f"Invalid wildcard prefix in VersionConstraint: {raw_clause!r}")
        prefix_ints = tuple(int(s) for s in raw_segs)
        return _FndConstraintClause(op="wild_eq" if op == "==" else "wild_ne", wildcard_prefix=prefix_ints)
    parsed_ver = SemVer4.parse(target_text)
    core_part = target_text.lstrip("vV").partition("-")[0]
    has_fourth = core_part.count(".") >= 3
    return _FndConstraintClause(op=op, target=parsed_ver, explicit_fourth=has_fourth)


def _eval_constraint_clause(clause: _FndConstraintClause, ver: SemVer4) -> bool:
    if clause.op == "*":
        return True
    if clause.op == "build_eq":
        return ver.is_build
    if clause.op == "build_ne":
        return not ver.is_build
    if clause.op in ("wild_eq", "wild_ne"):
        prefix = require_non_none(clause.wildcard_prefix)
        matched = (not ver.prerelease) and (not ver.is_build) and ver.triple()[: len(prefix)] == prefix
        return matched if clause.op == "wild_eq" else (not matched)
    target = require_non_none(clause.target)
    is_three_seg = (not clause.explicit_fourth) and (not target.prerelease) and (not target.is_build)
    in_three_family = is_three_seg and (not ver.prerelease) and (not ver.is_build) and ver.triple() == target.triple()
    if clause.op == "==":
        return in_three_family if is_three_seg else (ver.compare_precedence(target) == 0)
    if clause.op == "!=":
        return (not in_three_family) if is_three_seg else (ver.compare_precedence(target) != 0)
    if clause.op == ">":
        return ((not in_three_family) and ver.compare_precedence(target) > 0) if is_three_seg else (ver.compare_precedence(target) > 0)
    if clause.op == ">=":
        return ver.compare_precedence(target) >= 0
    if clause.op == "<":
        if (not target.prerelease) and (not target.is_build) and (ver.prerelease or ver.is_build):
            return ver.triple() < target.triple()
        return ver.compare_precedence(target) < 0
    if clause.op == "<=":
        return (in_three_family or ver.compare_precedence(target) <= 0) if is_three_seg else (ver.compare_precedence(target) <= 0)
    if clause.op in ("~=", "^="):
        return ver.compare_precedence(target) >= 0 and ver.major == target.major
    return False


@dataclass(frozen=True, slots=True)
class VersionConstraint:
    """Dependency version constraint supporting ==, =, !=, >, >=, <, <=, ~=, ^, * and comma conjunctions."""

    raw: str

    def __post_init__(self) -> None:
        require_pure_str(self.raw, "VersionConstraint", non_empty=True)
        cleaned = self.raw.strip()
        parts = [p.strip() for p in cleaned.split(",")]
        if not parts or any(not p for p in parts):
            raise ValueError(f"Invalid VersionConstraint: {self.raw!r}")
        for part in parts:
            _parse_single_constraint_clause(part)
        object.__setattr__(self, "raw", cleaned)

    @classmethod
    def parse(cls, raw: str) -> VersionConstraint:
        return cls(raw=raw)

    @classmethod
    def compatible_same_major(cls, ver: SemVer4) -> VersionConstraint:
        if not isinstance(ver, SemVer4):
            raise ValueError(f"compatible_same_major requires SemVer4, got {ver!r}")
        return cls(raw=f"^{ver}")

    def satisfies(self, ver: SemVer4) -> bool:
        if not isinstance(ver, SemVer4):
            raise ValueError(f"VersionConstraint.satisfies requires SemVer4, got {ver!r}")
        clauses = [_parse_single_constraint_clause(part) for part in self.raw.split(",")]
        return all(_eval_constraint_clause(cl, ver) for cl in clauses)

    def __str__(self) -> str:
        return self.raw


def _normalize_semantic_rel_path(raw_rel: str, *, allow_leading_at: bool) -> str:
    require_pure_str(raw_rel, "SemanticUri.rel_path")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw_rel):
        raise ValueError(f"Control characters forbidden in SemanticUri path: {raw_rel!r}")
    norm_slashes = raw_rel.replace("\\", "/")
    parts = [seg for seg in norm_slashes.split("/") if seg]
    for idx, seg in enumerate(parts):
        if seg == "@":
            if idx == 0 and allow_leading_at:
                continue
            raise ValueError(f"Module placeholder '@' is only allowed as the first path segment: {raw_rel!r}")
        validate_relative_segment(seg, label="SemanticUri segment")
    return "/".join(parts)


@dataclass(frozen=True, slots=True)
class SemanticUri:
    """Immutable semantic URI value object requiring an explicit scheme:// without path traversal."""

    scheme: str
    rel_path: str = ""

    def __post_init__(self) -> None:
        require_pure_str(self.scheme, "SemanticUri.scheme", non_empty=True)
        clean_scheme = self.scheme.strip().lower()
        if _URI_SCHEME_RE.fullmatch(clean_scheme) is None:
            raise ValueError(f"Invalid SemanticUri scheme: {self.scheme!r}")
        clean_rel = _normalize_semantic_rel_path(self.rel_path, allow_leading_at=True)
        object.__setattr__(self, "scheme", clean_scheme)
        object.__setattr__(self, "rel_path", clean_rel)

    @classmethod
    def parse(cls, raw: str) -> SemanticUri:
        require_pure_str(raw, "SemanticUri", non_empty=True)
        if "://" not in raw:
            raise ValueError(f"SemanticUri requires explicit '<scheme>://': {raw!r}")
        scheme_part, rel_part = raw.split("://", 1)
        if not scheme_part or scheme_part != scheme_part.strip():
            raise ValueError(f"Invalid SemanticUri scheme in {raw!r}")
        return cls(scheme=scheme_part, rel_path=rel_part)

    @property
    def uses_module_placeholder(self) -> bool:
        return self.rel_path == "@" or self.rel_path.startswith("@/")

    @property
    def name(self) -> str:
        if not self.rel_path:
            return ""
        return PurePosixPath(self.rel_path).name

    @property
    def suffix(self) -> str:
        if not self.rel_path or self.rel_path == "@":
            return ""
        return PurePosixPath(self.rel_path).suffix

    @property
    def parent(self) -> Optional[SemanticUri]:
        if not self.rel_path:
            return None
        if "/" not in self.rel_path:
            return SemanticUri(scheme=self.scheme, rel_path="")
        parent_rel = self.rel_path.rsplit("/", 1)[0]
        return SemanticUri(scheme=self.scheme, rel_path=parent_rel)

    def bind_module(self, module_id: ModuleId) -> SemanticUri:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"SemanticUri.bind_module requires ModuleId, got {module_id!r}")
        if not self.uses_module_placeholder:
            return self
        if self.rel_path == "@":
            return SemanticUri(scheme=self.scheme, rel_path=module_id.value)
        return SemanticUri(scheme=self.scheme, rel_path=f"{module_id.value}/{self.rel_path[2:]}")

    def join(self, *parts: str) -> SemanticUri:
        if not parts:
            return self
        joined_segs: list[str] = self.rel_path.split("/") if self.rel_path else []
        for idx, part in enumerate(parts):
            require_pure_str(part, "SemanticUri.join part", non_empty=True)
            if part.startswith(("/", "\\")) or ":" in part or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in part):
                raise ValueError(f"Invalid SemanticUri.join segment: {part!r}")
            sub_segs = [s for s in part.replace("\\", "/").split("/") if s]
            if not sub_segs:
                raise ValueError(f"Empty SemanticUri.join segment: {part!r}")
            for sub_idx, seg in enumerate(sub_segs):
                if seg == "@":
                    if not joined_segs and idx == 0 and sub_idx == 0:
                        joined_segs.append(seg)
                        continue
                    raise ValueError(f"Module placeholder '@' forbidden in non-leading SemanticUri.join: {part!r}")
                validate_relative_segment(seg, label="SemanticUri.join segment")
                joined_segs.append(seg)
        return SemanticUri(scheme=self.scheme, rel_path="/".join(joined_segs))

    def __truediv__(self, part: str) -> SemanticUri:
        return self.join(part)

    def __str__(self) -> str:
        return f"{self.scheme}://{self.rel_path}"


@dataclass(frozen=True, slots=True)
class SpaceId:
    """Logical file space identifier: named '<owner>/<name>' or synthetic union '/<name>' (owner='')."""

    owner: str
    name: str

    def __post_init__(self) -> None:
        require_pure_str(self.owner, "SpaceId.owner")
        require_pure_str(self.name, "SpaceId.name", non_empty=True)
        clean_owner = self.owner.strip()
        if self.owner and not clean_owner:
            raise ValueError(f"SpaceId.owner cannot be whitespace-only: {self.owner!r}")
        if clean_owner and _MODULE_ID_RE.fullmatch(clean_owner) is None:
            raise ValueError(f"Invalid SpaceId.owner: {self.owner!r}")
        clean_name = self.name.strip()
        if not clean_name or _MODULE_ID_RE.fullmatch(clean_name) is None:
            raise ValueError(f"Invalid SpaceId.name: {self.name!r}")
        object.__setattr__(self, "owner", clean_owner)
        object.__setattr__(self, "name", clean_name)

    @classmethod
    def parse(cls, raw: str) -> SpaceId:
        require_pure_str(raw, "SpaceId", non_empty=True)
        cleaned = raw.strip()
        if "/" not in cleaned:
            raise ValueError(f"Invalid SpaceId (expected '<owner>/<name>' or '/<name>'): {raw!r}")
        owner_part, name_part = cleaned.split("/", 1)
        if "/" in name_part or not name_part:
            raise ValueError(f"Invalid SpaceId format: {raw!r}")
        return cls(owner=owner_part, name=name_part)

    @property
    def is_synthetic(self) -> bool:
        return self.owner == ""

    def __str__(self) -> str:
        return f"/{self.name}" if not self.owner else f"{self.owner}/{self.name}"


@dataclass(frozen=True, slots=True)
class SpacePath:
    """Normalized POSIX relative path inside a logical space without leading slash or traversal."""

    rel_path: str

    def __post_init__(self) -> None:
        require_pure_str(self.rel_path, "SpacePath.rel_path", non_empty=True)
        if self.rel_path.startswith(("/", "\\")) or self.rel_path.endswith(("/", "\\")):
            raise ValueError(f"SpacePath forbids leading or trailing slashes: {self.rel_path!r}")
        norm = self.rel_path.replace("\\", "/")
        segs = norm.split("/")
        if not segs or any(not s for s in segs):
            raise ValueError(f"SpacePath forbids empty segments: {self.rel_path!r}")
        for seg in segs:
            validate_relative_segment(seg, label="SpacePath segment")
        object.__setattr__(self, "rel_path", "/".join(segs))

    @classmethod
    def parse(cls, raw: str) -> SpacePath:
        return cls(rel_path=raw)

    def __str__(self) -> str:
        return self.rel_path


@dataclass(frozen=True, slots=True)
class SnapshotGen:
    """Monotonically non-decreasing non-negative integer snapshot generation (>= 0)."""

    value: int

    def __post_init__(self) -> None:
        require_pure_int(self.value, "SnapshotGen.value", min_val=0, max_val=INT64_MAX)

    def next(self) -> SnapshotGen:
        return SnapshotGen(self.value + 1)

    def __lt__(self, other: SnapshotGen) -> bool:
        if not isinstance(other, SnapshotGen):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: SnapshotGen) -> bool:
        if not isinstance(other, SnapshotGen):
            return NotImplemented
        return self.value <= other.value


@dataclass(frozen=True, slots=True)
class EnvHash:
    """Immutable virtual environment hash identifier (lowercase hex, 16..64 chars)."""

    value: str

    def __post_init__(self) -> None:
        require_pure_str(self.value, "EnvHash.value", non_empty=True)
        cleaned = self.value.strip()
        if _ENV_HASH_RE.fullmatch(cleaned) is None:
            raise ValueError(f"EnvHash requires 16..64 lowercase hex characters, got {self.value!r}")
        object.__setattr__(self, "value", cleaned)

    def short(self, length: int = 16) -> str:
        require_pure_int(length, "EnvHash.short length", min_val=1, max_val=64)
        if length > len(self.value):
            raise ValueError(f"Requested short length {length} exceeds EnvHash length {len(self.value)}.")
        return self.value[:length]

    def __str__(self) -> str:
        return self.value


def _validate_windows_path_str(path_str: str) -> None:
    if _WIN_DEVICE_NS_RE.match(path_str) is not None:
        raise ValueError(f"Win32 device or verbatim namespace forbidden in HostPath: {path_str!r}")
    if path_str.startswith(("\\\\", "//")):
        unc_parts = [p for p in re.split(r"[\\/]+", path_str.lstrip("\\/")) if p]
        if len(unc_parts) < 2:
            raise ValueError(f"Incomplete Windows UNC path in HostPath: {path_str!r}")
        server, share = unc_parts[0], unc_parts[1]
        if ":" in server or ":" in share or not is_valid_relative_segment(server) or not is_valid_relative_segment(share):
            raise ValueError(f"Invalid UNC server/share component in HostPath: {path_str!r}")
        for seg in unc_parts[2:]:
            if ":" in seg or (seg not in (".", "..") and not is_valid_relative_segment(seg)):
                raise ValueError(f"Invalid cross-platform path segment {seg!r} in HostPath: {path_str!r}")
        return
    pw = PureWindowsPath(path_str)
    drv = pw.drive
    if len(drv) != 2 or not drv[0].isascii() or not drv[0].isalpha() or drv[1] != ":" or not pw.root:
        raise ValueError(f"Invalid Windows drive anchor in HostPath: {path_str!r}")
    tail = path_str[len(pw.anchor) :]
    if ":" in tail:
        raise ValueError(f"Colon / NTFS stream syntax forbidden in HostPath: {path_str!r}")
    for seg in re.split(r"[\\/]+", tail):
        if seg and seg not in (".", "..") and not is_valid_relative_segment(seg):
            raise ValueError(f"Invalid cross-platform path segment {seg!r} in HostPath: {path_str!r}")


def _validate_host_path_segments(path_str: str) -> None:
    if IS_WINDOWS:
        _validate_windows_path_str(path_str)
        return
    p_obj = Path(path_str)
    tail = path_str[len(p_obj.anchor) :] if p_obj.anchor else path_str
    if ":" in tail:
        raise ValueError(f"Colon / NTFS stream syntax forbidden in HostPath: {path_str!r}")
    for seg in re.split(r"/+", tail):
        if seg and seg not in (".", "..") and not is_valid_relative_segment(seg):
            raise ValueError(f"Invalid cross-platform path segment {seg!r} in HostPath: {path_str!r}")


def _strip_win_extended_prefix(path_str: str) -> str:
    if path_str.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path_str[8:]
    if path_str.startswith("\\\\?\\") and len(path_str) >= 6 and path_str[4].isalpha() and path_str[5] == ":":
        return path_str[4:]
    return path_str


def safe_realpath(raw_path: str) -> str:
    """Resolve realpath while stripping transient Windows extended drive/UNC prefixes left by ntpath races."""
    require_pure_str(raw_path, "raw_path")
    rp = os.path.realpath(raw_path)
    if IS_WINDOWS and not raw_path.startswith("\\\\?\\"):
        return _strip_win_extended_prefix(rp)
    return rp


def _resolve_canonical_host_path(raw_str: str) -> Path:
    seps = ("/", "\\") if IS_WINDOWS else ("/",)
    anchor = Path(raw_str).anchor
    if len(raw_str) > len(anchor) and raw_str.endswith(seps):
        real_dir = Path(safe_realpath(raw_str))
        stripped = raw_str.rstrip("/\\" if IS_WINDOWS else "/")
        if (os.path.lexists(real_dir) or os.path.islink(stripped)) and not real_dir.is_dir():
            raise ValueError(f"Trailing path separator on non-directory HostPath: {raw_str!r}")
        return real_dir
    parent_str, tail = os.path.split(raw_str)
    if tail in ("", ".", ".."):
        return Path(safe_realpath(raw_str))
    real_parent = Path(safe_realpath(parent_str))
    cand = real_parent / tail
    if (
        os.path.islink(cand)
        and os.path.normcase(real_parent.name) in ("bin", "scripts")
        and (real_parent.parent / "pyvenv.cfg").is_file()
    ):
        real_target = safe_realpath(str(cand))
        if os.path.isfile(real_target) and not os.path.isdir(real_target):
            return cand
    return Path(safe_realpath(str(cand)))


INT64_MIN: Final[int] = -(1 << 63)
INT64_MAX: Final[int] = (1 << 63) - 1


def _parse_bounded_json_int(token: str) -> int:
    digits = token[1:] if token[:1] in ("+", "-") else token
    if len(digits) > 20:
        raise ValueError("JSON integer out of int64 range.")
    val = int(token)
    if not (INT64_MIN <= val <= INT64_MAX):
        raise ValueError("JSON integer out of int64 range.")
    return val


def require_pure_str(val: object, label: str = "value", *, non_empty: bool = False) -> str:
    if type(val) is not str:
        raise ValueError(f"{label} must be an exact str, got {val!r}")
    val.encode("utf-8")
    if non_empty and not val.strip():
        raise ValueError(f"{label} must be a non-empty plain str.")
    return val


def require_pure_int(
    val: object,
    label: str = "value",
    *,
    min_val: Optional[int] = INT64_MIN,
    max_val: Optional[int] = INT64_MAX,
) -> int:
    if type(val) is not int:
        raise ValueError(f"{label} must be an exact int, got {val!r}")
    if (min_val is not None and val < min_val) or (max_val is not None and val > max_val):
        raise ValueError(f"{label} must be in [{min_val}, {max_val}], got {val!r}")
    return val


def invoke_observer_safely(fn: Callable[[], object]) -> None:
    """Execute an observer or progress callback isolating Exception, SystemExit, and GeneratorExit."""
    try:
        fn()
    except (Exception, SystemExit, GeneratorExit):
        return


def decrement_ref_count(table: dict[_T, int], key: _T) -> int:
    """Decrement positive integer ref-count for truthy key, popping entry when <= 0."""
    if not key:
        return 0
    rem = table.get(key, 0) - 1
    if rem <= 0:
        table.pop(key, None)
        return 0
    table[key] = rem
    return rem


def require_pure_bool(val: object, label: str = "value") -> bool:
    if type(val) is not bool:
        raise ValueError(f"{label} must be a bool, got {val!r}")
    return val


def require_typed_tuple(items: object, elem_type: type[_T], label: str = "items") -> tuple[_T, ...]:
    if isinstance(items, (str, bytes, bytearray, memoryview)) or not isinstance(items, Sequence):
        raise ValueError(f"{label} must be a non-string Sequence of {elem_type.__name__}.")
    tup = tuple(items)
    exact_scalars = (str, int, float, bool)
    for item in tup:
        if elem_type in exact_scalars:
            if type(item) is not elem_type:
                raise ValueError(f"{label} elements must be exact {elem_type.__name__}, got {item!r}")
        elif not isinstance(item, elem_type):
            raise ValueError(f"{label} elements must be {elem_type.__name__}, got {item!r}")
        if elem_type is str and type(item) is str:
            item.encode("utf-8")
    return tup


def require_typed_frozenset(items: object, elem_type: type[_T], label: str = "items") -> frozenset[_T]:
    """Validate an arbitrary non-string/bytes Iterable into a strongly typed frozenset."""
    if isinstance(items, (str, bytes, bytearray, memoryview)) or not isinstance(items, Iterable):
        raise ValueError(f"{label} must be an Iterable of {elem_type.__name__} (not str/bytes), got {items!r}")
    return frozenset(require_typed_tuple(tuple(items), elem_type, label))


def is_valid_type_annotation(tp_val: object) -> bool:
    return not isinstance(tp_val, bool) and (isinstance(tp_val, type) or get_origin(tp_val) is not None)


def _check_strict_json_scalar(val: object, *, label: str) -> JsonPrimitive:
    if isinstance(val, Enum):
        raise ValueError(f"{label} forbids unencoded Enum {type(val).__name__}")
    if val is None or type(val) is bool:
        return val
    if type(val) is int:
        if not (INT64_MIN <= val <= INT64_MAX):
            raise ValueError(f"{label} integer out of int64 range: {val!r}")
        return val
    if type(val) is float:
        if not math.isfinite(val):
            raise ValueError(f"{label} float must be finite: {val!r}")
        return val
    if type(val) is str:
        val.encode("utf-8")
        return val
    if isinstance(val, (int, float, str)):
        raise ValueError(f"{label} forbids custom scalar subclass {type(val).__name__}")
    raise TypeError(f"{label} contains unsupported JSON type {type(val).__name__}")


def validate_json_primitive(val: object, label: str = "payload") -> JsonPrimitive:
    try:
        return _check_strict_json_scalar(val, label=label)
    except TypeError as exc:
        raise ValueError(f"{label} contains unsupported JSON type {type(val).__name__}") from exc


def _walk_strict_json(
    cur: object,
    depth: int,
    max_depth: int,
    label: str,
    *,
    clone: bool,
) -> JsonValue:
    if depth > max_depth:
        raise ValueError(f"{label} exceeded maximum JSON nesting depth ({max_depth}).")
    if isinstance(cur, Mapping):
        out_map: MutableJsonObject = {}
        for k, v in cur.items():
            if type(k) is not str:
                raise TypeError(f"{label} mapping key must be exact str, got {type(k).__name__}")
            k.encode("utf-8")
            val = _walk_strict_json(v, depth + 1, max_depth, label, clone=clone)
            if clone:
                out_map[k] = val
        return out_map
    if isinstance(cur, (list, tuple)):
        if clone:
            return [_walk_strict_json(item, depth + 1, max_depth, label, clone=True) for item in cur]
        for item in cur:
            _walk_strict_json(item, depth + 1, max_depth, label, clone=False)
        return None
    return _check_strict_json_scalar(cur, label=label)


def validate_wire_json_object(
    payload: object,
    *,
    max_depth: int = MAX_ENVELOPE_JSON_DEPTH,
    label: str = "payload",
) -> None:
    """Validate an outbound JSON object symmetrically with strict_parse_json_object."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"{label} must be a JSON object Mapping, got {type(payload).__name__}")
    try:
        _walk_strict_json(payload, 0, max_depth, label, clone=False)
    except RecursionError as exc:
        raise ValueError(f"{label} exceeded maximum JSON recursion depth.") from exc


def clone_strict_json_object(
    payload: object,
    *,
    max_depth: int = MAX_USER_JSON_DEPTH,
    label: str = "payload",
) -> MutableJsonObject:
    """Deep-validate and deep-copy a JSON object (int64, UTF-8, finite float, no Enum, no container aliasing)."""
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object Mapping, got {payload!r}")
    try:
        cloned = _walk_strict_json(payload, 0, max_depth, label, clone=True)
    except (TypeError, RecursionError) as exc:
        raise ValueError(f"{label} validation failed: {exc}") from exc
    if not isinstance(cloned, dict):
        raise ValueError(f"{label} must clone to dict.")
    return cloned


def require_non_none(val: Optional[_T], message: str = "Expected non-None invariant") -> _T:
    """Narrow an Optional value at runtime under both standard and -O optimized execution."""
    if val is None:
        raise RuntimeError(message)
    return val


def _reject_duplicate_json_keys(pairs: list[tuple[str, JsonValue]]) -> MutableJsonObject:
    out: MutableJsonObject = {}
    for key, val in pairs:
        if key in out:
            raise ValueError(f"Duplicate JSON object key rejected: {key!r}")
        out[key] = val
    return out


def strict_parse_json_object(raw_text: str) -> MutableJsonObject:
    """Parse a JSON object rejecting non-str input, deep recursion, duplicate keys, NaN/Inf, and surrogates."""
    require_pure_str(raw_text, "raw_text")

    def _parse_float(token: str) -> float:
        val = float(token)
        if not math.isfinite(val):
            raise ValueError(f"Overflowing non-finite JSON float rejected: {token}")
        return val

    def _reject_const(token: str) -> None:
        raise ValueError(f"Non-finite JSON constant rejected: {token}")

    try:
        decoded = json.loads(
            raw_text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_const,
            parse_float=_parse_float,
            parse_int=_parse_bounded_json_int,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting depth limit exceeded.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Expected top-level JSON object.")
    validate_wire_json_object(decoded, max_depth=MAX_PARSE_JSON_DEPTH, label="JSON")
    return decoded


MAX_SAFE_WAIT_SEC: Final[float] = min(86400.0 * 7.0, float(threading.TIMEOUT_MAX) * 0.5)


def safe_real_to_float(val: object, *, label: str = "value") -> float:
    """Convert exact int/float (excluding bool/Enum/subclasses) to pure float, clamping huge ints within [-1e18, 1e18]."""
    if type(val) not in (int, float):
        raise ValueError(f"{label} must be an exact int or float, got {val!r}")
    if type(val) is int:
        return float(min(10**18, max(-(10**18), val)))
    return val


def validate_min_sec(min_sec: float) -> float:
    """Validate non-negative finite minimum wait bound clamped to MAX_SAFE_WAIT_SEC."""
    f_min = safe_real_to_float(min_sec, label="min_sec")
    if not math.isfinite(f_min) or f_min < 0.0:
        raise ValueError(f"min_sec must be finite and >= 0, got {min_sec!r}")
    return min(MAX_SAFE_WAIT_SEC, f_min)


def clamp_wait_sec(timeout_sec: Optional[float], *, min_sec: float = 0.0) -> Optional[float]:
    """Validate optional wait seconds (rejecting bool and NaN) and clamp within [min_sec, MAX_SAFE_WAIT_SEC]."""
    safe_min = validate_min_sec(min_sec)
    if timeout_sec is None:
        return None
    f_val = safe_real_to_float(timeout_sec, label="timeout_sec")
    if math.isnan(f_val):
        raise ValueError(f"timeout_sec must not be bool or NaN, got {timeout_sec!r}")
    return min(MAX_SAFE_WAIT_SEC, max(safe_min, f_val))
