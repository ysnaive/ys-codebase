"""Two-step single-use --approve=<token> store and 4x3 SecurityTier x CallerMode gate."""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import secrets
import time
from typing import Final, Mapping, Optional

from core.execution.runtime import LOCKS_SUBDIR, SecurityTier
from core.filesystem.fs import (
    FileLock,
    atomic_write_json,
    read_json_dict,
    resolve_contained_subpath,
)
from core.foundation import (
    DataclassCodec,
    ErrorCode,
    HostPath,
    JsonObject,
    MutableJsonObject,
    TaskId,
    YscbError,
    clamp_positive_sec,
    require_pure_bool,
    require_pure_str,
    require_typed_frozenset,
    safe_real_to_float,
)
from core.surface.cli.caller_mode import CallerMode, CliInputStream, CliOutputStream

_PENDING_APPROVALS_FILENAME: Final[str] = "pending_approvals.json"
_APPROVAL_LOCK_FILENAME: Final[str] = "pending_approvals.lock"
_DEFAULT_APPROVAL_TTL_SEC: Final[float] = 300.0


@dataclass(frozen=True, slots=True)
class PendingApprovalRecord:
    """Single-use pending approval token persisted in cache://core/pending_approvals.json."""

    token: str
    task_id: TaskId
    args_hash: str
    expires_at_epoch: float
    summary: str = ""

    def __post_init__(self) -> None:
        tok = require_pure_str(self.token, "PendingApprovalRecord.token", non_empty=True)
        if len(tok) < 6 or len(tok) > 32 or not all(ch in "0123456789abcdef" for ch in tok):
            raise ValueError(f"Invalid approval token hex format: {self.token!r}")
        if not isinstance(self.task_id, TaskId):
            raise ValueError(f"PendingApprovalRecord.task_id must be TaskId, got {self.task_id!r}")
        ah = require_pure_str(self.args_hash, "PendingApprovalRecord.args_hash", non_empty=True)
        if len(ah) != 64:
            raise ValueError(f"PendingApprovalRecord.args_hash must be 64-char SHA-256 hex, got {ah!r}")
        exp = safe_real_to_float(self.expires_at_epoch, label="expires_at_epoch")
        if exp <= 0.0:
            raise ValueError("PendingApprovalRecord.expires_at_epoch must be > 0")
        object.__setattr__(self, "expires_at_epoch", exp)
        require_pure_str(self.summary, "PendingApprovalRecord.summary")

    def to_json_dict(self) -> JsonObject:
        return {
            "token": self.token,
            "task_id": self.task_id.value,
            "args_hash": self.args_hash,
            "expires_at_epoch": self.expires_at_epoch,
            "summary": self.summary,
        }

    @classmethod
    def try_from_json(cls, doc: object) -> Optional[PendingApprovalRecord]:
        if not isinstance(doc, Mapping):
            return None
        try:
            raw_tok = require_pure_str(doc.get("token"), "token", non_empty=True)
            raw_tid = TaskId(require_pure_str(doc.get("task_id"), "task_id", non_empty=True))
            raw_ah = require_pure_str(doc.get("args_hash"), "args_hash", non_empty=True)
            raw_exp = safe_real_to_float(doc.get("expires_at_epoch"), label="expires_at_epoch")
            raw_sum = require_pure_str(doc.get("summary", ""), "summary")
            return cls(
                token=raw_tok,
                task_id=raw_tid,
                args_hash=raw_ah,
                expires_at_epoch=raw_exp,
                summary=raw_sum,
            )
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class SecurityGateResult:
    """Authorized CLI gate outcome carrying the single-task approval scope."""

    approval_scope: frozenset[TaskId] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approval_scope",
            require_typed_frozenset(self.approval_scope, TaskId, "SecurityGateResult.approval_scope"),
        )


def compute_approval_args_hash(task_id: TaskId, normalized_input: JsonObject) -> str:
    """Compute canonical SHA-256 fingerprint over {task_id, normalized_input}."""
    if not isinstance(task_id, TaskId):
        raise TypeError(f"task_id must be TaskId, got {type(task_id).__name__}")
    envelope: JsonObject = {
        "normalized_input": normalized_input,
        "task_id": task_id.value,
    }
    return DataclassCodec.canonical_hash(envelope)


class ApprovalTokenStore:
    """Atomic burn-on-use single-execution token store under cache://core/pending_approvals.json."""

    def __init__(self, cache_dir: HostPath, *, ttl_sec: float = _DEFAULT_APPROVAL_TTL_SEC) -> None:
        if not isinstance(cache_dir, HostPath):
            raise TypeError(f"cache_dir must be HostPath, got {type(cache_dir).__name__}")
        self._cache_dir = cache_dir
        self._ttl_sec = clamp_positive_sec(ttl_sec, min_sec=1.0, max_sec=86400.0, default_sec=_DEFAULT_APPROVAL_TTL_SEC)
        self._store_path = resolve_contained_subpath(cache_dir, "core", _PENDING_APPROVALS_FILENAME)
        self._lock_path = resolve_contained_subpath(cache_dir, LOCKS_SUBDIR, _APPROVAL_LOCK_FILENAME)

    def _load_active_locked(self, now_epoch: float) -> tuple[dict[str, PendingApprovalRecord], bool]:
        raw_doc = read_json_dict(self._store_path)
        if raw_doc is None:
            return ({}, False)
        raw_tokens = raw_doc.get("tokens")
        if not isinstance(raw_tokens, Mapping):
            return ({}, True)
        active: dict[str, PendingApprovalRecord] = {}
        dirty = False
        for key, item in raw_tokens.items():
            rec = PendingApprovalRecord.try_from_json(item)
            if rec is None or rec.token != key or rec.expires_at_epoch <= now_epoch:
                dirty = True
                continue
            active[rec.token] = rec
        return (active, dirty)

    def _save_active_locked(self, active: Mapping[str, PendingApprovalRecord]) -> None:
        tokens_obj: MutableJsonObject = {
            tok: rec.to_json_dict() for tok, rec in sorted(active.items())
        }
        atomic_write_json(self._store_path, {"schema_version": 1, "tokens": tokens_obj}, file_mode=0o600)

    def issue_token(
        self,
        task_id: TaskId,
        normalized_input: JsonObject,
        *,
        summary: str = "",
        now_epoch: Optional[float] = None,
    ) -> PendingApprovalRecord:
        """Mint and atomically persist a 6-8 hex char single-use approval token."""
        eff_now = time.time() if now_epoch is None else safe_real_to_float(now_epoch, label="now_epoch")
        args_hash = compute_approval_args_hash(task_id, normalized_input)
        lock = FileLock(self._lock_path, allow_transitions=False)
        lock.acquire(timeout_sec=5.0)
        try:
            active, _ = self._load_active_locked(eff_now)
            tok = secrets.token_hex(4)
            while tok in active:
                tok = secrets.token_hex(4)
            rec = PendingApprovalRecord(
                token=tok,
                task_id=task_id,
                args_hash=args_hash,
                expires_at_epoch=eff_now + self._ttl_sec,
                summary=require_pure_str(summary, "summary"),
            )
            active[tok] = rec
            self._save_active_locked(active)
            return rec
        finally:
            lock.release()

    def consume_token(
        self,
        token: str,
        task_id: TaskId,
        normalized_input: JsonObject,
        *,
        now_epoch: Optional[float] = None,
    ) -> PendingApprovalRecord:
        """Verify (token, task_id, args_hash, TTL) and burn the token immediately on match."""
        clean_tok = require_pure_str(token, "approve token", non_empty=True).strip().lower()
        eff_now = time.time() if now_epoch is None else safe_real_to_float(now_epoch, label="now_epoch")
        expected_hash = compute_approval_args_hash(task_id, normalized_input)
        lock = FileLock(self._lock_path, allow_transitions=False)
        lock.acquire(timeout_sec=5.0)
        try:
            raw_doc = read_json_dict(self._store_path)
            raw_map = raw_doc.get("tokens") if isinstance(raw_doc, Mapping) else None
            raw_entry = raw_map.get(clean_tok) if isinstance(raw_map, Mapping) else None
            matched_raw = PendingApprovalRecord.try_from_json(raw_entry)

            active, dirty = self._load_active_locked(eff_now)
            if matched_raw is not None and matched_raw.expires_at_epoch <= eff_now:
                if dirty:
                    self._save_active_locked(active)
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Approval token '{clean_tok}' for '{task_id}' has expired.",
                    remediation="Re-run the command without --approve to request a fresh single-use token.",
                    source_task=task_id.value,
                )

            rec = active.get(clean_tok)
            if rec is None:
                if dirty:
                    self._save_active_locked(active)
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Invalid or already consumed --approve token '{clean_tok}' for '{task_id}'.",
                    remediation="Request a fresh single-use authorization token and ask the developer for approval.",
                    source_task=task_id.value,
                )

            if rec.task_id != task_id or not hmac.compare_digest(rec.args_hash, expected_hash):
                if dirty:
                    self._save_active_locked(active)
                raise YscbError(
                    ErrorCode.SECURITY_GATED,
                    f"Approval token '{clean_tok}' does not match target task '{task_id}' or normalized arguments.",
                    remediation="Tokens are bound to exact (task_id, normalized_input); issue a new token for modified arguments.",
                    source_task=task_id.value,
                )

            del active[clean_tok]
            self._save_active_locked(active)
            return rec
        finally:
            lock.release()


def _extract_critical_confirm_phrase(normalized_input: JsonObject) -> str:
    raw_mods = normalized_input.get("modules")
    if isinstance(raw_mods, list) and len(raw_mods) == 1 and type(raw_mods[0]) is str and raw_mods[0].strip():
        return raw_mods[0].strip()
    raw_mod = normalized_input.get("module")
    if type(raw_mod) is str and raw_mod.strip():
        return raw_mod.strip()
    return "CONFIRM"


def evaluate_security_gate(
    *,
    task_id: TaskId,
    security_tier: SecurityTier,
    caller_mode: CallerMode,
    normalized_input: JsonObject,
    summary: str,
    token_store: ApprovalTokenStore,
    approve_token: Optional[str] = None,
    allow_noninteractive_approve: bool = True,
    ci_approve_gated: bool = False,
    stdin_stream: Optional[CliInputStream] = None,
    stderr_stream: Optional[CliOutputStream] = None,
) -> SecurityGateResult:
    """Enforce the 4x3 (SecurityTier x CallerMode) authorization matrix."""
    require_pure_bool(allow_noninteractive_approve, "allow_noninteractive_approve")
    require_pure_bool(ci_approve_gated, "ci_approve_gated")

    if security_tier in (SecurityTier.SAFE, SecurityTier.CONDITIONAL):
        if approve_token is not None:
            _ = token_store.consume_token(approve_token, task_id, normalized_input)
        return SecurityGateResult()

    if security_tier == SecurityTier.CRITICAL:
        if caller_mode != CallerMode.HUMAN_TTY:
            raise YscbError(
                ErrorCode.SECURITY_GATED,
                (
                    f"[CRITICAL] Task '{task_id}' ({summary}) permanently mutates or deletes protected data "
                    f"and is hard-blocked in {caller_mode.value} mode."
                ),
                remediation="Ask the human developer to run this CRITICAL command directly in an interactive terminal.",
                source_task=task_id.value,
            )
        phrase = _extract_critical_confirm_phrase(normalized_input)
        if stderr_stream is not None:
            stderr_stream.write(
                f"[CRITICAL WARNING] Task '{task_id}': {summary}\n"
                f"Type '{phrase}' to confirm permanent execution (Enter to cancel): "
            )
            stderr_stream.flush()
        answer = stdin_stream.readline().strip() if stdin_stream is not None else ""
        if answer != phrase:
            raise YscbError(
                ErrorCode.SECURITY_GATED,
                f"CRITICAL confirmation aborted for '{task_id}' (expected '{phrase}').",
                source_task=task_id.value,
            )
        return SecurityGateResult(approval_scope=frozenset({task_id}))

    if caller_mode in (CallerMode.AGENT, CallerMode.NON_TTY) and not allow_noninteractive_approve:
        raise YscbError(
            ErrorCode.SECURITY_GATED,
            f"[GATED] Non-interactive --approve is disabled by policy for '{task_id}'.",
            remediation="Execute this GATED command directly from an interactive human terminal.",
            source_task=task_id.value,
        )

    if approve_token is not None:
        _ = token_store.consume_token(approve_token, task_id, normalized_input)
        return SecurityGateResult(approval_scope=frozenset({task_id}))

    if caller_mode == CallerMode.HUMAN_TTY:
        if stderr_stream is not None:
            stderr_stream.write(f"[GATED] Task '{task_id}': {summary}\nProceed? [y/N]: ")
            stderr_stream.flush()
        reply = stdin_stream.readline().strip().lower() if stdin_stream is not None else ""
        if reply not in ("y", "yes"):
            raise YscbError(
                ErrorCode.SECURITY_GATED,
                f"User declined GATED confirmation for '{task_id}'.",
                source_task=task_id.value,
            )
        return SecurityGateResult(approval_scope=frozenset({task_id}))

    if caller_mode == CallerMode.CI_PIPELINE:
        if ci_approve_gated:
            return SecurityGateResult(approval_scope=frozenset({task_id}))
        raise YscbError(
            ErrorCode.SECURITY_GATED,
            f"[GATED] Task '{task_id}' ({summary}) is blocked by default in CI_PIPELINE mode.",
            remediation="Set YSCB_CI_APPROVE_GATED=1 or security.ci_approve_gated=true when explicitly authorized.",
            source_task=task_id.value,
        )

    issued = token_store.issue_token(task_id, normalized_input, summary=summary)
    raise YscbError(
        ErrorCode.SECURITY_GATED,
        (
            f"[GATED] Task '{task_id}' requires explicit developer authorization.\n"
            f"Impact: {summary or task_id.value}\n"
            f"Ask the developer for permission first, then re-run once with --approve={issued.token} "
            "(valid for 300s, single-use)."
        ),
        remediation=f"Obtain developer approval and re-execute with --approve={issued.token}",
        source_task=task_id.value,
    )
