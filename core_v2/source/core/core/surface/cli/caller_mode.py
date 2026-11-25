"""Deterministic 5-layer CallerMode classifier and AI host dialect detector."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
import sys
from types import MappingProxyType
from typing import Final, Mapping, Optional, Protocol, Sequence

from core.foundation import require_pure_bool, require_pure_str, require_typed_tuple

_CI_BOOL_ENV_KEYS: Final[tuple[str, ...]] = (
    "CI",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "TF_BUILD",
    "BUILDKITE",
    "CIRCLECI",
    "TRAVIS",
)
_CI_NONEMPTY_ENV_KEYS: Final[tuple[str, ...]] = (
    "JENKINS_URL",
    "BITBUCKET_BUILD_NUMBER",
)
_ANTIGRAVITY_ENV_KEYS: Final[tuple[str, ...]] = (
    "ANTIGRAVITY_AGENT",
    "ANTIGRAVITY_CONVERSATION_ID",
    "ANTIGRAVITY_TRAJECTORY_ID",
    "ANTIGRAVITY_SESSION",
    "AGY_AGENT",
    "AGY_SESSION",
)
_CLAUDE_ENV_KEYS: Final[tuple[str, ...]] = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_SSE_PORT",
)
_CODEX_ENV_KEYS: Final[tuple[str, ...]] = (
    "CODEX_SANDBOX",
    "CODEX_THREAD_ID",
    "CODEX_CI",
)
_GEMINI_ENV_KEYS: Final[tuple[str, ...]] = ("GEMINI_CLI",)
_CURSOR_ENV_KEYS: Final[tuple[str, ...]] = ("CURSOR_AGENT",)
_OTHER_AGENT_ENV_KEYS: Final[tuple[str, ...]] = (
    "AIDER_SESSION",
    "WINDSURF_AGENT",
    "OPENCODE",
)
_AGENT_EXACT_ENV_KEYS: Final[tuple[str, ...]] = (
    *_ANTIGRAVITY_ENV_KEYS,
    *_CLAUDE_ENV_KEYS,
    *_CODEX_ENV_KEYS,
    *_GEMINI_ENV_KEYS,
    *_CURSOR_ENV_KEYS,
    *_OTHER_AGENT_ENV_KEYS,
)
_FALSY_TOKENS: Final[frozenset[str]] = frozenset({"", "0", "false", "no", "off"})


class CliInputStream(Protocol):
    """Minimal input stream contract supporting TTY detection and single-line prompts."""

    def isatty(self) -> bool: ...
    def readline(self) -> str: ...


class CliOutputStream(Protocol):
    """Minimal output stream contract supporting TTY detection and text emission."""

    def isatty(self) -> bool: ...
    def write(self, s: str) -> object: ...
    def flush(self) -> None: ...


class CallerMode(Enum):
    """Deterministic 5-layer CLI runtime caller classification."""

    HUMAN_TTY = "human"
    NON_TTY = "non_tty"
    AGENT = "agent"
    CI_PIPELINE = "ci"


@dataclass(frozen=True, slots=True)
class CallerEnvironment:
    """Resolved CLI caller mode, AI host dialect, and real bidirectional TTY status."""

    mode: CallerMode
    dialect: Optional[str] = None
    stdin_isatty: bool = False
    stdout_isatty: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mode, CallerMode):
            raise ValueError(f"CallerEnvironment.mode must be CallerMode, got {self.mode!r}")
        if self.dialect is not None:
            require_pure_str(self.dialect, "CallerEnvironment.dialect", non_empty=True)
        require_pure_bool(self.stdin_isatty, "CallerEnvironment.stdin_isatty")
        require_pure_bool(self.stdout_isatty, "CallerEnvironment.stdout_isatty")


def _is_env_truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() not in _FALSY_TOKENS


_EXPLICIT_MODE_RANK: Final[Mapping[str, int]] = MappingProxyType({
    "agent": 3,
    "ci": 3,
    "ci_pipeline": 3,
    "non_tty": 2,
    "human": 1,
})


def _normalize_upper_env(env_map: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    exact_seen: set[str] = set()
    for k, v in env_map.items():
        if not (isinstance(k, str) and isinstance(v, str)):
            continue
        up = k.upper()
        is_exact = k == up
        new_truthy = _is_env_truthy(v)
        if up not in out:
            out[up] = v
            if is_exact:
                exact_seen.add(up)
        else:
            old_truthy = _is_env_truthy(out[up])
            if new_truthy and not old_truthy:
                out[up] = v
                if is_exact:
                    exact_seen.add(up)
            elif new_truthy and old_truthy and is_exact and up not in exact_seen:
                out[up] = v
                exact_seen.add(up)
    return out


def _resolve_explicit_caller_mode_token(env_map: Mapping[str, str]) -> str:
    if "YSCB_CALLER_MODE" in env_map and isinstance(env_map["YSCB_CALLER_MODE"], str):
        exact_tok = env_map["YSCB_CALLER_MODE"].strip().lower()
        if exact_tok in _EXPLICIT_MODE_RANK:
            return exact_tok
    best_tok = ""
    best_rank = 0
    for k, v in env_map.items():
        if isinstance(k, str) and isinstance(v, str) and k.upper() == "YSCB_CALLER_MODE":
            cand = v.strip().lower()
            rank = _EXPLICIT_MODE_RANK.get(cand, 0)
            if rank > best_rank:
                best_rank = rank
                best_tok = cand
    return best_tok


def _resolve_term_token(env_map: Mapping[str, str], upper_env: Mapping[str, str]) -> str:
    if "TERM" in env_map and isinstance(env_map["TERM"], str) and env_map["TERM"].strip():
        return env_map["TERM"].strip().lower()
    for k, v in env_map.items():
        if isinstance(k, str) and isinstance(v, str) and k.upper() == "TERM" and v.strip().lower() == "dumb":
            return "dumb"
    return upper_env.get("TERM", "").strip().lower()


def _safe_isatty(stream: Optional[CliInputStream | CliOutputStream]) -> bool:
    if stream is None:
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _detect_host_dialect(upper_env: Mapping[str, str]) -> Optional[str]:
    if any(_is_env_truthy(upper_env.get(key)) for key in _ANTIGRAVITY_ENV_KEYS):
        return "nouns-antigravity"
    if any(_is_env_truthy(upper_env.get(key)) for key in _CLAUDE_ENV_KEYS):
        return "nouns-claude"
    if any(_is_env_truthy(upper_env.get(key)) for key in _CODEX_ENV_KEYS):
        return "nouns-codex"
    if any(_is_env_truthy(upper_env.get(key)) for key in _GEMINI_ENV_KEYS):
        return "nouns-gemini"
    if any(_is_env_truthy(upper_env.get(key)) for key in _CURSOR_ENV_KEYS):
        return "nouns-cursor"
    return None


def _matches_ci_env(upper_env: Mapping[str, str]) -> bool:
    for key in _CI_BOOL_ENV_KEYS:
        if _is_env_truthy(upper_env.get(key)):
            return True
    for key in _CI_NONEMPTY_ENV_KEYS:
        raw = upper_env.get(key)
        if raw is not None and raw.strip() and _is_env_truthy(raw):
            return True
    return False


def _matches_agent_env(upper_env: Mapping[str, str], extra_prefixes_upper: tuple[str, ...]) -> bool:
    for exact_key in _AGENT_EXACT_ENV_KEYS:
        if _is_env_truthy(upper_env.get(exact_key)):
            return True
    if not extra_prefixes_upper:
        return False
    for key, val in upper_env.items():
        if not _is_env_truthy(val):
            continue
        if any(key.startswith(pfx) for pfx in extra_prefixes_upper if pfx):
            return True
    return False


def detect_caller_environment(
    *,
    env: Optional[Mapping[str, str]] = None,
    stdin_stream: Optional[CliInputStream] = None,
    stdout_stream: Optional[CliOutputStream] = None,
    extra_agent_env_prefixes: Sequence[str] = (),
) -> CallerEnvironment:
    """Classify the active CLI caller across the 5-layer priority hierarchy."""
    raw_env: Mapping[str, str] = env if env is not None else os.environ
    upper_env = _normalize_upper_env(raw_env)
    eff_in: Optional[CliInputStream] = stdin_stream if stdin_stream is not None else sys.stdin
    eff_out: Optional[CliOutputStream] = stdout_stream if stdout_stream is not None else sys.stdout
    extra_pfxs_upper = tuple(
        s.strip().upper()
        for s in require_typed_tuple(extra_agent_env_prefixes, str, "extra_agent_env_prefixes")
        if s.strip()
    )

    stdin_tty = _safe_isatty(eff_in)
    stdout_tty = _safe_isatty(eff_out)
    both_tty = stdin_tty and stdout_tty
    is_agent_env = _matches_agent_env(upper_env, extra_pfxs_upper)
    is_ci_env = _matches_ci_env(upper_env)

    explicit_raw = _resolve_explicit_caller_mode_token(raw_env)
    if explicit_raw:
        if explicit_raw == "agent":
            return CallerEnvironment(CallerMode.AGENT, _detect_host_dialect(upper_env), stdin_tty, stdout_tty)
        if explicit_raw in ("ci", "ci_pipeline"):
            return CallerEnvironment(CallerMode.CI_PIPELINE, None, stdin_tty, stdout_tty)
        if explicit_raw == "non_tty":
            return CallerEnvironment(CallerMode.NON_TTY, None, stdin_tty, stdout_tty)
        if explicit_raw == "human" and both_tty and not is_agent_env and not is_ci_env:
            return CallerEnvironment(CallerMode.HUMAN_TTY, None, stdin_tty, stdout_tty)

    if is_agent_env:
        return CallerEnvironment(CallerMode.AGENT, _detect_host_dialect(upper_env), stdin_tty, stdout_tty)

    if is_ci_env:
        return CallerEnvironment(CallerMode.CI_PIPELINE, None, stdin_tty, stdout_tty)

    term_val = _resolve_term_token(raw_env, upper_env)
    if not stdin_tty or not stdout_tty or term_val == "dumb":
        return CallerEnvironment(CallerMode.NON_TTY, None, stdin_tty, stdout_tty)

    return CallerEnvironment(CallerMode.HUMAN_TTY, None, stdin_tty, stdout_tty)


def detect_caller_mode(
    *,
    env: Optional[Mapping[str, str]] = None,
    stdin_stream: Optional[CliInputStream] = None,
    stdout_stream: Optional[CliOutputStream] = None,
    extra_agent_env_prefixes: Sequence[str] = (),
) -> CallerMode:
    """Return the resolved CallerMode for the active CLI invocation."""
    return detect_caller_environment(
        env=env,
        stdin_stream=stdin_stream,
        stdout_stream=stdout_stream,
        extra_agent_env_prefixes=extra_agent_env_prefixes,
    ).mode
