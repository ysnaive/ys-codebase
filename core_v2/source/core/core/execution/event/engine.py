"""Pure-data double-buffered event bus, batch folding, static pre-filtering, and exact O(V) causal lineage."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
from types import MappingProxyType
from typing import Callable, Generic, Mapping, Optional, Protocol, Sequence, TypeVar

from core.foundation.codec import DataclassCodec, infer_sequence_element_dataclass
from core.foundation.errors import EventCycleError
from core.foundation.primitives import (
    EventId,
    JsonObject,
    JsonPrimitive,
    JsonValue,
    TaskId,
    clone_strict_json_object,
    is_valid_type_annotation,
    require_pure_str,
    require_typed_tuple,
    validate_json_primitive,
)

TPayload = TypeVar("TPayload")
TIn = TypeVar("TIn")
TIn_co = TypeVar("TIn_co", covariant=True)
ScopedHop = tuple[str, EventId]


class EventOrdering(Enum):
    """Controls batch folding vs. strict FIFO single-item delivery at freeze_and_swap."""

    UNORDERED = "unordered"
    ORDERED = "ordered"


def normalize_payload_filter(
    payload_filter: Optional[Mapping[str, Sequence[JsonPrimitive]]],
) -> Optional[Mapping[str, tuple[JsonPrimitive, ...]]]:
    """Validate and freeze a declarative event payload_filter mapping."""
    if payload_filter is None:
        return None
    if not isinstance(payload_filter, Mapping):
        raise ValueError(f"payload_filter must be a Mapping, got {payload_filter!r}")
    normalized: dict[str, tuple[JsonPrimitive, ...]] = {}
    for key, allowed in payload_filter.items():
        require_pure_str(key, "payload_filter key")
        if isinstance(allowed, (str, bytes, bytearray)) or not isinstance(allowed, Sequence):
            raise ValueError(f"payload_filter[{key!r}] must be a non-string Sequence of JsonPrimitive.")
        items = tuple(allowed)
        for item in items:
            validate_json_primitive(item, f"payload_filter[{key!r}]")
        normalized[key] = items
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class EventMetadata(Generic[TPayload]):
    """Static contract metadata for a strongly typed domain event."""

    event_id: EventId
    payload_type: type[TPayload]
    ordering: EventOrdering = EventOrdering.UNORDERED
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId):
            raise ValueError(f"EventMetadata.event_id must be EventId, got {self.event_id!r}")
        if not is_valid_type_annotation(self.payload_type):
            raise ValueError(f"EventMetadata.payload_type must be a valid type or alias, got {self.payload_type!r}")
        if not isinstance(self.ordering, EventOrdering):
            raise ValueError(f"EventMetadata.ordering must be EventOrdering, got {self.ordering!r}")
        require_pure_str(self.description, "EventMetadata.description")


def hop_conflicts(existing: ScopedHop, cand_scope: str, cand_id: EventId) -> bool:
    """Return True when two workspace-scoped event hops collide (empty scope acts as cross-workspace wildcard)."""
    ex_scope, ex_id = existing
    if ex_id != cand_id:
        return False
    return not ex_scope or not cand_scope or ex_scope == cand_scope


def _merge_wildcard_hop(merged_hops: list[ScopedHop], h_eid: EventId) -> None:
    seen_wildcard = False
    filtered: list[ScopedHop] = []
    for ex_scope, ex_eid in merged_hops:
        if ex_eid != h_eid:
            filtered.append((ex_scope, ex_eid))
        elif not seen_wildcard:
            seen_wildcard = True
            filtered.append(("", h_eid))
    if not seen_wildcard:
        filtered.append(("", h_eid))
    merged_hops[:] = filtered


def _merge_single_scoped_hop(merged_hops: list[ScopedHop], hop: ScopedHop) -> None:
    h_scope, h_eid = hop
    if not h_scope:
        _merge_wildcard_hop(merged_hops, h_eid)
        return
    for ex_scope, ex_eid in merged_hops:
        if ex_eid == h_eid and (not ex_scope or ex_scope == h_scope):
            return
    merged_hops.append(hop)


@dataclass(frozen=True, slots=True)
class CausalLineage:
    """Immutable deduplicated O(V) ancestor set of workspace-scoped EventIds with zero path truncation."""

    chain: tuple[EventId, ...] = ()
    scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        c_tup = require_typed_tuple(self.chain, EventId, "CausalLineage.chain")
        s_tup = require_typed_tuple(self.scopes, str, "CausalLineage.scopes")
        if len(s_tup) not in (0, len(c_tup)):
            raise ValueError("CausalLineage.scopes must be empty or match CausalLineage.chain length.")
        eff_s = s_tup if s_tup else tuple("" for _ in c_tup)
        seen_hops: list[ScopedHop] = []
        for sc, eid in zip(eff_s, c_tup):
            if any(hop_conflicts(prev, sc, eid) for prev in seen_hops):
                raise ValueError(f"CausalLineage contains conflicting duplicate hop {(sc, eid)!r}")
            seen_hops.append((sc, eid))
        object.__setattr__(self, "chain", c_tup)
        object.__setattr__(self, "scopes", eff_s)

    def scoped_hops(self) -> tuple[ScopedHop, ...]:
        return tuple(zip(self.scopes, self.chain))

    def advance(
        self,
        next_event_id: EventId,
        *,
        source_task: Optional[str] = None,
        workspace_scope: str = "",
    ) -> CausalLineage:
        if not isinstance(next_event_id, EventId):
            raise ValueError(f"next_event_id must be EventId, got {next_event_id!r}")
        require_pure_str(workspace_scope, "workspace_scope")
        if source_task is not None:
            require_pure_str(source_task, "source_task")
        cur_hops = self.scoped_hops()
        if any(hop_conflicts(h, workspace_scope, next_event_id) for h in cur_hops):
            cycle_str = " -> ".join([*(str(e) for e in self.chain), str(next_event_id)])
            raise EventCycleError(
                f"Event causal cycle detected: {cycle_str}",
                source_task=source_task,
            )
        return CausalLineage(
            chain=(*self.chain, next_event_id),
            scopes=(*(s for s, _ in cur_hops), workspace_scope),
        )

    @staticmethod
    def merge(lineages: Sequence[CausalLineage]) -> CausalLineage:
        lin_tup = require_typed_tuple(lineages, CausalLineage, "CausalLineage.merge lineages")
        merged_hops: list[ScopedHop] = []
        for lin in lin_tup:
            for hop in lin.scoped_hops():
                _merge_single_scoped_hop(merged_hops, hop)
        return CausalLineage(
            chain=tuple(eid for _s, eid in merged_hops),
            scopes=tuple(s for s, _eid in merged_hops),
        )


@dataclass(frozen=True, slots=True)
class RawEventRecord:
    """Validated serialized event record ready to commit to a Turn's staging queue."""

    event_id: EventId
    emitter_task: TaskId
    raw_payload: JsonObject
    ordering: EventOrdering
    lineage: CausalLineage = field(default_factory=CausalLineage)

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId) or not isinstance(self.emitter_task, TaskId):
            raise ValueError("RawEventRecord requires EventId and TaskId.")
        if not isinstance(self.ordering, EventOrdering) or not isinstance(self.lineage, CausalLineage):
            raise ValueError("RawEventRecord requires EventOrdering and CausalLineage.")
        object.__setattr__(
            self,
            "raw_payload",
            clone_strict_json_object(self.raw_payload, label="RawEventRecord.raw_payload"),
        )


@dataclass(frozen=True, slots=True)
class EventBatchEnvelope:
    """Pure-data batch envelope yielded by DoubleBufferedEventQueue.freeze_and_swap."""

    event_id: EventId
    ordering: EventOrdering
    payloads: tuple[JsonObject, ...]
    merged_lineage: CausalLineage
    record_lineages: tuple[CausalLineage, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, EventId) or not isinstance(self.ordering, EventOrdering):
            raise ValueError("EventBatchEnvelope requires EventId and EventOrdering.")
        if not isinstance(self.merged_lineage, CausalLineage):
            raise ValueError("EventBatchEnvelope.merged_lineage must be CausalLineage.")
        if isinstance(self.payloads, (str, bytes)) or not isinstance(self.payloads, Sequence):
            raise ValueError("EventBatchEnvelope.payloads must be a non-string Sequence.")
        if isinstance(self.record_lineages, (str, bytes)) or not isinstance(self.record_lineages, Sequence):
            raise ValueError("EventBatchEnvelope.record_lineages must be a non-string Sequence.")
        p_tup = tuple(
            clone_strict_json_object(p, label="EventBatchEnvelope.payloads") for p in self.payloads
        )
        l_tup = tuple(self.record_lineages)
        if any(not isinstance(lin, CausalLineage) for lin in l_tup):
            raise ValueError("EventBatchEnvelope.record_lineages elements must be CausalLineage.")
        if l_tup and len(l_tup) != len(p_tup):
            raise ValueError("EventBatchEnvelope.record_lineages length must match payloads.")
        object.__setattr__(self, "payloads", p_tup)
        object.__setattr__(self, "record_lineages", l_tup)

    def filter_for_subscription(
        self,
        payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]],
    ) -> tuple[tuple[JsonObject, ...], CausalLineage]:
        """Filter payloads and merge causal lineage strictly over records matching payload_filter."""
        norm_filter = normalize_payload_filter(payload_filter)
        if not norm_filter:
            return (self.payloads, self.merged_lineage)
        eff_lineages = self.record_lineages or (self.merged_lineage,) * len(self.payloads)
        matched = [
            (raw, lin)
            for raw, lin in zip(self.payloads, eff_lineages)
            if _payload_matches_filter(raw, norm_filter)
        ]
        if not matched:
            return ((), CausalLineage())
        return (
            tuple(raw for raw, _lin in matched),
            CausalLineage.merge([lin for _raw, lin in matched]),
        )


class BoundEventSubscription(Protocol, Generic[TIn_co]):
    """Variance-safe protocol allowing a single TaskMetadata[TIn, TOut] to subscribe to heterogeneous event payloads."""

    @property
    def event_id(self) -> EventId: ...

    @property
    def payload_filter(self) -> Optional[Mapping[str, tuple[JsonPrimitive, ...]]]: ...

    def decode_and_map(self, raw_payloads: Sequence[JsonObject]) -> Optional[TIn_co]: ...


@dataclass(frozen=True, slots=True)
class EventSubscriptionSpec(Generic[TPayload, TIn]):
    """Declarative event subscription binding either EventMetadata[TPayload] directly or an EventId + typed mapper."""

    event: EventMetadata[TPayload] | EventId
    batch_mapper: Callable[[Sequence[TPayload]], Optional[TIn]]
    payload_filter: Optional[Mapping[str, tuple[JsonPrimitive, ...]]] = None
    payload_type: Optional[type[TPayload]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.event, (EventMetadata, EventId)):
            raise ValueError(f"EventSubscriptionSpec.event must be EventMetadata or EventId, got {self.event!r}")
        if not callable(self.batch_mapper):
            raise ValueError("EventSubscriptionSpec.batch_mapper must be callable.")
        if self.payload_type is not None and not is_valid_type_annotation(self.payload_type):
            raise ValueError(f"EventSubscriptionSpec.payload_type must be a valid type or alias, got {self.payload_type!r}")
        object.__setattr__(self, "payload_filter", normalize_payload_filter(self.payload_filter))
        if not isinstance(self.event, EventMetadata) and self.payload_type is None:
            infer_sequence_element_dataclass(self.batch_mapper, strict_unresolved=False)

    @property
    def event_id(self) -> EventId:
        return self.event.event_id if isinstance(self.event, EventMetadata) else self.event

    def _effective_payload_form(self, *, strict_unresolved: bool) -> Optional[object]:
        if isinstance(self.event, EventMetadata):
            return self.event.payload_type
        if self.payload_type is not None:
            return self.payload_type
        _, inf_tp = infer_sequence_element_dataclass(self.batch_mapper, strict_unresolved=strict_unresolved)
        return inf_tp

    def decode_and_map(self, raw_payloads: Sequence[JsonObject]) -> Optional[TIn]:
        if self.payload_filter:
            raw_payloads = [item for item in raw_payloads if _payload_matches_filter(item, self.payload_filter)]
            if not raw_payloads:
                return None
        form = self._effective_payload_form(strict_unresolved=True)
        if form is not None:
            decoded_batch = tuple(DataclassCodec.decode(form, item) for item in raw_payloads)
            return self.batch_mapper(decoded_batch)
        raw_cast: Sequence[TPayload] = tuple(clone_strict_json_object(item) for item in raw_payloads)
        return self.batch_mapper(raw_cast)


def _scalar_matches_allowed(val: JsonValue, allowed_values: Sequence[JsonPrimitive]) -> bool:
    if isinstance(val, Enum):
        return False
    for allowed in allowed_values:
        if isinstance(val, bool) != isinstance(allowed, bool) or isinstance(val, float) != isinstance(allowed, float):
            continue
        if val == allowed:
            return True
    return False


def _payload_matches_filter(
    raw: JsonObject,
    payload_filter: Mapping[str, tuple[JsonPrimitive, ...]],
) -> bool:
    for field_key, allowed_values in payload_filter.items():
        if isinstance(allowed_values, (str, bytes, bytearray)) or not isinstance(allowed_values, Sequence):
            raise ValueError(f"payload_filter[{field_key!r}] must be a non-string Sequence.")
        if field_key not in raw:
            return False
        val = raw[field_key]
        if isinstance(val, (list, tuple)):
            if not any(_scalar_matches_allowed(item, allowed_values) for item in val):
                return False
        elif not _scalar_matches_allowed(val, allowed_values):
            return False
    return True


class TaskLocalOutbox:
    """Per-step outbox branching each emission off immutable base_lineage (supports sibling multi-emit)."""

    def __init__(
        self,
        emitter_task: TaskId,
        base_lineage: CausalLineage,
        *,
        workspace_scope: str = "",
    ) -> None:
        if not isinstance(emitter_task, TaskId) or not isinstance(base_lineage, CausalLineage):
            raise ValueError("TaskLocalOutbox requires TaskId and CausalLineage.")
        require_pure_str(workspace_scope, "workspace_scope")
        self._emitter_task = emitter_task
        self._base_lineage = base_lineage
        self._ws_scope = workspace_scope
        self._staged: list[RawEventRecord] = []
        self._lock = threading.Lock()

    @property
    def base_lineage(self) -> CausalLineage:
        return self._base_lineage

    def compute_immediate_lineage(self, event_id: EventId) -> CausalLineage:
        return self._base_lineage.advance(
            event_id,
            source_task=str(self._emitter_task),
            workspace_scope=self._ws_scope,
        )

    def stage(
        self,
        event_id: EventId,
        raw_payload: JsonObject,
        ordering: EventOrdering = EventOrdering.UNORDERED,
    ) -> RawEventRecord:
        branched_lineage = self._base_lineage.advance(
            event_id,
            source_task=str(self._emitter_task),
            workspace_scope=self._ws_scope,
        )
        record = RawEventRecord(
            event_id=event_id,
            emitter_task=self._emitter_task,
            raw_payload=raw_payload,
            ordering=ordering,
            lineage=branched_lineage,
        )
        with self._lock:
            self._staged.append(record)
        return record

    def discard(self) -> None:
        with self._lock:
            self._staged.clear()

    def drain_committed(self) -> tuple[RawEventRecord, ...]:
        with self._lock:
            committed = tuple(self._staged)
            self._staged.clear()
            return committed


class DoubleBufferedEventQueue:
    """Pure thread-safe double-buffered queue performing atomic freeze_and_swap and UNORDERED folding."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._staging: list[RawEventRecord] = []

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return bool(self._staging)

    def append_committed(self, records: Sequence[RawEventRecord]) -> None:
        tup = require_typed_tuple(records, RawEventRecord, "DoubleBufferedEventQueue.append_committed")
        if not tup:
            return
        with self._lock:
            self._staging.extend(tup)

    def clear(self) -> None:
        with self._lock:
            self._staging.clear()

    def freeze_and_swap(self) -> tuple[EventBatchEnvelope, ...]:
        with self._lock:
            if not self._staging:
                return ()
            frozen = self._staging
            self._staging = []

        envelopes: list[EventBatchEnvelope] = []
        unordered_index_by_id: dict[EventId, int] = {}
        unordered_groups: dict[EventId, list[RawEventRecord]] = {}

        for rec in frozen:
            if rec.ordering == EventOrdering.ORDERED:
                envelopes.append(
                    EventBatchEnvelope(
                        event_id=rec.event_id,
                        ordering=EventOrdering.ORDERED,
                        payloads=(rec.raw_payload,),
                        merged_lineage=rec.lineage,
                        record_lineages=(rec.lineage,),
                    )
                )
            elif rec.event_id not in unordered_groups:
                unordered_index_by_id[rec.event_id] = len(envelopes)
                unordered_groups[rec.event_id] = [rec]
                envelopes.append(
                    EventBatchEnvelope(
                        event_id=rec.event_id,
                        ordering=EventOrdering.UNORDERED,
                        payloads=(),
                        merged_lineage=CausalLineage(),
                    )
                )
            else:
                unordered_groups[rec.event_id].append(rec)

        for eid, group in unordered_groups.items():
            slot = unordered_index_by_id[eid]
            rec_lins = tuple(r.lineage for r in group)
            envelopes[slot] = EventBatchEnvelope(
                event_id=eid,
                ordering=EventOrdering.UNORDERED,
                payloads=tuple(r.raw_payload for r in group),
                merged_lineage=CausalLineage.merge(rec_lins),
                record_lineages=rec_lins,
            )
        return tuple(envelopes)
