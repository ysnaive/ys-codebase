"""GitignoreMaterializer: deterministic managed block synthesizer with Zero-Touch idempotency."""

from __future__ import annotations

import fnmatch
import re
from typing import Optional

from core.filesystem.space.registry import SpaceRegistry, spc_compile_gitignore_rules
from core.filesystem.space.rules import (
    GitignoreSyncResult,
    SpcControlPlaneRoots,
    SpcRuleItem,
    spc_check_space_uri_owner_boundary,
    spc_compute_rel_str,
    spc_is_control_plane_reserved_path,
    spc_sort_owner_keys,
)
from core.filesystem.vfs import KernelVfs
from core.foundation.errors import YscbError
from core.foundation.primitives import ModuleId, SemanticUri


_GITIGNORE_WILDCARD_CHARS = frozenset({"*", "?", "["})
_RESERVED_GITIGNORE_ROOT_FILES = (
    ".gitignore",
    "yscb.config.json",
    "yscb.config.local.json",
    "yscb.py",
)


def _targets_reserved_gitignore_control_name(
    norm_pat: str,
    control_roots: Optional[SpcControlPlaneRoots] = None,
) -> bool:
    raw = norm_pat.lstrip("!").strip().replace("\\", "/")
    if not raw:
        return False
    is_dir_only = raw.endswith("/")
    cur = raw
    while True:
        if cur.startswith("./"):
            cur = cur[2:]
        elif cur.startswith("**/"):
            cur = cur[3:]
        elif cur.startswith("/"):
            cur = cur[1:]
        else:
            break
    cur = cur.rstrip("/").lower()
    if not cur:
        return False
    if cur in ("*", "**"):
        return True
    segs = [seg for seg in cur.split("/") if seg and seg not in (".", "**")]
    if not segs:
        return True

    reserved_dirs: set[str] = {".yscb", ".git"}
    if (
        control_roots is not None
        and control_roots.yscb_root is not None
        and control_roots.proj_root is not None
    ):
        yscb_rel = spc_compute_rel_str(control_roots.yscb_root.path, control_roots.proj_root.path)
        if yscb_rel:
            reserved_dirs.add(yscb_rel.split("/", 1)[0].lower())

    for seg in segs:
        if any(fnmatch.fnmatchcase(ctrl_dir, seg) for ctrl_dir in reserved_dirs):
            return True

    if not is_dir_only and len(segs) == 1:
        leaf_pat = segs[0]
        if any(fnmatch.fnmatchcase(rf, leaf_pat) for rf in _RESERVED_GITIGNORE_ROOT_FILES):
            return True
    return False


def _anchor_gitignore_pattern(
    rule_item: SpcRuleItem,
    fallback_owner: str,
    control_roots: SpcControlPlaneRoots,
    vfs: KernelVfs,
    *,
    is_exemption: bool,
) -> Optional[str]:
    proj_root = control_roots.proj_root
    bind_owner = rule_item.source_space.owner or fallback_owner
    cleaned = rule_item.raw_pattern.strip()
    if not cleaned or cleaned.startswith("#"):
        return None
    if cleaned.startswith("!"):
        cleaned = cleaned[1:].strip()
        is_exemption = True
    if not cleaned:
        return None

    trailing_slash = cleaned.endswith(("/", "\\"))
    if "://" in cleaned:
        if proj_root is None:
            return None
        scheme_part, rest_part = cleaned.split("://", 1)
        scheme_clean = scheme_part.strip()
        rest_clean = rest_part.strip().lstrip("/\\").replace("\\", "/").rstrip("/")
        if not scheme_clean:
            return None

        wildcard_idx = -1
        for idx, ch in enumerate(rest_clean):
            if ch in _GITIGNORE_WILDCARD_CHARS:
                wildcard_idx = idx
                break

        if wildcard_idx == -1:
            base_rel = rest_clean
            glob_tail = ""
        else:
            static_prefix = rest_clean[:wildcard_idx]
            if "/" in static_prefix:
                base_rel, _ = static_prefix.rsplit("/", 1)
                glob_tail = rest_clean[len(base_rel) + 1 :]
            else:
                base_rel = ""
                glob_tail = rest_clean

        raw_uri_str = f"{scheme_clean}://{base_rel}" if base_rel else f"{scheme_clean}://"
        try:
            parsed_uri = SemanticUri.parse(raw_uri_str)
            if spc_check_space_uri_owner_boundary(parsed_uri, bind_owner, is_readonly_space=False) is not None:
                return None
            if parsed_uri.uses_module_placeholder:
                if not bind_owner or bind_owner == "project":
                    return None
                parsed_uri = parsed_uri.bind_module(ModuleId(bind_owner))
            resolved_hp = vfs.try_get_physical_path(parsed_uri)
        except (ValueError, YscbError):
            return None
        if resolved_hp is None:
            return None
        if bind_owner != "core" and spc_is_control_plane_reserved_path(resolved_hp, control_roots):
            return None
        rel_str = spc_compute_rel_str(resolved_hp.path, proj_root.path)
        if rel_str is None:
            return None
        if rel_str == "":
            if not glob_tail:
                return None
            combined_rel = glob_tail
        else:
            combined_rel = f"{rel_str}/{glob_tail}" if glob_tail else rel_str
        anchored = f"/{combined_rel}"
        if trailing_slash and not anchored.endswith("/"):
            anchored = f"{anchored}/"
        if bind_owner != "core" and _targets_reserved_gitignore_control_name(anchored, control_roots):
            return None
        return f"!{anchored}" if is_exemption else anchored

    norm_glob = cleaned.replace("\\", "/")
    if bind_owner != "core" and _targets_reserved_gitignore_control_name(norm_glob, control_roots):
        return None
    return f"!{norm_glob}" if is_exemption else norm_glob


class GitignoreMaterializer:
    """Single-file managed block synthesizer for project://.gitignore."""

    BEGIN_MARKER: str = "# === YSCB MANAGED GITIGNORE BEGIN ==="
    END_MARKER: str = "# === YSCB MANAGED GITIGNORE END ==="

    def __init__(self, registry: SpaceRegistry, vfs: KernelVfs) -> None:
        if not isinstance(registry, SpaceRegistry):
            raise ValueError(f"GitignoreMaterializer requires SpaceRegistry, got {registry!r}")
        if not isinstance(vfs, KernelVfs):
            raise ValueError(f"GitignoreMaterializer requires KernelVfs, got {vfs!r}")
        self._registry: SpaceRegistry = registry
        self._vfs: KernelVfs = vfs

    def render_managed_block(self) -> tuple[str, dict[str, tuple[str, ...]]]:
        try:
            proj_root = self._vfs.try_get_physical_path(SemanticUri("project", ""))
        except YscbError:
            proj_root = None
        try:
            yscb_root = self._vfs.try_get_physical_path(SemanticUri("yscb", ""))
        except YscbError:
            yscb_root = None
        try:
            host_dir = self._vfs.try_get_physical_path(SemanticUri("yscb.host", ""))
        except YscbError:
            host_dir = None
        control_roots = SpcControlPlaneRoots(
            yscb_root=yscb_root,
            host_dir=host_dir,
            proj_root=proj_root,
        )

        compiled_rules_by_owner = spc_compile_gitignore_rules(self._registry)
        ordered_owners = spc_sort_owner_keys(tuple(compiled_rules_by_owner.keys()))
        groups: dict[str, tuple[str, ...]] = {}

        for owner in ordered_owners:
            eff_inc, eff_exc = compiled_rules_by_owner[owner]
            pos_patterns: list[str] = []
            neg_patterns: list[str] = []
            seen: set[str] = set()

            for raw_inc in eff_inc:
                norm_inc = _anchor_gitignore_pattern(
                    raw_inc,
                    owner,
                    control_roots,
                    self._vfs,
                    is_exemption=False,
                )
                if norm_inc is not None and norm_inc not in seen:
                    seen.add(norm_inc)
                    if norm_inc.startswith("!"):
                        neg_patterns.append(norm_inc)
                    else:
                        pos_patterns.append(norm_inc)

            for raw_exc in eff_exc:
                norm_exc = _anchor_gitignore_pattern(
                    raw_exc,
                    owner,
                    control_roots,
                    self._vfs,
                    is_exemption=True,
                )
                if norm_exc is not None and norm_exc not in seen:
                    seen.add(norm_exc)
                    neg_patterns.append(norm_exc)

            if pos_patterns or neg_patterns:
                if owner == "core":
                    groups[owner] = (*pos_patterns, *neg_patterns)
                else:
                    groups[owner] = (*sorted(pos_patterns), *sorted(neg_patterns))

        lines: list[str] = [
            self.BEGIN_MARKER,
            "# Auto-managed by YSCB core.filesystem.space. Do not edit this block manually.",
        ]
        for owner in ordered_owners:
            pats = groups.get(owner)
            if not pats:
                continue
            lines.append(f"# [{owner}]")
            lines.extend(pats)
        lines.append(self.END_MARKER)
        return ("\n".join(lines), groups)

    def sync(self) -> GitignoreSyncResult:
        target_uri = SemanticUri("project", ".gitignore")
        has_existing = self._vfs.exists(target_uri)
        existing_bytes = self._vfs.read_bytes(target_uri) if has_existing else b""
        existing_text = existing_bytes.decode("utf-8") if existing_bytes else ""

        block_text, groups = self.render_managed_block()
        managed_re = re.compile(
            rf"{re.escape(self.BEGIN_MARKER)}[\s\S]*?{re.escape(self.END_MARKER)}",
            re.MULTILINE,
        )

        if managed_re.search(existing_text):
            merged_text = managed_re.sub(lambda _m: block_text, existing_text, count=1)
            if not merged_text.endswith("\n"):
                merged_text = f"{merged_text}\n"
        else:
            trimmed = existing_text.rstrip("\r\n")
            if trimmed.strip():
                merged_text = f"{trimmed}\n\n{block_text}\n"
            else:
                merged_text = f"{block_text}\n"

        merged_bytes = merged_text.encode("utf-8")
        if has_existing and existing_bytes == merged_bytes:
            return GitignoreSyncResult(changed=False, target_uri=target_uri, groups=groups)

        self._vfs.write_bytes_through_readonly(target_uri, merged_bytes)
        return GitignoreSyncResult(changed=True, target_uri=target_uri, groups=groups)
