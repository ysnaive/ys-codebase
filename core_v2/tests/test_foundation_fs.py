"""Domain tests for core.foundation, core.filesystem.fs, and core.execution.{event,lifecycle,rpc}."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Annotated, Callable, Generic, Mapping, Optional, Sequence, TypeVar, Union

from core.execution.event import (
    CausalLineage,
    DoubleBufferedEventQueue,
    EventMetadata,
    EventOrdering,
    RawEventRecord,
    TaskLocalOutbox,
    hop_conflicts,
)
from core.execution.lifecycle import (
    ColdTurnRunner,
    ContainerState,
    LifoResourceStack,
    StepExecutionResult,
    TurnEngine,
    TurnExecutionReport,
    TurnKind,
    TurnScope,
    WorkerContainerLifecycle,
)
from core.execution.rpc import (
    FrameKind,
    InboundCallHandler,
    MAX_FRAME_BYTES,
    MultiplexedChannel,
    RpcServerListener,
    accept_worker_handshake,
    bind_loopback_ephemeral,
    connect_and_handshake,
)
from core.execution.runtime import WORKER_AUTH_ENV_KEY, sanitize_caller_env
from core.filesystem.fs import (
    CrossProcessLockPaths,
    DEFAULT_WATCHER_IGNORED_DIRS,
    FileLock,
    IGNORED_FS_PREFIXES,
    PollingDirectoryWatcher,
    atomic_write_bytes,
    atomic_write_json,
    hash_nofollow_regular_sha256,
    is_contained_nonsymlink_path,
    is_symlink_or_reparse,
    read_json_dict,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.foundation import (
    CancellationToken,
    DataclassCodec,
    DeadlineGuard,
    EnvHash,
    ErrorCode,
    ErrorDetail,
    EventId,
    HOST_DIR_ENV_KEY,
    HostPath,
    INT64_MAX,
    INT64_MIN,
    IO_REPARSE_TAG_MOUNT_POINT,
    IO_REPARSE_TAG_SYMLINK,
    IS_WINDOWS,
    JsonObject,
    LocaleCatalog,
    LogLevel,
    LogRecord,
    LogRotator,
    MAX_LOCALE_INTERPOLATION_DEPTH,
    MAX_USER_JSON_DEPTH,
    ManagedProcessTree,
    ModuleId,
    PRIVATE_ENV_PREFIX,
    PUBLIC_ENV_ALLOWLIST,
    ROOT_DIR_ENV_KEY,
    SchemaExporter,
    SemVer4,
    SemanticUri,
    SessionTelemetryRecord,
    SessionTelemetryWriter,
    SignalWakeupGuard,
    SnapshotGen,
    SpaceId,
    SpacePath,
    StructuredLogger,
    TEST_SANDBOX_ENV_KEY,
    TREE_ID_ENV_KEY,
    TaskCancelledException,
    TaskId,
    VersionConstraint,
    YscbError,
    clone_strict_json_object,
    get_process_start_tag,
    infer_sequence_element_dataclass,
    is_disallowed_reparse_tag,
    is_process_alive,
    require_pure_bool,
    require_pure_int,
    safe_exception_summary,
    sanitize_utf8_text,
    spawn_detached,
    strict_parse_json_object,
)
from tests._harness import assert_raises_val_error, check, expect_yscb_code, log, wait_until


@dataclass(frozen=True, slots=True)
class _CodecLeafDto:
    count: int
    ratio: float
    flag: bool
    label: str = "def"


@dataclass(frozen=True, slots=True)
class _UnionLeftDto:
    tag: str
    score: int


@dataclass(frozen=True, slots=True)
class _UnionRightDto:
    tag: str
    note: str


@dataclass(frozen=True, slots=True)
class _CodecCompositeDto:
    title: str
    item: Optional[_CodecLeafDto]
    choice: Union[_UnionLeftDto, _UnionRightDto]
    extras: tuple[_CodecLeafDto, ...] = ()


@dataclass(frozen=True, slots=True)
class _Wave12VoBundleDto:
    version: SemVer4
    constraint: VersionConstraint
    uri: SemanticUri
    space_id: SpaceId
    space_path: SpacePath
    gen: SnapshotGen
    env_hash: EnvHash
    deps: Mapping[ModuleId, VersionConstraint] = field(default_factory=dict)
    space_gens: Mapping[SpaceId, SnapshotGen] = field(default_factory=dict)
    gen_paths: Mapping[SnapshotGen, SpacePath] = field(default_factory=dict)


class _SchemaMergeTag(Enum):
    MERGE = "merge"
    EXTEND = "extend"


@dataclass(frozen=True, slots=True)
class _SchemaFieldMeta:
    description: str = ""
    merge: Optional[_SchemaMergeTag] = None


@dataclass(frozen=True, slots=True)
class _SchemaTreeNodeDto:
    name: Annotated[str, "Node display name"]
    level: LogLevel = LogLevel.INFO
    uri: Optional[SemanticUri] = None
    gen: SnapshotGen = SnapshotGen(0)
    children: Annotated[
        tuple[_SchemaTreeNodeDto, ...],
        _SchemaFieldMeta(description="Child tree nodes", merge=_SchemaMergeTag.EXTEND),
    ] = ()
    next_peer: Optional[_SchemaTreeNodeDto] = None


_SchemaItemT = TypeVar("_SchemaItemT")


@dataclass(frozen=True, slots=True)
class _SchemaGenBoxDto(Generic[_SchemaItemT]):
    payload: _SchemaItemT


@dataclass(frozen=True, slots=True)
class _SchemaRootEnvelopeDto:
    module_id: ModuleId
    version: SemVer4
    env_hash: EnvHash
    space: SpaceId
    root_node: _SchemaTreeNodeDto
    optional_leaf: Optional[_CodecLeafDto] = None


class _MemoryStructuredLogger:
    def __init__(self, name: str, rotator: LogRotator) -> None:
        self.records: list[LogRecord] = []
        self._name = name
        self._rotator = rotator

    def log(self, level: LogLevel, message: str, *, fields: Optional[JsonObject] = None) -> None:
        rec = LogRecord(
            ts_utc="2026-11-22T00:00:00Z",
            level=level,
            logger_name=self._name,
            message=message,
            fields=fields if fields is not None else {},
        )
        self.records.append(rec)
        self._rotator.append_jsonl(DataclassCodec.encode_object(rec))

    def debug(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.DEBUG, message, fields=fields)

    def info(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.INFO, message, fields=fields)

    def warning(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.WARNING, message, fields=fields)

    def error(self, message: str, *, fields: Optional[JsonObject] = None) -> None:
        self.log(LogLevel.ERROR, message, fields=fields)


class _ToxicStrError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("toxic __str__ failure")


def _expect_codec_or_val_err(fn: Callable[[], object]) -> None:
    try:
        fn()
    except (YscbError, ValueError) as exc:
        if isinstance(exc, YscbError):
            check(exc.detail.code == ErrorCode.CODEC_VALIDATION_FAILED, f"Unexpected YscbError code: {exc.detail.code}")
        return
    raise AssertionError("Expected YscbError(CODEC_VALIDATION_FAILED) or ValueError")


def _sample_mapper(items: Sequence[_CodecLeafDto]) -> Optional[_CodecLeafDto]:
    return items[0] if items else None


def _unresolved_mapper_base(items: object) -> None:
    _ = items


def _build_nested_dict(depth: int) -> dict[str, object]:
    cur: dict[str, object] = {"leaf": 1}
    for _ in range(depth):
        cur = {"n": cur}
    return cur


def _verify_codec_contracts() -> None:
    sample = _CodecCompositeDto(
        title="alpha",
        item=_CodecLeafDto(count=42, ratio=1.5, flag=True, label="x"),
        choice=_UnionLeftDto(tag="left", score=99),
        extras=(_CodecLeafDto(count=-7, ratio=0.25, flag=False),),
    )
    raw = DataclassCodec.encode(sample)
    typed_raw = DataclassCodec.encode_typed(_CodecCompositeDto, sample)
    env = DataclassCodec.encode_envelope(sample)
    check(raw == typed_raw, "encode and encode_typed mismatch")
    check(DataclassCodec.decode_envelope(_CodecCompositeDto, env) == sample, "decode_envelope round-trip mismatch")
    check(DataclassCodec.decode(_CodecCompositeDto, raw) == sample, "decode round-trip mismatch")

    right_raw = DataclassCodec.encode(
        _CodecCompositeDto(
            title="beta",
            item=None,
            choice=_UnionRightDto(tag="right", note="ok"),
        )
    )
    decoded_right = DataclassCodec.decode(_CodecCompositeDto, right_raw)
    check(isinstance(decoded_right, _CodecCompositeDto), "Expected _CodecCompositeDto")
    check(decoded_right.item is None and isinstance(decoded_right.choice, _UnionRightDto), "Optional/Union decode mismatch")

    _expect_codec_or_val_err(
        lambda: DataclassCodec.decode(
            _CodecLeafDto, {"count": True, "ratio": 1.0, "flag": False, "label": "bad_bool"}
        )
    )
    _expect_codec_or_val_err(lambda: require_pure_int(True, "flag_as_int"))
    _expect_codec_or_val_err(lambda: require_pure_bool(1, "int_as_bool"))
    for bad_num in (math.nan, math.inf, -math.inf):
        _expect_codec_or_val_err(
            lambda v=bad_num: DataclassCodec.encode(_CodecLeafDto(count=1, ratio=v, flag=False))
        )
    _expect_codec_or_val_err(lambda: strict_parse_json_object('{"ratio": NaN}'))

    min_ok = DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MIN, "ratio": 0.0, "flag": False})
    max_ok = DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MAX, "ratio": 0.0, "flag": True})
    check(min_ok == _CodecLeafDto(count=INT64_MIN, ratio=0.0, flag=False), "INT64_MIN failed")
    check(max_ok == _CodecLeafDto(count=INT64_MAX, ratio=0.0, flag=True), "INT64_MAX failed")
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MAX + 1, "ratio": 0.0, "flag": True}))
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(_CodecLeafDto, {"count": INT64_MIN - 1, "ratio": 0.0, "flag": False}))

    _expect_codec_or_val_err(lambda: DataclassCodec.encode(_CodecLeafDto(count=1, ratio=0.0, flag=True, label="\ud800")))
    _expect_codec_or_val_err(lambda: strict_parse_json_object('{"bad": "\\ud800"}'))
    check("\ud800" not in sanitize_utf8_text("pre\ud800post"), "sanitize_utf8_text kept lone surrogate")

    ok_depth = _build_nested_dict(MAX_USER_JSON_DEPTH - 1)
    too_deep = _build_nested_dict(MAX_USER_JSON_DEPTH)
    check(clone_strict_json_object(ok_depth) == ok_depth, "Exact max JSON depth failed")
    _expect_codec_or_val_err(lambda: clone_strict_json_object(too_deep))

    h_first = DataclassCodec.canonical_hash({"b": [1, 2], "a": {"y": True, "x": 1}})
    h_second = DataclassCodec.canonical_hash({"a": {"x": 1, "y": True}, "b": [1, 2]})
    h_bool_diff = DataclassCodec.canonical_hash({"a": {"x": True, "y": True}, "b": [1, 2]})
    check(h_first == h_second and h_first != h_bool_diff, "canonical_hash invariant failed")

    DataclassCodec.evict_module_prefix(__name__)
    check(DataclassCodec.decode(_CodecCompositeDto, raw) == sample, "decode after evict_module_prefix failed")

    ok_res, elem_cls = infer_sequence_element_dataclass(_sample_mapper, strict_unresolved=True)
    check(ok_res and elem_cls is _CodecLeafDto, f"Expected _CodecLeafDto inference, got {elem_cls!r}")
    orig_ann = _unresolved_mapper_base.__annotations__.get("items", "object")
    _unresolved_mapper_base.__annotations__["items"] = "Sequence[MissingRefDto]"
    try:
        ok_unres, unres_cls = infer_sequence_element_dataclass(_unresolved_mapper_base, strict_unresolved=False)
        check((not ok_unres) and unres_cls is None, "Unresolved lenient inference should return (False, None)")
        expect_yscb_code(
            lambda: infer_sequence_element_dataclass(_unresolved_mapper_base, strict_unresolved=True),
            ErrorCode.CODEC_VALIDATION_FAILED,
        )
    finally:
        _unresolved_mapper_base.__annotations__["items"] = orig_ann


def _verify_wave12_value_objects_and_env() -> None:
    check(PRIVATE_ENV_PREFIX == "_YSCB_", f"Unexpected PRIVATE_ENV_PREFIX: {PRIVATE_ENV_PREFIX!r}")
    check(WORKER_AUTH_ENV_KEY.startswith(PRIVATE_ENV_PREFIX), "WORKER_AUTH_ENV_KEY must carry PRIVATE_ENV_PREFIX")
    for priv_key in (WORKER_AUTH_ENV_KEY, TREE_ID_ENV_KEY, TEST_SANDBOX_ENV_KEY, HOST_DIR_ENV_KEY, ROOT_DIR_ENV_KEY):
        check(priv_key.startswith(PRIVATE_ENV_PREFIX), f"Private env key missing prefix: {priv_key!r}")
    expected_allowlist = frozenset(
        {
            "YSCB_NO_DAEMON",
            "YSCB_FORCE_DAEMON",
            "YSCB_LOG_LEVEL",
            "YSCB_NO_UPDATE_CHECK",
            "YSCB_LOCALE",
            "YSCB_OFFLINE",
            "YSCB_CALLER_MODE",
            "YSCB_CI_APPROVE_GATED",
        }
    )
    check(PUBLIC_ENV_ALLOWLIST == expected_allowlist, f"PUBLIC_ENV_ALLOWLIST mismatch: {PUBLIC_ENV_ALLOWLIST}")
    sanitized = sanitize_caller_env(
        {
            WORKER_AUTH_ENV_KEY: "forged_auth",
            WORKER_AUTH_ENV_KEY.lower(): "forged_lower",
            TREE_ID_ENV_KEY: "forged_tree",
            TEST_SANDBOX_ENV_KEY: "1",
            f"{PRIVATE_ENV_PREFIX}INJECTED": "blocked",
            "YSCB_LOCALE": "en,zh",
            "YSCB_OFFLINE": "1",
            "UNLISTED_RANDOM_VAR": "dropped",
        }
    )
    check(sanitized == {"YSCB_LOCALE": "en,zh", "YSCB_OFFLINE": "1"}, f"sanitize_caller_env leak: {sanitized}")

    wave12_codes = (
        ErrorCode.URI_UNDEFINED,
        ErrorCode.URI_CYCLE,
        ErrorCode.ACCESS_DENIED,
        ErrorCode.READONLY_VIOLATION,
        ErrorCode.SPACE_CYCLE,
        ErrorCode.SPACE_NOT_FOUND,
        ErrorCode.STORAGE_CORRUPT,
        ErrorCode.SCHEMA_MIGRATION_ERROR,
        ErrorCode.CONFIG_INVALID,
        ErrorCode.CONTRIBUTES_INVALID,
        ErrorCode.DEPENDENCY_CONFLICT,
        ErrorCode.PACKAGE_INTEGRITY_ERROR,
        ErrorCode.ENV_BUILD_FAILED,
    )
    for err_code in wave12_codes:
        det = ErrorDetail(err_code, "diagnostic", remediation="fix")
        check(DataclassCodec.decode(ErrorDetail, DataclassCodec.encode(det)) == det, f"ErrorCode codec failed: {err_code}")

    ver_norm = SemVer4.parse("1.2.3")
    check(ver_norm == SemVer4(1, 2, 3, 0) and str(ver_norm) == "1.2.3.0", f"3-segment SemVer4 failed: {ver_norm!r}")
    check(ver_norm.triple() == (1, 2, 3), f"SemVer4.triple mismatch: {ver_norm.triple()!r}")
    ver_rev = SemVer4.parse("1.2.3.7")
    ver_build = SemVer4.parse("1.2.3.build")
    ver_pre = SemVer4.parse("1.2.3-beta.2")
    ver_pre_ten = SemVer4.parse("1.2.3-beta.10")
    ver_pre_rev = SemVer4.parse("1.2.3.4-alpha.1")
    check(ver_build.is_build and ver_build.revision == 0 and str(ver_build) == "1.2.3.build", "SemVer4 .build mismatch")
    check(str(ver_pre) == "1.2.3-beta.2" and str(ver_pre_rev) == "1.2.3.4-alpha.1", "SemVer4 prerelease __str__ mismatch")
    check(SemVer4.parse("1.10.0") > SemVer4.parse("1.9.0"), "Numeric minor ordering failed")
    check(ver_rev > ver_norm and ver_norm > ver_build and ver_norm > ver_pre, "SemVer4 precedence invariant failed")
    check(ver_pre_ten > ver_pre and ver_pre <= ver_pre_ten and ver_rev >= ver_norm, "SemVer4 comparison operators failed")
    check(ver_norm.compare_precedence(SemVer4(1, 2, 3, 0)) == 0, "SemVer4 equal precedence failed")
    for bad_ver in ("", "1.2", "1.2.3.4.5", "01.2.3", "1.2.3.unknown", "1.2.3.build-rc.1", "1.2.3-beta..1", "1.2.3-01", "1.2.3-rc.02"):
        assert_raises_val_error(lambda raw_v=bad_ver: SemVer4.parse(raw_v))
    assert_raises_val_error(lambda: SemVer4(1, 2, 3, revision=1, is_build=True))
    assert_raises_val_error(lambda: SemVer4(True, 0, 0))

    eq_three = VersionConstraint.parse("==1.2.3")
    ne_three = VersionConstraint.parse("!=1.2.3")
    gt_three = VersionConstraint.parse(">1.2.3")
    le_three = VersionConstraint.parse("<=1.2.3")
    eq_four = VersionConstraint.parse("==1.2.3.0")
    check(eq_three.satisfies(ver_norm) and eq_three.satisfies(ver_rev), "==1.2.3 must accept numeric revisions")
    check((not ne_three.satisfies(ver_norm)) and (not ne_three.satisfies(ver_rev)), "!=1.2.3 must reject 1.2.3.x family")
    check(ne_three.satisfies(ver_build) and ne_three.satisfies(ver_pre), "!=1.2.3 must accept build/prerelease")
    check((not gt_three.satisfies(ver_rev)) and le_three.satisfies(ver_rev), "1.2.3.7 must satisfy <=1.2.3 and not >1.2.3")
    check(gt_three.satisfies(SemVer4.parse("1.2.4-alpha.1")) and (not le_three.satisfies(SemVer4.parse("1.2.4-alpha.1"))), "1.2.4-alpha.1 must exceed <=1.2.3")
    check((not eq_three.satisfies(ver_build)) and (not eq_three.satisfies(ver_pre)), "==1.2.3 must reject build/pre")
    check(eq_four.satisfies(ver_norm) and (not eq_four.satisfies(ver_rev)), "==1.2.3.0 must require exact revision")
    caret = VersionConstraint.compatible_same_major(SemVer4.parse("1.2.3"))
    tilde = VersionConstraint.parse("~=1.2.3")
    for maj_lock in (caret, tilde):
        check(maj_lock.satisfies(SemVer4.parse("1.2.3.0")), "Same-major floor failed")
        check(maj_lock.satisfies(SemVer4.parse("1.99.0.5")), "Same-major upgrade failed")
        check(not maj_lock.satisfies(SemVer4.parse("1.2.2.9")), "Same-major lower bound failed")
        check(not maj_lock.satisfies(SemVer4.parse("2.0.0.0")), "Same-major ceiling failed")
        check(not maj_lock.satisfies(SemVer4.parse("2.0.0-alpha.1")), "Same-major next-major prerelease leaked")
    conj = VersionConstraint.parse(">=1.2.0, <2.0.0, !=1.5.0.0")
    check(conj.satisfies(SemVer4.parse("1.5.0.1")) and (not conj.satisfies(SemVer4.parse("1.5.0.0"))), "Conjunction failed")
    check(VersionConstraint.parse("*").satisfies(ver_build), "Wildcard '*' failed")
    check(VersionConstraint.parse("1.2.*").satisfies(ver_rev) and (not VersionConstraint.parse("1.2.*").satisfies(SemVer4.parse("1.3.0"))), "Prefix wildcard failed")
    check(VersionConstraint.parse("build").satisfies(ver_build) and (not VersionConstraint.parse("build").satisfies(ver_norm)), "build constraint failed")
    check(not VersionConstraint.parse("<2.0.0").satisfies(SemVer4.parse("2.0.0-alpha.1")), "<2.0.0 must reject 2.0.0-alpha.1")
    check(not VersionConstraint.parse("<2.0.0.0").satisfies(SemVer4.parse("2.0.0.build")), "<2.0.0.0 must reject 2.0.0.build")
    check(VersionConstraint.compatible_same_major(ver_build).satisfies(ver_build), "compatible_same_major(.build) must satisfy self")
    for bad_cons in ("", "   ", ">=1.0.0,", ",<2.0.0", ">>1.0.0", "^1.2.*"):
        assert_raises_val_error(lambda raw_c=bad_cons: VersionConstraint.parse(raw_c))

    uri_mod = SemanticUri.parse("storage.local://@\\state//main.db/")
    check(str(uri_mod) == "storage.local://@/state/main.db", f"SemanticUri normalization failed: {uri_mod}")
    check(uri_mod.uses_module_placeholder and uri_mod.name == "main.db" and uri_mod.suffix == ".db", "SemanticUri props failed")
    bound_uri = uri_mod.bind_module(ModuleId("knowledge-db"))
    check(str(bound_uri) == "storage.local://knowledge-db/state/main.db" and (not bound_uri.uses_module_placeholder), "bind_module failed")
    root_uri = SemanticUri.parse("project://")
    check(root_uri.parent is None and root_uri.name == "" and root_uri.suffix == "", "Root SemanticUri props failed")
    joined_uri = (root_uri / "src").join("core", "init.py")
    check(str(joined_uri) == "project://src/core/init.py", f"SemanticUri join/truediv failed: {joined_uri}")
    check(joined_uri.parent == SemanticUri.parse("project://src/core"), "SemanticUri.parent mismatch")
    check(SemanticUri.parse("project://src").parent == root_uri, "Single-segment SemanticUri.parent mismatch")
    for bad_uri in (
        "",
        "relative/no_scheme",
        "://missing_scheme",
        "1bad://path",
        "project://../escape",
        "project://a/../b",
        "project://./dot",
        "project://CON/file.txt",
        "project://nul.json",
        "project://bad:stream",
        "project://sub/@/illegal_at",
        "project://trail ",
    ):
        assert_raises_val_error(lambda raw_u=bad_uri: SemanticUri.parse(raw_u))
    assert_raises_val_error(lambda: joined_uri.join("..", "x"))
    assert_raises_val_error(lambda: joined_uri.join("@"))

    named_sp = SpaceId.parse("core/gitignore")
    synth_sp = SpaceId.parse("/gitignore")
    check((not named_sp.is_synthetic) and named_sp.owner == "core" and str(named_sp) == "core/gitignore", "Named SpaceId failed")
    check(synth_sp.is_synthetic and synth_sp.owner == "" and str(synth_sp) == "/gitignore", "Synthetic SpaceId failed")
    for bad_sp in ("", "/", "core/", "bare_name", "a/b/c", "../gitignore", "core/BAD_CAPS"):
        assert_raises_val_error(lambda raw_s=bad_sp: SpaceId.parse(raw_s))

    sp_path = SpacePath.parse("src\\foundation/primitives.py")
    check(str(sp_path) == "src/foundation/primitives.py", f"SpacePath normalization failed: {sp_path}")
    check(str(SpacePath.parse(".gitignore")) == ".gitignore", "Dotfile SpacePath failed")
    for bad_rel in ("", "/leading/slash", "trailing/slash/", "a//b", "../escape", "a/../b", "CON.py", "file:ads"):
        assert_raises_val_error(lambda raw_p=bad_rel: SpacePath.parse(raw_p))

    gen_zero = SnapshotGen(0)
    gen_one = gen_zero.next()
    check(gen_one == SnapshotGen(1) and gen_zero < gen_one and gen_zero <= gen_one and gen_one > gen_zero and gen_one >= gen_zero, "SnapshotGen ordering failed")
    assert_raises_val_error(lambda: SnapshotGen(-1))
    assert_raises_val_error(lambda: SnapshotGen(True))

    eh = EnvHash("0123456789abcdef0123456789abcdef")
    check(eh.short(16) == "0123456789abcdef" and str(eh) == "0123456789abcdef0123456789abcdef", "EnvHash failed")
    for bad_eh in ("", "0123456789abcde", "0123456789ABCDEF", "0123456789abcdefg", "a" * 65):
        assert_raises_val_error(lambda raw_h=bad_eh: EnvHash(raw_h))

    vo_bundle = _Wave12VoBundleDto(
        version=SemVer4.parse("2.1.0"),
        constraint=VersionConstraint.parse("^2.0.0"),
        uri=SemanticUri.parse("config://@/settings.json"),
        space_id=synth_sp,
        space_path=sp_path,
        gen=SnapshotGen(7),
        env_hash=eh,
        deps={ModuleId("core"): VersionConstraint.parse(">=2.0.0.0")},
        space_gens={named_sp: SnapshotGen(3), synth_sp: SnapshotGen(4)},
        gen_paths={SnapshotGen(3): SpacePath.parse("README.md")},
    )
    vo_wire = DataclassCodec.encode_object(vo_bundle, expected_type=_Wave12VoBundleDto)
    check(vo_wire["version"] == "2.1.0.0" and type(vo_wire["gen"]) is int and vo_wire["gen"] == 7, f"Unexpected VO wire format: {vo_wire}")
    vo_round = DataclassCodec.decode(_Wave12VoBundleDto, vo_wire)
    check(vo_round == vo_bundle, "Wave 1.2 VO bundle DataclassCodec round-trip mismatch")
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(SnapshotGen, True))
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(SnapshotGen, -1))
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(SnapshotGen, "7"))
    _expect_codec_or_val_err(lambda: DataclassCodec.decode(SemanticUri, "missing_scheme"))


def _verify_schema_exporter() -> None:
    schema = SchemaExporter.export(_SchemaRootEnvelopeDto, title="CustomRootContract")
    check(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"Missing Draft 2020-12 URI: {schema}")
    check(schema.get("title") == "CustomRootContract" and schema.get("type") == "object", "Root schema metadata mismatch")
    check(schema.get("additionalProperties") is False, "Root schema must set additionalProperties=False")
    props = schema.get("properties")
    defs = schema.get("$defs")
    check(isinstance(props, dict) and isinstance(defs, dict), "Schema properties/$defs must be dicts")
    if not isinstance(props, dict) or not isinstance(defs, dict):
        return
    check("_SchemaTreeNodeDto" in defs and "_CodecLeafDto" in defs, f"Expected nested $defs entries, got {list(defs.keys())}")
    opt_leaf_sc = props.get("optional_leaf")
    check(
        isinstance(opt_leaf_sc, dict)
        and opt_leaf_sc.get("anyOf") == [{"$ref": "#/$defs/_CodecLeafDto"}, {"type": "null"}],
        f"Optional dataclass schema mismatch: {opt_leaf_sc}",
    )
    node_def = defs["_SchemaTreeNodeDto"]
    check(isinstance(node_def, dict) and node_def.get("additionalProperties") is False, "Nested def additionalProperties must be False")
    if isinstance(node_def, dict):
        node_props = node_def.get("properties")
        check(isinstance(node_props, dict), "Node properties missing")
        if isinstance(node_props, dict):
            nm_sc = node_props.get("name")
            lvl_sc = node_props.get("level")
            ch_sc = node_props.get("children")
            peer_sc = node_props.get("next_peer")
            check(isinstance(nm_sc, dict) and nm_sc.get("description") == "Node display name", f"Annotated str description missing: {nm_sc}")
            check(
                isinstance(lvl_sc, dict) and lvl_sc.get("enum") == ["debug", "info", "warning", "error"],
                f"Enum schema mismatch: {lvl_sc}",
            )
            check(
                isinstance(ch_sc, dict)
                and ch_sc.get("description") == "Child tree nodes"
                and ch_sc.get("x-yscb-merge") == "extend"
                and ch_sc.get("items") == {"$ref": "#/$defs/_SchemaTreeNodeDto"},
                f"Recursive tuple Annotated schema mismatch: {ch_sc}",
            )
            check(
                isinstance(peer_sc, dict)
                and peer_sc.get("anyOf") == [{"$ref": "#/$defs/_SchemaTreeNodeDto"}, {"type": "null"}],
                f"Recursive Optional schema mismatch: {peer_sc}",
            )

    direct_rec_schema = SchemaExporter.export(_SchemaTreeNodeDto)
    rec_defs = direct_rec_schema.get("$defs")
    check(
        isinstance(rec_defs, dict) and "_SchemaTreeNodeDto" in rec_defs,
        f"Self-recursive root must populate $defs target: {direct_rec_schema}",
    )
    dict_meta_box_schema = SchemaExporter.export(_SchemaGenBoxDto[Annotated[str, {"description": "dict_meta_val"}]])
    check(dict_meta_box_schema.get("type") == "object", f"Dict metadata Annotated generic export failed: {dict_meta_box_schema}")


def _verify_observability_rotator_locale_telemetry(tmp_root: Path) -> None:
    obs_dir = HostPath(tmp_root / "ws_obs_wave12")
    obs_dir.path.mkdir(parents=True, exist_ok=True)

    jsonl_path = obs_dir.join("unicode_events.jsonl")
    stale_tmp = jsonl_path.path.parent / f".{jsonl_path.path.name}.rot_tmp_99999_1_abcdef012345"
    stale_tmp.write_text("stale_crash_temp", encoding="utf-8")
    old_epoch = time.time() - 120.0
    os.utime(stale_tmp, (old_epoch, old_epoch))
    fresh_tmp = jsonl_path.path.parent / f".{jsonl_path.path.name}.rot_tmp_99999_2_abcdef012345"
    fresh_tmp.write_text("fresh_inflight_temp", encoding="utf-8")
    own_tmp = jsonl_path.path.parent / f".{jsonl_path.path.name}.rot_tmp_{os.getpid()}_1_abcdef012345"
    own_tmp.write_text("own_pid_temp", encoding="utf-8")
    os.utime(own_tmp, (old_epoch, old_epoch))
    jsonl_path.path.write_bytes(b'{"corrupt_partial":')
    jsonl_rot = LogRotator(jsonl_path, max_bytes=140, keep_lines=3)
    try:
        check(not stale_tmp.exists(), "LogRotator failed to clean up aged 3-part crash rotation temp file")
        check(fresh_tmp.exists(), "LogRotator prematurely deleted fresh (<60s) 3-part rotation temp file")
        check(own_tmp.exists(), "LogRotator deleted own-PID 3-part rotation temp file")
        fresh_tmp.unlink()
        own_tmp.unlink()
        for seq_i in range(5):
            jsonl_rot.append_jsonl({"seq": seq_i, "text": f"alpha\u2028beta\u2029item_{seq_i}"})
        all_rows = jsonl_rot.read_jsonl()
        check(len(all_rows) == 3, f"Expected keep_lines=3 JSONL rows after rotation, got {len(all_rows)}: {all_rows}")
        check([row["seq"] for row in all_rows] == [2, 3, 4], f"Unexpected JSONL sequence tail: {all_rows}")
        check(all_rows[-1]["text"] == "alpha\u2028beta\u2029item_4", f"Unicode U+2028/U+2029 corrupted: {all_rows[-1]}")
        lim_rows = jsonl_rot.read_jsonl(limit=2)
        check([row["seq"] for row in lim_rows] == [3, 4], f"read_jsonl(limit=2) mismatch: {lim_rows}")
    finally:
        jsonl_rot.close()

    hist_path = obs_dir.join("rolling_text.log")
    hist_rot = LogRotator(hist_path, max_bytes=4096, max_lines=2, max_history_files=2)
    try:
        for idx in range(7):
            hist_rot.append_line(f"line\u2028entry_{idx}")
        check((hist_path.path.parent / f"{hist_path.path.name}.1").is_file(), "History .1 missing")
        check((hist_path.path.parent / f"{hist_path.path.name}.2").is_file(), "History .2 missing")
        check(not (hist_path.path.parent / f"{hist_path.path.name}.3").exists(), "History .3 exceeded max_history_files=2")
        tail_txt = hist_rot.read_tail_lines(limit=4)
        check(
            tail_txt == ("line\u2028entry_3", "line\u2028entry_4", "line\u2028entry_5", "line\u2028entry_6"),
            f"History read_tail_lines mismatch: {tail_txt}",
        )
    finally:
        hist_rot.close()

    struct_log_path = obs_dir.join("structured.jsonl")
    struct_rot = LogRotator(struct_log_path)
    logger: StructuredLogger = _MemoryStructuredLogger("core.test", struct_rot)
    logger.info("boot_ok", fields={"step": 1})
    logger.error("boom_err", fields={"fatal": False})
    struct_rows = struct_rot.read_jsonl()
    check(len(struct_rows) == 2 and struct_rows[0]["level"] == "info" and struct_rows[1]["level"] == "error", f"StructuredLogger rows mismatch: {struct_rows}")
    struct_rot.close()
    expect_yscb_code(lambda: struct_rot.append_line("after_close"), ErrorCode.TEARDOWN_ERROR)
    expect_yscb_code(lambda: struct_rot.append_jsonl({"after": True}), ErrorCode.TEARDOWN_ERROR)
    if not IS_WINDOWS:
        ext_victim = obs_dir.join("victim.txt").path
        ext_victim.write_text("do_not_overwrite\n", encoding="utf-8")
        sym_log = obs_dir.join("sym_attack.log")
        os.symlink(ext_victim, sym_log.path)
        sym_rot = LogRotator(sym_log)
        try:
            expect_yscb_code(lambda: sym_rot.append_line("injected"), ErrorCode.ACCESS_DENIED)
            check(ext_victim.read_text(encoding="utf-8") == "do_not_overwrite\n", "LogRotator followed symlink")
        finally:
            sym_rot.close()
            os.unlink(sym_log.path)
        anc_ext_dir = obs_dir.join("ext_anc_target").path
        anc_ext_dir.mkdir(parents=True, exist_ok=True)
        anc_base = obs_dir.join("anc_trap")
        deep_log = anc_base.join("nested/escape.log")
        anc_rot = LogRotator(deep_log)
        os.symlink(anc_ext_dir, anc_base.path)
        try:
            expect_yscb_code(lambda: anc_rot.append_line("escaped"), ErrorCode.ACCESS_DENIED)
            check(not (anc_ext_dir / "nested").exists(), "LogRotator traversed symlinked ancestor during mkdir")
        finally:
            anc_rot.close()
            os.unlink(anc_base.path)
        hist_sym = hist_path.path.parent / f"{hist_path.path.name}.1"
        hist_sym.unlink(missing_ok=True)
        os.symlink(ext_victim, hist_sym)
        hist_chk_rot = LogRotator(hist_path, max_bytes=4096, max_lines=2, max_history_files=2)
        try:
            expect_yscb_code(lambda: hist_chk_rot.read_tail_lines(limit=4), ErrorCode.ACCESS_DENIED)
        finally:
            hist_chk_rot.close()
            hist_sym.unlink(missing_ok=True)

    check(MAX_LOCALE_INTERPOLATION_DEPTH == 5, f"Unexpected MAX_LOCALE_INTERPOLATION_DEPTH: {MAX_LOCALE_INTERPOLATION_DEPTH}")
    mod_core = ModuleId("core")
    mod_alpha = ModuleId("alpha")
    mod_zeta = ModuleId("zeta")
    catalog = LocaleCatalog(
        {
            mod_core: {
                "nouns-agy": {"tool.view": "view_file"},
                "zh-TW": {
                    "msg.hint": "請使用 {tool.view} 檢視 {{literal}} {target}",
                    "tool.view": "檢視器",
                    "hop0": "{hop1}",
                    "hop1": "{hop2}",
                    "hop2": "{hop3}",
                    "hop3": "{hop4}",
                    "hop4": "{hop5}",
                    "hop5": "{hop6}",
                    "hop6": "too_deep",
                    "cyc.a": "A->{cyc.b}",
                    "cyc.b": "B->{cyc.a}",
                },
                "zh": {"only.zh": "中文保底"},
                "en": {"only.zh": "english_fallback", "tool.view": "viewer"},
            },
            mod_alpha: {
                "en": {"shared.key": "from_alpha"},
            },
            mod_zeta: {
                "en": {"shared.key": "from_zeta"},
            },
        },
        default_chain=("zh",),
    )
    rendered_agy = catalog.translate(
        "msg.hint",
        caller_module=mod_core,
        chain=("nouns-agy", "zh-TW", "en"),
        params={"target": "README {{raw}}"},
    )
    check(rendered_agy == "請使用 view_file 檢視 {literal} README {{raw}}", f"Locale interpolation/escape mismatch: {rendered_agy!r}")
    no_implicit_parent = catalog.translate("only.zh", caller_module=mod_core, chain=("zh-TW", "en"))
    check(no_implicit_parent == "english_fallback", f"LocaleCatalog must not split 'zh-TW' into 'zh': {no_implicit_parent!r}")
    check(catalog.translate("shared.key", caller_module=mod_zeta, chain=("en",)) == "from_zeta", "caller_module priority failed")
    check(catalog.translate("shared.key", chain=("en",)) == "from_alpha", "Alphabetical module fallback failed")
    check(catalog.translate("zeta:shared.key", caller_module=mod_alpha, chain=("en",)) == "from_zeta", "Explicit <module>: prefix failed")
    check(catalog.translate("hop0", caller_module=mod_core, chain=("zh-TW",)) == "{hop6}", "Depth 5 cap failed")
    check(catalog.translate("hop1", caller_module=mod_core, chain=("zh-TW",)) == "too_deep", "Exact depth 5 resolution failed")
    check(catalog.translate("cyc.a", caller_module=mod_core, chain=("zh-TW",)) == "A->B->{cyc.a}", "Cycle guard failed")

    telem_off_path = obs_dir.join("telem_disabled.jsonl")
    telem_sbx_path = obs_dir.join("telem_sandbox.jsonl")
    telem_on_path = obs_dir.join("telem_active.jsonl")
    sample_telem = SessionTelemetryRecord(
        ts_utc="2026-11-22T01:00:00Z",
        epoch_ms=1795309200000,
        task_id="core.status",
        args=("--json",),
        exit_code=0,
        duration_ms=12,
        executed_hot=True,
        caller_cwd=str(obs_dir),
    )
    writer_off = SessionTelemetryWriter(LogRotator(telem_off_path), enabled=False)
    writer_off.record(sample_telem)
    check((not telem_off_path.path.exists()) and writer_off.read_recent() == (), "Disabled telemetry must not write")

    writer_sbx = SessionTelemetryWriter(LogRotator(telem_sbx_path), env={TEST_SANDBOX_ENV_KEY: "1"})
    writer_sbx.record(sample_telem)
    check((not telem_sbx_path.path.exists()) and writer_sbx.read_recent() == (), "Sandbox telemetry must auto-disable")

    active_rot = LogRotator(telem_on_path, max_bytes=4096, keep_lines=10)
    writer_on = SessionTelemetryWriter(active_rot, env={"YSCB_LOCALE": "en"})
    second_telem = SessionTelemetryRecord(
        ts_utc="2026-11-22T01:00:01Z",
        epoch_ms=1795309201000,
        task_id="core.list",
        args=("--remote",),
        exit_code=2,
        duration_ms=45,
        executed_hot=False,
        caller_cwd=str(obs_dir),
        error_hint="offline",
    )
    writer_on.record(sample_telem)
    writer_on.record(second_telem)
    check(writer_on.read_recent() == (sample_telem, second_telem), "Active SessionTelemetryWriter round-trip mismatch")
    check(writer_on.read_recent(limit=1) == (second_telem,), "SessionTelemetryWriter limit=1 mismatch")
    active_rot.close()

    byte_cap_path = obs_dir.join("compact_byte_ceiling.log")
    byte_cap_rot = LogRotator(byte_cap_path, max_bytes=110, keep_lines=20)
    try:
        for idx in range(8):
            byte_cap_rot.append_line(f"payload_segment_number_{idx:02d}_abcdefghijklmnop")
        disk_sz = byte_cap_path.path.stat().st_size
        kept_tail = byte_cap_rot.read_tail_lines()
        check(disk_sz <= 110, f"In-place keep_lines compaction exceeded max_bytes=110: {disk_sz}")
        check(
            kept_tail == (
                "payload_segment_number_06_abcdefghijklmnop",
                "payload_segment_number_07_abcdefghijklmnop",
            ),
            f"Unexpected tail after byte-capped compaction: {kept_tail}",
        )
        byte_cap_rot.append_line("oversized_single_line_" + ("x" * 160))
        check(
            len(byte_cap_rot.read_tail_lines()) == 1,
            "Single oversized line must remain as sole surviving record",
        )
    finally:
        byte_cap_rot.close()


def _verify_foundation_primitives_errors_proc(tmp_root: Path) -> None:
    ws_hp = HostPath(tmp_root / "ws_found")
    ws_hp.path.mkdir(parents=True, exist_ok=True)

    check(safe_exception_summary(_ToxicStrError()) == "_ToxicStrError: <unprintable exception>", "Toxic str leak")
    detail = ErrorDetail(ErrorCode.BUSINESS_FAILURE, "boom", remediation="retry")
    fb_detail = detail.with_fallback_task("mod.task")
    check(fb_detail.source_task == "mod.task" and fb_detail.code == ErrorCode.BUSINESS_FAILURE, "ErrorDetail fallback failed")
    y_err = YscbError(ErrorCode.SECURITY_GATED, "denied", source_task="sec.op")
    check(y_err.detail.code == ErrorCode.SECURITY_GATED and "denied" in safe_exception_summary(y_err), "YscbError detail mismatch")

    tok_a = CancellationToken()
    tok_b = CancellationToken()
    cb_events: list[tuple[bool, str]] = []
    unreg = tok_a.register_callback(lambda p, r: cb_events.append((p, r)))
    unreg()
    tok_a.register_callback(lambda p, r: cb_events.append((p, r)))
    combined, unbind_comb = CancellationToken.combine(tok_a, tok_b)
    try:
        tok_b.cancel(preempted=True, reason="preempt_now")
        check(combined.is_cancelled and combined.is_preempted and combined.reason == "preempt_now", "combine failed")
        try:
            combined.raise_if_cancelled()
        except TaskCancelledException as exc:
            check(exc.detail.code == ErrorCode.TASK_PREEMPTED, f"Expected TASK_PREEMPTED, got {exc.detail.code}")
        else:
            raise AssertionError("Expected TaskCancelledException")
    finally:
        unbind_comb()
    tok_a.cancel(reason="manual_stop")
    check(cb_events == [(False, "manual_stop")], f"Unexpected cancel callbacks: {cb_events}")

    dg = DeadlineGuard.from_timeout_ms(250, cancel_token=CancellationToken())
    rem = dg.remaining_ms()
    check(rem is not None and 0 < rem <= 250, f"Unexpected remaining_ms: {rem}")

    assert_raises_val_error(lambda: HostPath("relative/path"))
    assert_raises_val_error(lambda: ws_hp.join("..", "escape"))
    assert_raises_val_error(lambda: ws_hp.join("bad:stream"))
    if IS_WINDOWS:
        assert_raises_val_error(lambda: ws_hp.join("CON"))
    rel_resolved = ws_hp.resolve_caller_relative("sub/item.txt")
    check(rel_resolved == ws_hp.join("sub", "item.txt"), "resolve_caller_relative mismatch")

    check(IO_REPARSE_TAG_SYMLINK == 0xA000000C, "Unexpected IO_REPARSE_TAG_SYMLINK value")
    check(IO_REPARSE_TAG_MOUNT_POINT == 0xA0000003, "Unexpected IO_REPARSE_TAG_MOUNT_POINT value")
    check(is_disallowed_reparse_tag(IO_REPARSE_TAG_SYMLINK), "Symlink reparse tag must be disallowed")
    check(is_disallowed_reparse_tag(IO_REPARSE_TAG_MOUNT_POINT), "Mount-point reparse tag must be disallowed")
    for allowed_tag in (0, 0x9000001A, 0x80000017, 0x9000101A):
        check(
            not is_disallowed_reparse_tag(allowed_tag),
            f"Benign Windows reparse tag 0x{allowed_tag:X} must be permitted",
        )
    for bad_tag in (True, -1, "0xA000000C"):
        assert_raises_val_error(lambda raw_t=bad_tag: is_disallowed_reparse_tag(raw_t))

    mod_id = ModuleId("alpha_mod")
    tid = TaskId("alpha_mod.run")
    eid = EventId("alpha_mod.evt")
    check(tid.module_id == mod_id and eid.module_id == mod_id, "module_id property mismatch")
    for bad_id in ("", "bad/slash", "no_dot", ".lead", "trail."):
        assert_raises_val_error(lambda v=bad_id: TaskId(v))
        assert_raises_val_error(lambda v=bad_id: EventId(v))
    assert_raises_val_error(lambda: ModuleId("a.b"))

    orig_sigint = signal.getsignal(signal.SIGINT)
    hits: list[str] = []
    guard = SignalWakeupGuard(
        (signal.SIGINT,),
        lambda: hits.append("first"),
        on_second_signal=lambda: hits.append("second"),
    )
    try:
        guard.install()
        signal.raise_signal(signal.SIGINT)
        wait_until(lambda: "first" in hits, timeout_sec=1.5)
        signal.raise_signal(signal.SIGINT)
        wait_until(lambda: "second" in hits, timeout_sec=1.5)
        check(hits == ["first", "second"], f"SignalWakeupGuard hits mismatch: {hits}")
    finally:
        guard.close()
        if signal.getsignal(signal.SIGINT) is not orig_sigint:
            signal.signal(signal.SIGINT, orig_sigint)
    check(signal.getsignal(signal.SIGINT) is orig_sigint, "SignalWakeupGuard failed to restore SIGINT")
    ctx_hits: list[int] = []
    with SignalWakeupGuard((signal.SIGINT,), lambda: ctx_hits.append(1)):
        signal.raise_signal(signal.SIGINT)
        wait_until(lambda: len(ctx_hits) == 1, timeout_sec=1.5)
    if signal.getsignal(signal.SIGINT) is not orig_sigint:
        signal.signal(signal.SIGINT, orig_sigint)
    check(signal.getsignal(signal.SIGINT) is orig_sigint, "Context manager failed to restore SIGINT")

    tree = ManagedProcessTree(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=ws_hp,
    )
    try:
        check(tree.pid > 0, "Invalid ManagedProcessTree pid")
        check(is_process_alive(tree.pid), "Child should be alive")
        start_tag = get_process_start_tag(tree.pid)
        check(isinstance(start_tag, str) and len(start_tag) > 0, f"Invalid start tag: {start_tag!r}")
        tree.snapshot_descendants()
        check(tree.poll() is None, "Sleep child exited prematurely")
    finally:
        tree.terminate_tree(grace_sec=0.5)
        if tree.poll() is None:
            tree.kill_tree_now()
    wait_until(lambda: not is_process_alive(tree.pid), timeout_sec=3.0)

    det_pid = spawn_detached([sys.executable, "-c", "import time; time.sleep(30)"], cwd=ws_hp)
    try:
        check(det_pid > 0 and is_process_alive(det_pid), "spawn_detached child not alive")
    finally:
        try:
            os.kill(det_pid, signal.SIGTERM)
        except OSError:
            pass
    wait_until(lambda: not is_process_alive(det_pid), timeout_sec=3.0)


def _try_create_symlink_or_junction(link_path: Path, target_path: Path, *, is_dir: bool) -> bool:
    try:
        link_path.symlink_to(target_path, target_is_directory=is_dir)
        return True
    except OSError:
        if not IS_WINDOWS or not is_dir:
            return False
        res = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
            check=False,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return res.returncode == 0


def _verify_filesystem_fs(tmp_root: Path) -> None:
    fs_root = HostPath(tmp_root / "ws_fs_root")
    outside_root = HostPath(tmp_root / "outside_fs_root")
    fs_root.path.mkdir(parents=True, exist_ok=True)
    outside_root.path.mkdir(parents=True, exist_ok=True)

    json_target = resolve_contained_subpath(fs_root, "cfg", "settings.json")
    atomic_write_json(json_target, {"version": 2, "items": ["a", "b"]})
    loaded_json = read_json_dict(fs_root, "cfg", "settings.json")
    check(loaded_json == {"version": 2, "items": ["a", "b"]}, f"Atomic JSON mismatch: {loaded_json}")

    bin_target = resolve_contained_subpath(fs_root, "cfg", "blob.bin")
    atomic_write_bytes(bin_target, b"hello-sha256")
    digest = hash_nofollow_regular_sha256(str(bin_target))
    check(len(digest) == 64, f"Unexpected sha256 digest: {digest}")

    corrupt_target = resolve_contained_subpath(fs_root, "cfg", "corrupt.json")
    atomic_write_bytes(corrupt_target, b"{not_valid_json")
    check(read_json_dict(corrupt_target) is None, "Corrupt JSON must return None")

    assert_raises_val_error(lambda: resolve_contained_subpath(fs_root, "..", "outside"))
    check(try_resolve_contained_subpath(fs_root, "..", "outside") is None, "Escape subpath must return None")
    check(is_contained_nonsymlink_path(fs_root, bin_target), "Normal file containment check failed")
    check(not is_contained_nonsymlink_path(fs_root, outside_root), "Outside path passed containment")

    secret_file = outside_root.path / "secret.txt"
    secret_file.write_text("secret", encoding="utf-8")
    link_dir = fs_root.path / "escape_dir"
    if _try_create_symlink_or_junction(link_dir, outside_root.path, is_dir=True):
        try:
            check(is_symlink_or_reparse(str(link_dir)), "Reparse/symlink not detected")
            check(not is_contained_nonsymlink_path(fs_root, link_dir, is_dir=True), "Symlink dir passed containment")
            check(
                not is_contained_nonsymlink_path(fs_root, link_dir / "secret.txt"),
                "Symlink intermediate passed containment",
            )
        finally:
            if IS_WINDOWS:
                os.rmdir(link_dir)
            else:
                link_dir.unlink(missing_ok=True)

    locks_dir = resolve_contained_subpath(fs_root, "locks")
    lock_paths = CrossProcessLockPaths.for_stem(locks_dir, "domain_res")
    lk_main = lock_paths.lock_file
    lk_peer = FileLock(lock_paths.lock_file.lock_path)
    check(lk_main.acquire(shared=False, blocking=False), "Initial exclusive lock failed")
    try:
        try:
            lk_main.acquire(shared=False, blocking=False)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Same-instance double acquire must raise RuntimeError")
        check(not lk_peer.acquire(shared=False, blocking=False), "Non-blocking lock succeeded while held")
        expect_yscb_code(lambda: lk_peer.acquire(shared=False, blocking=True, timeout_sec=0.0), ErrorCode.TASK_TIMEOUT)
        lk_main.downgrade_to_shared()
        check(lk_main.is_shared, "Lock should be shared after downgrade")
        check(lk_peer.acquire(shared=True, blocking=False), "Peer shared lock failed while downgraded")
        lk_peer.release()
        lk_main.upgrade_to_exclusive()
        check(not lk_main.is_shared, "Lock should be exclusive after upgrade")
    finally:
        if lk_peer.is_acquired:
            lk_peer.release()
        if lk_main.is_acquired:
            lk_main.release()
    child_lock_script = (
        "import sys, time\n"
        "from core.filesystem.fs import FileLock\n"
        "from core.foundation import HostPath\n"
        "lk = FileLock(HostPath(sys.argv[1]))\n"
        "assert lk.acquire(shared=False, blocking=False)\n"
        "try:\n"
        "    with open(sys.argv[2], 'w', encoding='utf-8') as f: f.write('held')\n"
        "    while not open_ok(sys.argv[3]): time.sleep(0.02)\n"
        "finally:\n"
        "    lk.release()\n"
    ).replace(
        "while not open_ok(sys.argv[3])",
        "import os\n    while not os.path.exists(sys.argv[3])",
    )
    held_marker = fs_root.path / "child_held.flag"
    release_marker = fs_root.path / "child_release.flag"
    env_cp = os.environ.copy()
    env_cp["PYTHONPATH"] = os.pathsep.join(sys.path)
    lock_proc = subprocess.Popen(
        [sys.executable, "-c", child_lock_script, str(lock_paths.lock_file.lock_path), str(held_marker), str(release_marker)],
        env=env_cp,
        creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
    )
    try:
        wait_until(lambda: held_marker.exists(), timeout_sec=5.0)
        check(not lk_peer.acquire(shared=False, blocking=False), "Cross-process lock must fail while child holds it")
        release_marker.write_text("go", encoding="utf-8")
        check(lock_proc.wait(timeout=5.0) == 0, "Lock holder child failed")
        check(lk_peer.acquire(shared=False, blocking=True, timeout_sec=2.0), "Lock acquire failed after child exited")
    finally:
        if lk_peer.is_acquired:
            lk_peer.release()
        if lock_proc.poll() is None:
            lock_proc.kill()
            lock_proc.wait(timeout=3.0)

    watch_dir = fs_root.join("watch_root")
    watch_dir.path.mkdir(parents=True, exist_ok=True)
    ignored_sub = watch_dir.path / (IGNORED_FS_PREFIXES[0] + "scratch")
    ignored_sub.mkdir(parents=True, exist_ok=True)
    suppressed_file = watch_dir.join("echo_skip.txt")
    normal_file = watch_dir.join("tracked.txt")
    batches: list[frozenset[HostPath]] = []
    batch_evt = threading.Event()
    suppressed_flag = [True]

    def _on_watch(paths: frozenset[HostPath]) -> None:
        batches.append(paths)
        batch_evt.set()

    def _is_suppressed(p: HostPath, _m: int, _s: int, _i: int) -> bool:
        return suppressed_flag[0] and p == suppressed_file

    watcher = PollingDirectoryWatcher(
        (watch_dir,),
        _on_watch,
        debounce_sec=0.04,
        poll_interval_sec=0.02,
        is_suppressed=_is_suppressed,
    )
    watcher.start()
    try:
        (ignored_sub / "temp.txt").write_text("ignored", encoding="utf-8")
        atomic_write_bytes(suppressed_file, b"suppressed_v1")
        time.sleep(0.15)
        check(not batches, f"Ignored/suppressed writes triggered watcher: {batches}")

        suppressed_flag[0] = False
        resynced = watcher.resync_paths((watch_dir,))
        check(not resynced or suppressed_file not in resynced, f"Spurious resync leakage: {resynced}")
        batches.clear()
        batch_evt.clear()

        atomic_write_bytes(normal_file, b"real_change")
        check(batch_evt.wait(timeout=2.5), "Watcher did not emit debounced batch")
        seen_paths = {p for batch in batches for p in batch}
        check(normal_file in seen_paths, f"Normal file missing in watcher batches: {seen_paths}")
        check(normal_file in watcher.tracked_paths, "Normal file missing from tracked_paths")

        check(
            DEFAULT_WATCHER_IGNORED_DIRS
            == frozenset({".git", "node_modules", ".venv", ".cache", "build", "dist", "target"}),
            f"Unexpected DEFAULT_WATCHER_IGNORED_DIRS: {DEFAULT_WATCHER_IGNORED_DIRS}",
        )
        batches.clear()
        batch_evt.clear()
        pruned_targets: list[HostPath] = []
        for pruned_name in (".git", "node_modules", ".venv", ".cache", "build", "dist", "target"):
            pruned_dir = watch_dir.path / pruned_name / "nested"
            pruned_dir.mkdir(parents=True, exist_ok=True)
            pruned_file = HostPath(pruned_dir / "ignored_artifact.txt")
            atomic_write_bytes(pruned_file, b"derived_noise")
            pruned_targets.append(pruned_file)
        time.sleep(0.15)
        check(not batches, f"Pruned derivative directories triggered watcher: {batches}")
        resynced_pruned = watcher.resync_paths((watch_dir,))
        for p_target in pruned_targets:
            check(p_target not in watcher.tracked_paths, f"Pruned file leaked into tracked_paths: {p_target}")
            check(p_target not in resynced_pruned, f"Pruned file leaked into resync_paths: {p_target}")
    finally:
        watcher.stop()

    anc_watch_dir = fs_root.join("build", "watched_app")
    anc_watch_dir.path.mkdir(parents=True, exist_ok=True)
    anc_tracked_file = anc_watch_dir.join("main.py")
    anc_nested_build_file = anc_watch_dir.join("build", "out.bin")
    check(
        is_contained_nonsymlink_path(
            anc_watch_dir,
            anc_tracked_file,
            ignored_dir_names=DEFAULT_WATCHER_IGNORED_DIRS,
        ),
        "Ancestor directory named 'build' above watch root must not be pruned",
    )
    check(
        not is_contained_nonsymlink_path(
            anc_watch_dir,
            anc_nested_build_file,
            ignored_dir_names=DEFAULT_WATCHER_IGNORED_DIRS,
        ),
        "Relative child directory named 'build' under watch root must be pruned",
    )
    anc_batches: list[frozenset[HostPath]] = []
    anc_evt = threading.Event()

    def _on_anc_watch(paths: frozenset[HostPath]) -> None:
        anc_batches.append(paths)
        anc_evt.set()

    anc_watcher = PollingDirectoryWatcher(
        (anc_watch_dir,),
        _on_anc_watch,
        debounce_sec=0.04,
        poll_interval_sec=0.02,
    )
    anc_watcher.start()
    try:
        atomic_write_bytes(anc_tracked_file, b"print_free = 1\n")
        check(anc_evt.wait(timeout=2.5), "Watcher under ancestor 'build/' failed to emit event")
        anc_seen = {p for batch in anc_batches for p in batch}
        check(anc_tracked_file in anc_seen, f"Expected main.py under ancestor 'build/': {anc_seen}")
        check(anc_tracked_file in anc_watcher.tracked_paths, "main.py missing from ancestor-build watcher tracked_paths")
    finally:
        anc_watcher.stop()


class _SampleStepExecutor:
    def __init__(self, *, fail_event: bool = False) -> None:
        self.calls: list[str] = []
        self._fail_event = fail_event

    def run_primary_step(self, request: str, turn: TurnScope) -> StepExecutionResult[str]:
        self.calls.append(f"primary:{request}")
        turn.scoped_stack.push_closeable("primary.res", lambda: self.calls.append("close:primary"))
        outbox = TaskLocalOutbox(TaskId("demo.primary"), CausalLineage())
        outbox.stage(EventId("demo.ev"), {"item": request}, ordering=EventOrdering.ORDERED)
        return StepExecutionResult(ok=True, outcome=f"done:{request}", committed_events=outbox.drain_committed())

    def run_event_step(self, batch: object, turn: TurnScope) -> Sequence[StepExecutionResult[str]]:
        _ = batch
        self.calls.append("event")
        if self._fail_event:
            diag = ErrorDetail(ErrorCode.BUSINESS_FAILURE, "event failed", source_task="demo.sub")
            turn.record_event_diagnostic(diag)
            return (StepExecutionResult(ok=False, error=diag, fatal_abort_turn=True),)
        return (StepExecutionResult(ok=True, outcome="sub_ok"),)

    def finalize_turn_events(self, _turn: TurnScope, *, abort_only: bool = False) -> Optional[ErrorDetail]:
        self.calls.append(f"finalize:{abort_only}")
        return None


class _CustomFatalBaseError(BaseException):
    pass


def _verify_event_and_lifecycle(tmp_root: Path) -> None:
    _ = tmp_root
    ev_u = EventId("mod.unord")
    ev_o = EventId("mod.ord")
    ev_meta = EventMetadata(ev_o, _CodecLeafDto, ordering=EventOrdering.ORDERED, description="ordered ev")
    check(ev_meta.event_id == ev_o and ev_meta.ordering == EventOrdering.ORDERED, "EventMetadata mismatch")

    queue = DoubleBufferedEventQueue()
    check(not queue.has_pending, "New queue should be empty")
    lin_root = CausalLineage().advance(EventId("mod.seed"), workspace_scope="ws_a")
    rec_first = RawEventRecord(ev_o, TaskId("mod.emit"), {"seq": 1}, EventOrdering.ORDERED, lin_root)
    rec_u_first = RawEventRecord(ev_u, TaskId("mod.emit"), {"k": "a"}, EventOrdering.UNORDERED, lin_root)
    rec_u_second = RawEventRecord(ev_u, TaskId("mod.emit"), {"k": "b"}, EventOrdering.UNORDERED, lin_root)
    rec_second = RawEventRecord(ev_o, TaskId("mod.emit"), {"seq": 2}, EventOrdering.ORDERED, lin_root)
    queue.append_committed((rec_first, rec_u_first, rec_u_second, rec_second))
    check(queue.has_pending, "Queue must report pending records")

    envelopes = queue.freeze_and_swap()
    check(not queue.has_pending, "Queue must empty after swap")
    ordered_seqs = [e.payloads[0]["seq"] for e in envelopes if e.event_id == ev_o]
    check(ordered_seqs == [1, 2], f"ORDERED batches broke FIFO: {ordered_seqs}")
    unord_envs = [e for e in envelopes if e.event_id == ev_u]
    check(len(unord_envs) == 1 and len(unord_envs[0].payloads) == 2, f"UNORDERED should merge: {unord_envs}")
    queue.append_committed((rec_first,))
    queue.clear()
    check(not queue.has_pending, "Queue clear failed")

    hop_a = lin_root.scoped_hops()[0]
    check(hop_conflicts(hop_a, "ws_a", EventId("mod.seed")), "Same scope+event should conflict")
    check(not hop_conflicts(hop_a, "ws_b", EventId("mod.seed")), "Different workspace scope should not conflict")
    lin_next = lin_root.advance(EventId("mod.step"), workspace_scope="ws_b")
    lin_merged = CausalLineage.merge((lin_root, lin_next))
    check(len(lin_merged.chain) >= 2, "CausalLineage merge lost hops")

    order: list[str] = []
    stack = LifoResourceStack()
    stack.push_closeable("first", lambda: order.append("first"))
    stack.push_closeable("toxic", lambda: (_ for _ in ()).throw(_ToxicStrError()))
    stack.push_closeable("sys_exit", lambda: (_ for _ in ()).throw(SystemExit(3)))
    stack.push_closeable("last", lambda: order.append("last"))
    teardown_errs = stack.close_all_lifo()
    check(order == ["last", "first"], f"LIFO order mismatch: {order}")
    check(len(teardown_errs) == 2, f"Expected 2 TEARDOWN_ERROR entries: {teardown_errs}")
    check(all(err.code == ErrorCode.TEARDOWN_ERROR for err in teardown_errs), "Wrong teardown error code")
    check(any("<unprintable exception>" in err.message for err in teardown_errs), "Toxic str leaked in teardown")

    base_order: list[str] = []
    base_stack = LifoResourceStack()
    base_stack.push_closeable("bottom", lambda: base_order.append("bottom"))
    base_stack.push_closeable("fatal", lambda: (_ for _ in ()).throw(_CustomFatalBaseError("ctrl_break")))
    base_stack.push_closeable("top", lambda: base_order.append("top"))
    try:
        base_stack.close_all_lifo()
    except _CustomFatalBaseError:
        pass
    else:
        raise AssertionError("Custom BaseException must propagate after LIFO cleanup")
    check(base_order == ["top", "bottom"], f"BaseException skipped LIFO closers: {base_order}")

    life = WorkerContainerLifecycle()
    check(life.state == ContainerState.UNINITIALIZED, "Initial state must be UNINITIALIZED")
    assert_raises_val_error(lambda: life.transition_boot_phase(ContainerState.DRAINING))
    life.transition_boot_phase(ContainerState.BOOTING)
    life.transition_boot_phase(ContainerState.WARMING)
    warm_ok: list[str] = []
    life.warmup(
        {
            ModuleId("bad_mod"): lambda: (_ for _ in ()).throw(_ToxicStrError()),
            ModuleId("good_mod"): lambda: warm_ok.append("good"),
        }
    )
    check(warm_ok == ["good"], "Warmup must isolate failing module hook")
    check(ModuleId("bad_mod") in life.degraded_modules, "Failed warmup must mark module degraded")
    life.transition_boot_phase(ContainerState.READY)
    hot_scope = life.begin_hot_turn(TurnKind.HOT_FOREGROUND, turn_id="hot_t1")
    check(hot_scope is not None and hot_scope.turn_id == "hot_t1", "begin_hot_turn failed in READY")
    life.quiesce()
    check(life.state == ContainerState.QUIESCED and life.base_state == ContainerState.READY, "Lifecycle failed to enter QUIESCED")
    life.resume()
    check(life.state == ContainerState.READY, "Lifecycle resume did not restore READY")
    drain_errs = life.drain_and_stop(grace_period_ms=500)
    check(life.state == ContainerState.STOPPED and drain_errs == (), "drain_and_stop failed")
    check(life.begin_hot_turn(TurnKind.HOT_FOREGROUND) is None, "STOPPED must reject new hot turns")

    ok_exec = _SampleStepExecutor(fail_event=False)
    ok_engine = TurnEngine(ok_exec)
    ok_rep: TurnExecutionReport = ok_engine.execute_turn("alpha", TurnKind.COLD, turn_id="cold_t1")
    check(ok_rep.primary_result.ok and ok_rep.fatal_event_error is None, "TurnEngine turn failed")
    check("event" in ok_exec.calls and "close:primary" in ok_exec.calls, f"Missing turn stages: {ok_exec.calls}")

    fail_exec = _SampleStepExecutor(fail_event=True)
    fail_runner = ColdTurnRunner(
        TurnEngine(fail_exec),
        on_bootstrap_check=lambda st: st.push_closeable("boot", lambda: fail_exec.calls.append("close:boot")),
    )
    bad_scope = TurnScope("cold_t2", TurnKind.COLD, CancellationToken())
    bad_rep = fail_runner.execute_leased_turn("beta", scope=bad_scope, fallback_task="demo.primary")
    check(bad_rep.fatal_event_error is not None, "Fatal event error not surfaced")
    check("close:boot" in fail_exec.calls, "ColdTurnRunner failed to close bootstrap closer")


class _RpcProbeHandler(InboundCallHandler):
    def __init__(self) -> None:
        self.call_started = threading.Event()
        self.allow_finish = threading.Event()
        self.saw_peer_cancel = threading.Event()

    def on_call(
        self,
        _stream_id: int,
        payload: dict[str, object],
        ack_accepted: Callable[[], bool],
        emit_progress: Callable[[dict[str, object]], None],
        peer_cancel_token: CancellationToken,
    ) -> tuple[bool, dict[str, object]]:
        _ = ack_accepted()
        self.call_started.set()
        mode = str(payload.get("mode", "fast"))
        emit_progress({"phase": mode})
        if mode == "hold":
            self.allow_finish.wait(timeout=4.0)
        elif mode == "wait_cancel":
            if peer_cancel_token.wait(timeout_sec=3.0):
                self.saw_peer_cancel.set()
            return (False, {"cancelled": True})
        return (True, {"echo": payload.get("val")})

    def on_control(self, kind: FrameKind, payload: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "kind": kind.value, "keys": list(payload.keys())}


def _verify_execution_rpc(tmp_root: Path) -> None:
    check(MAX_FRAME_BYTES == 67108864, f"Unexpected MAX_FRAME_BYTES: {MAX_FRAME_BYTES}")
    rpc_ws = HostPath(tmp_root / "ws_rpc")
    rpc_ws.path.mkdir(parents=True, exist_ok=True)
    probe_handler = _RpcProbeHandler()

    srv = RpcServerListener(rpc_ws, probe_handler, boot_id="boot_rpc_1", auth_token="rpc_secret")
    ep = srv.start()
    cli_ep_ch = None
    try:
        cli_ep_ch = connect_and_handshake(ep, handler=probe_handler, connect_timeout_sec=2.0)
        check(cli_ep_ch is not None and cli_ep_ch.ping(timeout_ms=2000), "RpcServerListener handshake/ping failed")
    finally:
        if cli_ep_ch is not None:
            cli_ep_ch.close()
        srv.close_all()

    hs_sock = bind_loopback_ephemeral()
    bad_cli: Optional[socket.socket] = None
    accepted_conn: Optional[socket.socket] = None
    try:
        hs_addr = hs_sock.getsockname()
        bad_cli = socket.create_connection((str(hs_addr[0]), int(hs_addr[1])), timeout=2.0)
        bad_cli.sendall(struct.pack(">I", 65537) + b"{}")
        accepted_conn, _addr = hs_sock.accept()
        accepted_ch = accept_worker_handshake(
            accepted_conn,
            expected_auth_token="rpc_secret",
            boot_id="boot_hs",
            handler=probe_handler,
            expected_workspace_root=rpc_ws,
        )
        check(accepted_ch is None, "Pre-auth oversized frame must be rejected")
    finally:
        for sock_obj in (accepted_conn, bad_cli, hs_sock):
            if sock_obj is not None:
                try:
                    sock_obj.close()
                except OSError:
                    pass

    left_sock, right_sock = socket.socketpair()
    cli_ch: Optional[MultiplexedChannel] = None
    srv_ch: Optional[MultiplexedChannel] = None
    try:
        cli_ch = MultiplexedChannel(left_sock, is_initiator=True, handler=probe_handler, max_frame_bytes=512)
        srv_ch = MultiplexedChannel(right_sock, is_initiator=False, handler=probe_handler, max_frame_bytes=512)
        if left_sock.family in (socket.AF_INET, socket.AF_INET6):
            nodelay_val = left_sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
            check(nodelay_val != 0, f"TCP_NODELAY not enabled on MultiplexedChannel: {nodelay_val}")

        big_out = cli_ch.call({"mode": "fast", "val": "x" * 1024})
        check(
            (not big_out.was_accepted) and big_out.error_code == ErrorCode.PAYLOAD_TOO_LARGE,
            f"Oversized payload should fail PAYLOAD_TOO_LARGE: {big_out}",
        )

        pre_cancel = CancellationToken()
        pre_cancel.cancel(reason="pre_aborted")
        unsent_out = cli_ch.call({"mode": "fast", "val": 1}, cancel_token=pre_cancel)
        check(
            (not unsent_out.was_accepted) and unsent_out.error_code == ErrorCode.TASK_CANCELLED,
            f"Pre-cancelled call should never be accepted: {unsent_out}",
        )

        probe_handler.call_started.clear()
        hold_res: list[object] = []

        def _run_hold() -> None:
            hold_res.append(cli_ch.call({"mode": "hold", "val": 99}))

        hold_thr = threading.Thread(target=_run_hold, daemon=True)
        hold_thr.start()
        check(probe_handler.call_started.wait(timeout=2.0), "Hold call did not start")
        srv_ch.close_when_idle()
        check(not srv_ch.is_closed, "close_when_idle must keep retiring channel alive while call in-flight")
        probe_handler.allow_finish.set()
        hold_thr.join(timeout=3.0)
        check(bool(hold_res) and srv_ch.wait_until_closed(timeout_sec=3.0), "Retiring channel failed to drain and close")
    finally:
        if cli_ch is not None:
            cli_ch.close()
        if srv_ch is not None:
            srv_ch.close()
        for raw_s in (left_sock, right_sock):
            try:
                raw_s.close()
            except OSError:
                pass

    c_left, c_right = socket.socketpair()
    cancel_cli: Optional[MultiplexedChannel] = None
    cancel_srv: Optional[MultiplexedChannel] = None
    try:
        probe_handler.call_started.clear()
        probe_handler.saw_peer_cancel.clear()
        cancel_cli = MultiplexedChannel(c_left, is_initiator=True, handler=probe_handler)
        cancel_srv = MultiplexedChannel(c_right, is_initiator=False, handler=probe_handler)
        live_tok = CancellationToken()
        progress_seen = threading.Event()

        def _trigger_cancel() -> None:
            if progress_seen.wait(timeout=2.0):
                live_tok.cancel(reason="abort_in_flight")

        canceller = threading.Thread(target=_trigger_cancel, daemon=True)
        canceller.start()
        in_flight_out = cancel_cli.call(
            {"mode": "wait_cancel"},
            on_progress=lambda _p: progress_seen.set(),
            cancel_token=live_tok,
        )
        canceller.join(timeout=2.0)
        check(in_flight_out.was_accepted and probe_handler.saw_peer_cancel.is_set(), "Accepted cancel failed to propagate")
    finally:
        if cancel_cli is not None:
            cancel_cli.close()
        if cancel_srv is not None:
            cancel_srv.close()
        for raw_s in (c_left, c_right):
            try:
                raw_s.close()
            except OSError:
                pass


def run_foundation_fs_suite(tmp_root: Path) -> None:
    """Run all domain unit checks for foundation, filesystem.fs, and execution.{event,lifecycle,rpc}."""
    suite_root = tmp_root / "domain_foundation_fs"
    suite_root.mkdir(parents=True, exist_ok=True)
    log("[FOUNDATION-FS] Verifying DataclassCodec contracts...")
    _verify_codec_contracts()
    log("[FOUNDATION-FS] Verifying Wave 1.2 value objects, SchemaExporter, LogRotator, and LocaleCatalog...")
    _verify_wave12_value_objects_and_env()
    _verify_schema_exporter()
    _verify_observability_rotator_locale_telemetry(suite_root)
    log("[FOUNDATION-FS] Verifying foundation primitives, errors, signals, and process trees...")
    _verify_foundation_primitives_errors_proc(suite_root)
    log("[FOUNDATION-FS] Verifying filesystem atomic I/O, containment, locks, and watcher...")
    _verify_filesystem_fs(suite_root)
    log("[FOUNDATION-FS] Verifying execution event queue, lifecycle, and RPC channels...")
    _verify_event_and_lifecycle(suite_root)
    _verify_execution_rpc(suite_root)
    log("[FOUNDATION-FS] All domain checks passed.")


__all__ = ("run_foundation_fs_suite",)
