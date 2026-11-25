"""Out-of-band RFC 6901 JSON Pointer provenance graph without payload magic keys."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from core.foundation.primitives import (
    JsonValue,
    MutableJsonObject,
    require_pure_str,
    require_typed_tuple,
)


def ctb_escape_pointer_token(token: str) -> str:
    """Escape a single JSON Pointer reference token per RFC 6901 (~0 and ~1)."""
    return token.replace("~", "~0").replace("/", "~1")


def ctb_join_pointer(parent: str, token: str) -> str:
    """Append an escaped RFC 6901 reference token to ``parent`` JSON Pointer."""
    return f"{parent}/{ctb_escape_pointer_token(token)}"


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    """Immutable provenance record for a single JSON Pointer node."""

    json_pointer: str
    contributors: tuple[str, ...]
    final_owner: str

    def __post_init__(self) -> None:
        require_pure_str(self.json_pointer, "ProvenanceEntry.json_pointer")
        if self.json_pointer != "" and not self.json_pointer.startswith("/"):
            raise ValueError(
                f"ProvenanceEntry.json_pointer must be '' or start with '/', got {self.json_pointer!r}"
            )
        tup = require_typed_tuple(self.contributors, str, "ProvenanceEntry.contributors")
        if not tup or any(not item.strip() for item in tup):
            raise ValueError("ProvenanceEntry.contributors must contain at least one non-empty donor string.")
        object.__setattr__(self, "contributors", tup)
        require_pure_str(self.final_owner, "ProvenanceEntry.final_owner", non_empty=True)


class ProvenanceGraph:
    """Out-of-band provenance index supporting exact RFC 6901 JSON Pointer origin queries."""

    def __init__(self, entries: Mapping[str, ProvenanceEntry]) -> None:
        if not isinstance(entries, Mapping):
            raise ValueError(f"ProvenanceGraph.entries must be a Mapping, got {entries!r}")
        validated: dict[str, ProvenanceEntry] = {}
        for ptr_key in sorted(entries.keys()):
            require_pure_str(ptr_key, "ProvenanceGraph pointer key")
            entry = entries[ptr_key]
            if not isinstance(entry, ProvenanceEntry):
                raise ValueError(f"ProvenanceGraph value at {ptr_key!r} must be ProvenanceEntry, got {entry!r}")
            if entry.json_pointer != ptr_key:
                raise ValueError(
                    f"ProvenanceGraph key {ptr_key!r} mismatches entry.json_pointer {entry.json_pointer!r}"
                )
            validated[ptr_key] = entry
        self._entries: Mapping[str, ProvenanceEntry] = MappingProxyType(validated)

    def origin_for(self, json_pointer: str) -> Optional[ProvenanceEntry]:
        """Return the ProvenanceEntry for an exact RFC 6901 JSON Pointer, or None."""
        require_pure_str(json_pointer, "json_pointer")
        return self._entries.get(json_pointer)

    def contributors_for(self, json_pointer: str) -> tuple[str, ...]:
        """Return the ordered tuple of contributors for ``json_pointer``, or ``()`` if absent."""
        require_pure_str(json_pointer, "json_pointer")
        entry = self._entries.get(json_pointer)
        return entry.contributors if entry is not None else ()

    def pointers_by_donor(self, donor: str) -> tuple[str, ...]:
        """Return all sorted JSON Pointers to which ``donor`` contributed."""
        require_pure_str(donor, "donor", non_empty=True)
        return tuple(ptr for ptr, entry in self._entries.items() if donor in entry.contributors)

    def to_json(self) -> MutableJsonObject:
        """Export the provenance graph as a clean JSON-serializable dictionary."""
        out: MutableJsonObject = {}
        for ptr, entry in self._entries.items():
            out[ptr] = {
                "contributors": list(entry.contributors),
                "final_owner": entry.final_owner,
            }
        return out


class CtbProvenanceTracker:
    """Internal builder accumulating per-pointer contributor chains during topological merge."""

    def __init__(self) -> None:
        self._contributors: dict[str, list[str]] = {}
        self._owners: dict[str, str] = {}

    def has_donor(self, json_pointer: str, donor: str) -> bool:
        return donor in self._contributors.get(json_pointer, ())

    def touch(self, json_pointer: str, donor: str, *, update_owner: bool = True) -> None:
        chain = self._contributors.setdefault(json_pointer, [])
        if donor not in chain:
            chain.append(donor)
        if update_owner or json_pointer not in self._owners:
            self._owners[json_pointer] = donor

    def prune_descendants(self, json_pointer: str) -> None:
        if json_pointer == "":
            for key in [k for k in self._owners if k != ""]:
                self._owners.pop(key, None)
                self._contributors.pop(key, None)
            return
        prefix = f"{json_pointer}/"
        stale = [k for k in self._owners if k.startswith(prefix)]
        for key in stale:
            self._owners.pop(key, None)
            self._contributors.pop(key, None)

    def record_subtree(self, json_pointer: str, value: JsonValue, donor: str) -> None:
        self.touch(json_pointer, donor, update_owner=True)
        if isinstance(value, Mapping):
            for k, v in value.items():
                self.record_subtree(ctb_join_pointer(json_pointer, k), v, donor)
        elif isinstance(value, (list, tuple)):
            for idx, item in enumerate(value):
                self.record_subtree(f"{json_pointer}/{idx}", item, donor)

    def build(self) -> ProvenanceGraph:
        built: dict[str, ProvenanceEntry] = {}
        for ptr in sorted(self._owners.keys()):
            built[ptr] = ProvenanceEntry(
                json_pointer=ptr,
                contributors=tuple(self._contributors[ptr]),
                final_owner=self._owners[ptr],
            )
        return ProvenanceGraph(built)

