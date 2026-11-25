"""12-hour throttled update detector with pre-stamped last_checked_at, cross-pruned urgency aggregation, and LF host drift check."""

from __future__ import annotations

import hashlib
from http.client import HTTPException
import os
import time
from typing import Final, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import urllib.request

from core.filesystem.fs import (
    MAX_JSON_FILE_BYTES,
    assert_no_symlink_raw_path,
    atomic_write_json,
    has_symlink_raw_path,
    read_json_dict,
    read_nofollow_regular_bytes,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.foundation.errors import YscbError
from core.foundation.primitives import (
    TEST_SANDBOX_ENV_KEY,
    HostPath,
    JsonObject,
    JsonValue,
    ModuleId,
    MutableJsonObject,
    SemVer4,
    require_pure_bool,
    require_pure_str,
)
from core.foundation.proc import is_public_env_truthy
from core.metadata.config import ConfigStore, ReleaseUrgency
from core.packaging.installer.models import (
    RemoteModuleIndex,
    UpdateCandidate,
    UpdateCheckReport,
    ins_utc_now_iso,
)
from core.packaging.installer.provider import (
    ProviderClient,
    ins_build_safe_http_opener,
    ins_is_provider_offline,
    ins_resolve_file_uri_to_host_path,
)

_URGENCY_RANK: Final[tuple[tuple[ReleaseUrgency, int], ...]] = (
    (ReleaseUrgency.OPTIONAL, 1),
    (ReleaseUrgency.RECOMMENDED, 2),
    (ReleaseUrgency.CRITICAL, 3),
)
_MAX_SCRIPT_BYTES: Final[int] = 4 * 1024 * 1024


def _rank_for_urgency(urgency: ReleaseUrgency) -> int:
    for urg_key, rank in _URGENCY_RANK:
        if urg_key == urgency:
            return rank
    return 2


def _normalize_lf_sha256(raw_bytes: bytes) -> str:
    lf_bytes = raw_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(lf_bytes).hexdigest()


def _decode_cached_candidates(raw_items: object) -> tuple[UpdateCandidate, ...]:
    if not isinstance(raw_items, list):
        return ()
    decoded: list[UpdateCandidate] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        raw_mod = item.get("module_id")
        raw_cur = item.get("current_version")
        raw_lat = item.get("latest_version")
        raw_urg = item.get("max_urgency")
        raw_sums = item.get("summaries", [])
        if (
            type(raw_mod) is not str
            or type(raw_cur) is not str
            or type(raw_lat) is not str
            or type(raw_urg) is not str
            or not isinstance(raw_sums, list)
            or any(type(s) is not str for s in raw_sums)
        ):
            continue
        try:
            decoded.append(
                UpdateCandidate(
                    module_id=ModuleId(raw_mod),
                    current_version=SemVer4.parse(raw_cur),
                    latest_version=SemVer4.parse(raw_lat),
                    max_urgency=ReleaseUrgency(raw_urg),
                    summaries=tuple(raw_sums),
                )
            )
        except ValueError:
            continue
    return tuple(decoded)


def _encode_candidates_json(candidates: tuple[UpdateCandidate, ...]) -> list[JsonValue]:
    out: list[JsonValue] = []
    for cand in candidates:
        out.append(
            {
                "module_id": cand.module_id.value,
                "current_version": str(cand.current_version),
                "latest_version": str(cand.latest_version),
                "max_urgency": cand.max_urgency.value,
                "summaries": list(cand.summaries),
            }
        )
    return out


def _evaluate_module_candidate(
    module_id: ModuleId,
    current_version: SemVer4,
    index: RemoteModuleIndex,
) -> Optional[UpdateCandidate]:
    active_newer: list[SemVer4] = []
    for cand_v in index.versions:
        if cand_v.is_build or cand_v <= current_version:
            continue
        rel_rec = index.releases.get(str(cand_v))
        if rel_rec is not None and (rel_rec.status != "active" or rel_rec.yanked):
            continue
        active_newer.append(cand_v)
    for rel_rec in index.releases.values():
        cand_v = rel_rec.version
        if (
            not cand_v.is_build
            and cand_v > current_version
            and rel_rec.status == "active"
            and not rel_rec.yanked
            and cand_v not in active_newer
        ):
            active_newer.append(cand_v)

    if not active_newer:
        return None
    latest_ver = max(active_newer)

    intermediate_vers: set[SemVer4] = set()
    for v in index.versions:
        if not v.is_build and current_version < v <= latest_ver:
            rec = index.releases.get(str(v))
            if rec is None or not rec.yanked:
                intermediate_vers.add(v)
    for rec in index.releases.values():
        if not rec.version.is_build and not rec.yanked and current_version < rec.version <= latest_ver:
            intermediate_vers.add(rec.version)

    max_urg = ReleaseUrgency.OPTIONAL
    has_any_rec = False
    collected_summaries: list[str] = []
    for step_ver in sorted(intermediate_vers):
        rec = index.releases.get(str(step_ver))
        if rec is None:
            continue
        has_any_rec = True
        if _rank_for_urgency(rec.urgency) > _rank_for_urgency(max_urg):
            max_urg = rec.urgency
        clean_sum = rec.summary.strip()
        if clean_sum and clean_sum not in collected_summaries:
            collected_summaries.append(clean_sum)

    if not has_any_rec:
        max_urg = ReleaseUrgency.RECOMMENDED

    return UpdateCandidate(
        module_id=module_id,
        current_version=current_version,
        latest_version=latest_ver,
        max_urgency=max_urg,
        summaries=tuple(collected_summaries),
    )


def _fetch_remote_or_local_yscb_bytes(
    host_dir: HostPath,
    self_update_url: str,
    timeout_sec: float,
) -> Optional[bytes]:
    cleaned = self_update_url.strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if lower.startswith(("http://", "https://")):
        chunks: list[bytes] = []
        total = 0
        try:
            parsed = urlparse(cleaned)
            _ = parsed.port
            if not parsed.hostname:
                return None
            req = urllib.request.Request(
                cleaned,
                headers={"User-Agent": "yscb-update-checker/2.0", "Connection": "close"},
            )
            opener = ins_build_safe_http_opener(cleaned, raise_security_error=False)
            with opener.open(req, timeout=timeout_sec) as resp:
                try:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > _MAX_SCRIPT_BYTES:
                            return None
                        chunks.append(chunk)
                finally:
                    resp.close()
            return b"".join(chunks)
        except URLError as exc:
            if isinstance(exc, HTTPError):
                try:
                    exc.close()
                except OSError:
                    pass
            return None
        except (HTTPException, TimeoutError, OSError, ValueError, YscbError):
            return None

    if lower.startswith("file://"):
        try:
            target_hp = ins_resolve_file_uri_to_host_path(cleaned)
        except YscbError:
            return None
    elif "://" in cleaned:
        return None
    else:
        raw_cand = cleaned if os.path.isabs(cleaned) else os.path.join(str(host_dir), cleaned)
        if has_symlink_raw_path(raw_cand):
            return None
        try:
            target_hp = host_dir.resolve_caller_relative(cleaned)
        except ValueError:
            return None

    try:
        return read_nofollow_regular_bytes(str(target_hp), max_bytes=_MAX_SCRIPT_BYTES)
    except OSError:
        return None


class UpdateChecker:
    """12-hour throttled update detector (pre-stamped last_checked_at, cross-pruned critical aggregation, yscb.py LF SHA-256 drift)."""

    DEFAULT_INTERVAL_SEC: float = 12 * 3600.0
    DEFAULT_TIMEOUT_SEC: float = 2.0

    def __init__(
        self,
        *,
        host_dir: HostPath,
        yscb_root: HostPath,
        config_store: ConfigStore,
        provider: ProviderClient,
        self_update_url: str,
    ) -> None:
        if not isinstance(host_dir, HostPath):
            raise ValueError(f"UpdateChecker.host_dir must be HostPath, got {host_dir!r}")
        if not isinstance(yscb_root, HostPath):
            raise ValueError(f"UpdateChecker.yscb_root must be HostPath, got {yscb_root!r}")
        if not isinstance(config_store, ConfigStore):
            raise ValueError(f"UpdateChecker.config_store must be ConfigStore, got {config_store!r}")
        if not isinstance(provider, ProviderClient):
            raise ValueError(f"UpdateChecker.provider must be ProviderClient, got {provider!r}")
        require_pure_str(self_update_url, "UpdateChecker.self_update_url")
        assert_no_symlink_raw_path(str(host_dir))
        assert_no_symlink_raw_path(str(yscb_root))
        self._host_dir = host_dir
        self._yscb_root = yscb_root
        self._config_store = config_store
        self._provider = provider
        self._self_update_url = self_update_url.strip()
        self._state_path = resolve_contained_subpath(yscb_root, ".cache", "core", "update_check.json")

    def _read_state_doc(self) -> Optional[JsonObject]:
        return read_json_dict(self._state_path, max_bytes=MAX_JSON_FILE_BYTES)

    def _write_state_doc(
        self,
        *,
        last_checked_at: float,
        checked_at_utc: str,
        candidates: tuple[UpdateCandidate, ...],
        yscb_host_drift: bool,
    ) -> None:
        payload: MutableJsonObject = {
            "last_checked_at": last_checked_at,
            "checked_at_utc": checked_at_utc,
            "yscb_host_drift": yscb_host_drift,
            "candidates": _encode_candidates_json(candidates),
        }
        try:
            atomic_write_json(self._state_path, payload)
        except (OSError, ValueError, YscbError):
            pass

    def _detect_host_script_drift(self) -> bool:
        if not self._self_update_url or ins_is_provider_offline(self._provider):
            return False
        local_script_hp = try_resolve_contained_subpath(self._host_dir, "yscb.py")
        if local_script_hp is None:
            return False
        try:
            local_bytes = read_nofollow_regular_bytes(str(local_script_hp), max_bytes=_MAX_SCRIPT_BYTES)
        except OSError:
            return False
        if local_bytes is None:
            return False
        remote_bytes = _fetch_remote_or_local_yscb_bytes(
            self._host_dir,
            self._self_update_url,
            self.DEFAULT_TIMEOUT_SEC,
        )
        if remote_bytes is None:
            return False
        return _normalize_lf_sha256(local_bytes) != _normalize_lf_sha256(remote_bytes)

    def check_if_due(self, *, force: bool = False, offline: bool = False) -> UpdateCheckReport:
        require_pure_bool(force, "force")
        require_pure_bool(offline, "offline")
        if (
            offline
            or ins_is_provider_offline(self._provider)
            or is_public_env_truthy("YSCB_OFFLINE")
            or is_public_env_truthy("YSCB_NO_UPDATE_CHECK")
            or is_public_env_truthy(TEST_SANDBOX_ENV_KEY)
        ):
            return UpdateCheckReport()

        now_epoch = time.time()
        cached_doc = self._read_state_doc()
        prev_epoch = 0.0
        prev_utc = ""
        prev_drift = False
        prev_cands: tuple[UpdateCandidate, ...] = ()
        if cached_doc is not None:
            raw_last = cached_doc.get("last_checked_at")
            if type(raw_last) in (int, float) and float(raw_last) > 0.0:
                prev_epoch = float(raw_last)
            raw_utc = cached_doc.get("checked_at_utc")
            if type(raw_utc) is str:
                prev_utc = raw_utc
            raw_drift = cached_doc.get("yscb_host_drift")
            if type(raw_drift) is bool:
                prev_drift = raw_drift
            prev_cands = _decode_cached_candidates(cached_doc.get("candidates"))

        if not force and prev_epoch > 0.0 and (now_epoch - prev_epoch) < self.DEFAULT_INTERVAL_SEC:
            return UpdateCheckReport(
                candidates=prev_cands,
                yscb_host_drift=prev_drift,
                checked_at_utc=prev_utc or ins_utc_now_iso(prev_epoch),
                throttled=True,
            )

        now_utc = ins_utc_now_iso(now_epoch)
        self._write_state_doc(
            last_checked_at=now_epoch,
            checked_at_utc=now_utc,
            candidates=prev_cands,
            yscb_host_drift=prev_drift,
        )

        try:
            host_cfg = self._config_store.load_host_config()
        except (OSError, ValueError, YscbError):
            return UpdateCheckReport(checked_at_utc=now_utc, throttled=False)

        found_candidates: list[UpdateCandidate] = []
        ordered_mods = sorted(
            host_cfg.installed_modules.keys(),
            key=lambda m: (0 if m.value == "core" else 1, m.value),
        )
        for mod_id in ordered_mods:
            inst_rec = host_cfg.installed_modules[mod_id]
            if inst_rec.version.is_build:
                continue
            mod_prov = inst_rec.provider.strip() if inst_rec.provider.strip() else host_cfg.default_provider
            try:
                idx = self._provider.fetch_index(mod_id, provider=mod_prov if mod_prov else None)
            except (YscbError, OSError, ValueError):
                continue
            cand = _evaluate_module_candidate(mod_id, inst_rec.version, idx)
            if cand is not None:
                found_candidates.append(cand)

        host_drift = self._detect_host_script_drift()
        final_cands = tuple(found_candidates)
        self._write_state_doc(
            last_checked_at=now_epoch,
            checked_at_utc=now_utc,
            candidates=final_cands,
            yscb_host_drift=host_drift,
        )
        return UpdateCheckReport(
            candidates=final_cands,
            yscb_host_drift=host_drift,
            checked_at_utc=now_utc,
            throttled=False,
        )
