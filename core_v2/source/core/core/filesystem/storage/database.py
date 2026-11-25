"""Thin sqlite3 WAL MVCC persistence engine, snapshot readers, serialized write transactions, and schema migrations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import math
import os
import sqlite3
import stat
import threading
import time
from typing import Callable, Final, Iterator, Optional, Sequence, TypeAlias

from core.filesystem.fs import has_symlink_raw_path, is_symlink_or_reparse
from core.filesystem.vfs import ScopedVfs, VfsCapabilities
from core.foundation.errors import ErrorCode, YscbError, safe_exception_summary
from core.foundation.observability import CancellationToken
from core.foundation.primitives import (
    INT64_MAX,
    INT64_MIN,
    HostPath,
    SemanticUri,
    SnapshotGen,
    require_pure_bool,
    require_pure_int,
    require_pure_str,
    require_typed_tuple,
)

SqlParam: TypeAlias = None | bool | int | float | str | bytes
SqlParams: TypeAlias = Sequence[SqlParam]
SqlRow: TypeAlias = tuple[SqlParam, ...]

_STG_REQUIRED_CAPS: Final[VfsCapabilities] = (
    VfsCapabilities.READABLE
    | VfsCapabilities.WRITABLE
    | VfsCapabilities.PERSISTENT
    | VfsCapabilities.PHYSICAL_PATH
)

_STG_CREATE_GEN_TABLE_SQL: Final[str] = (
    "CREATE TABLE IF NOT EXISTS _yscb_generation ("
    "singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1), "
    "committed_gen INTEGER NOT NULL DEFAULT 0, "
    "updated_at_ns INTEGER NOT NULL DEFAULT 0"
    ")"
)

_STG_CREATE_WATERMARKS_TABLE_SQL: Final[str] = (
    "CREATE TABLE IF NOT EXISTS _yscb_watermarks ("
    "watermark_key TEXT PRIMARY KEY, "
    "watermark_value TEXT NOT NULL, "
    "updated_at_ns INTEGER NOT NULL DEFAULT 0"
    ")"
)

_STG_INIT_GEN_ROW_SQL: Final[str] = (
    "INSERT OR IGNORE INTO _yscb_generation (singleton_id, committed_gen, updated_at_ns) "
    "VALUES (1, 0, 0)"
)


def stg_verify_local_storage_target(
    vfs: ScopedVfs,
    raw_uri: SemanticUri | str,
    *,
    label: str,
    require_non_root: bool,
) -> tuple[SemanticUri, HostPath]:
    """Verify that target URI resolves to an authorized, non-Git-tracked persistent local path."""
    if not isinstance(vfs, ScopedVfs):
        raise TypeError(f"{label} requires a ScopedVfs instance, got {type(vfs).__name__}")
    if not isinstance(raw_uri, SemanticUri):
        require_pure_str(raw_uri, f"{label} uri", non_empty=True)
    bound_uri = vfs.bind_uri(raw_uri)
    if require_non_root and not bound_uri.rel_path:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"{label} target '{bound_uri}' must specify a concrete file path under 'storage.local://'.",
            remediation="Specify a file path such as 'storage.local://@/state.db'.",
        )
    try:
        caps = vfs.get_capabilities(bound_uri)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.URI_UNDEFINED:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"{label} target '{bound_uri}' is not an accessible persistent local storage space: {exc.detail.message}",
                remediation="Use 'storage.local://@/...' for ModuleDatabase and BlobVault persistence.",
            ) from exc
        raise
    if (caps & _STG_REQUIRED_CAPS) != _STG_REQUIRED_CAPS:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"{label} target '{bound_uri}' lacks required persistent local capabilities ({caps!r}).",
            remediation="Use 'storage.local://@/...' for ModuleDatabase and BlobVault persistence.",
        )
    if bool(caps & VfsCapabilities.GIT_TRACKED):
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"{label} target '{bound_uri}' resides in a Git-tracked space and cannot host binary state.",
            remediation="Move databases and blob vaults to 'storage.local://@/...'.",
        )
    if not vfs.can_write(bound_uri):
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Module '{vfs.module_id}' is not authorized to write to storage target '{bound_uri}'.",
            remediation="Bind storage under the owning module's 'storage.local://@/...' namespace.",
        )
    try:
        phys = vfs.try_get_physical_path(bound_uri)
    except YscbError as exc:
        if exc.detail.code == ErrorCode.URI_UNDEFINED:
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"{label} target '{bound_uri}' has no configured local filesystem backing: {exc.detail.message}",
                remediation="Mount 'storage.local://' with PhysicalDirectoryProvider.",
            ) from exc
        raise
    if phys is None:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"{label} target '{bound_uri}' is not backed by a physical host filesystem path.",
            remediation="Mount 'storage.local://' with PhysicalDirectoryProvider.",
        )
    try:
        storage_local_root = vfs.try_get_physical_path(SemanticUri("storage.local", ""))
    except YscbError as exc:
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"{label} requires a configured 'storage.local://' physical root: {exc.detail.message}",
            remediation="Mount 'storage.local://' with PhysicalDirectoryProvider.",
        ) from exc
    root_key = storage_local_root.comparison_key.rstrip("/\\") if storage_local_root is not None else ""
    phys_key = phys.comparison_key.rstrip("/\\")
    within_local = bool(root_key) and (
        (phys_key == root_key and not require_non_root) or phys_key.startswith(f"{root_key}{os.sep}")
    )
    if not within_local or has_symlink_raw_path(str(phys)):
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"{label} target '{bound_uri}' must reside strictly within 'storage.local://'.",
            remediation="Use 'storage.local://@/...' instead of config.local:// or other schemes.",
        )
    return (bound_uri, phys)


_SQLITE_PRIMARY_BUSY: Final[int] = 5
_SQLITE_PRIMARY_LOCKED: Final[int] = 6
_SQLITE_PRIMARY_IOERR: Final[int] = 10
_SQLITE_PRIMARY_CORRUPT: Final[int] = 11
_SQLITE_PRIMARY_NOTADB: Final[int] = 26

_SQLITE_TIMEOUT_CODES: Final[frozenset[int]] = frozenset(
    {
        _SQLITE_PRIMARY_BUSY,
        _SQLITE_PRIMARY_LOCKED,
    }
)
_SQLITE_CORRUPT_CODES: Final[frozenset[int]] = frozenset(
    {
        _SQLITE_PRIMARY_IOERR,
        _SQLITE_PRIMARY_CORRUPT,
        _SQLITE_PRIMARY_NOTADB,
    }
)
_SQLITE_TIMEOUT_TOKENS: Final[tuple[str, ...]] = (
    "database is locked",
    "database table is locked",
    "is locked",
    "busy",
)
_SQLITE_CORRUPT_TOKENS: Final[tuple[str, ...]] = (
    "malformed",
    "not a database",
    "corrupt",
    "disk i/o error",
)


def _stg_sqlite_primary_errorcode(exc: sqlite3.Error) -> Optional[int]:
    try:
        raw_code = exc.sqlite_errorcode
    except AttributeError:
        return None
    if type(raw_code) is int and raw_code > 0:
        return raw_code & 0xFF
    return None


def _stg_translate_db_error(exc: sqlite3.Error, uri_text: str) -> YscbError:
    """Classify sqlite3.Error into TASK_TIMEOUT, BUSINESS_FAILURE, or STORAGE_CORRUPT."""
    primary_code = _stg_sqlite_primary_errorcode(exc)
    msg_low = str(exc).lower()
    summary = safe_exception_summary(exc)

    if primary_code in _SQLITE_TIMEOUT_CODES or (
        isinstance(exc, sqlite3.OperationalError)
        and any(tok in msg_low for tok in _SQLITE_TIMEOUT_TOKENS)
    ):
        return YscbError(
            ErrorCode.TASK_TIMEOUT,
            f"SQLite lock busy/timeout on '{uri_text}': {summary}",
            remediation="Retry after concurrent database lock clears or increase StorageOpenOptions.busy_timeout_ms.",
        )

    if isinstance(
        exc,
        (
            sqlite3.IntegrityError,
            sqlite3.ProgrammingError,
            sqlite3.DataError,
            sqlite3.NotSupportedError,
            sqlite3.InterfaceError,
        ),
    ):
        return YscbError(
            ErrorCode.BUSINESS_FAILURE,
            f"SQLite query or constraint error on '{uri_text}': {summary}",
            remediation="Inspect SQL statement syntax, parameter bindings, or schema constraints.",
        )

    if primary_code in _SQLITE_CORRUPT_CODES or (
        primary_code is None and any(tok in msg_low for tok in _SQLITE_CORRUPT_TOKENS)
    ):
        return YscbError(
            ErrorCode.STORAGE_CORRUPT,
            f"SQLite corruption or I/O error on '{uri_text}': {summary}",
            remediation="Verify disk health or rebuild the affected local storage database under 'storage.local://'.",
        )

    if isinstance(exc, sqlite3.OperationalError):
        return YscbError(
            ErrorCode.BUSINESS_FAILURE,
            f"SQLite operational error on '{uri_text}': {summary}",
            remediation="Inspect SQL statement, table schema, or available local disk space.",
        )

    return YscbError(
        ErrorCode.STORAGE_CORRUPT,
        f"SQLite error on '{uri_text}': {summary}",
        remediation="Verify disk health or rebuild the affected local storage database under 'storage.local://'.",
    )


def _stg_normalize_sql_param(val: object) -> SqlParam:
    if val is None or type(val) is bool:
        return val
    if type(val) is int:
        if not (INT64_MIN <= val <= INT64_MAX):
            raise ValueError(f"SQL integer parameter out of int64 range: {val!r}")
        return val
    if type(val) is float:
        if not math.isfinite(val):
            raise ValueError(f"SQL float parameter must be finite: {val!r}")
        return val
    if type(val) is str:
        val.encode("utf-8")
        return val
    if type(val) is bytes:
        return val
    raise TypeError(f"Unsupported SQL parameter type {type(val).__name__}: {val!r}")


def _stg_normalize_sql_params(params: SqlParams) -> tuple[SqlParam, ...]:
    if isinstance(params, (str, bytes, bytearray, memoryview)) or not isinstance(params, Sequence):
        raise TypeError(f"SQL params must be a non-string Sequence, got {type(params).__name__}")
    return tuple(_stg_normalize_sql_param(item) for item in params)


def _stg_normalize_sql_row(raw_row: Sequence[object]) -> SqlRow:
    return tuple(_stg_normalize_sql_param(col) if type(col) is not float else col for col in raw_row)


def _stg_exec_sql(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[SqlParam, ...],
    uri_text: str,
) -> int:
    try:
        cur = conn.execute(sql, params)
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, uri_text) from exc
    try:
        rc = cur.rowcount
        return int(rc) if rc is not None and rc > 0 else 0
    finally:
        cur.close()


def _stg_exec_many_sql(
    conn: sqlite3.Connection,
    sql: str,
    param_rows: list[tuple[SqlParam, ...]],
    uri_text: str,
) -> int:
    if not param_rows:
        return 0
    try:
        cur = conn.executemany(sql, param_rows)
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, uri_text) from exc
    try:
        rc = cur.rowcount
        return int(rc) if rc is not None and rc > 0 else 0
    finally:
        cur.close()


def _stg_query_one_sql(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[SqlParam, ...],
    uri_text: str,
) -> Optional[SqlRow]:
    try:
        cur = conn.execute(sql, params)
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, uri_text) from exc
    try:
        row = cur.fetchone()
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, uri_text) from exc
    finally:
        cur.close()
    if row is None:
        return None
    return _stg_normalize_sql_row(row)


def _stg_query_all_sql(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[SqlParam, ...],
    uri_text: str,
) -> list[SqlRow]:
    try:
        cur = conn.execute(sql, params)
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, uri_text) from exc
    try:
        rows = cur.fetchall()
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, uri_text) from exc
    finally:
        cur.close()
    return [_stg_normalize_sql_row(r) for r in rows]


def _stg_safe_rollback(conn: sqlite3.Connection) -> None:
    try:
        if conn.in_transaction:
            conn.execute("ROLLBACK").close()
    except sqlite3.Error:
        pass


def _stg_safe_close_conn(conn: Optional[sqlite3.Connection]) -> None:
    if conn is None:
        return
    _stg_safe_rollback(conn)
    try:
        conn.close()
    except sqlite3.Error:
        pass


def _stg_read_committed_gen(conn: sqlite3.Connection, uri_text: str) -> SnapshotGen:
    row = _stg_query_one_sql(
        conn,
        "SELECT committed_gen FROM _yscb_generation WHERE singleton_id = 1",
        (),
        uri_text,
    )
    if row is None or type(row[0]) is not int or row[0] < 0:
        raise YscbError(
            ErrorCode.STORAGE_CORRUPT,
            f"Missing or invalid _yscb_generation singleton row in '{uri_text}'.",
            remediation="Rebuild the corrupted local database under 'storage.local://'.",
        )
    return SnapshotGen(row[0])


def _stg_read_watermark(conn: sqlite3.Connection, key: str, uri_text: str) -> Optional[str]:
    clean_key = require_pure_str(key, "watermark key")
    if not clean_key:
        raise ValueError("watermark key must be a non-empty str.")
    row = _stg_query_one_sql(
        conn,
        "SELECT watermark_value FROM _yscb_watermarks WHERE watermark_key = ?",
        (clean_key,),
        uri_text,
    )
    if row is None:
        return None
    if type(row[0]) is not str:
        raise YscbError(
            ErrorCode.STORAGE_CORRUPT,
            f"Corrupt non-text watermark value for key {clean_key!r} in '{uri_text}'.",
            remediation="Rebuild the corrupted local database under 'storage.local://'.",
        )
    return row[0]


def _stg_read_user_version(conn: sqlite3.Connection, uri_text: str) -> int:
    row = _stg_query_one_sql(conn, "PRAGMA user_version", (), uri_text)
    if row is None or type(row[0]) is not int or row[0] < 0:
        raise YscbError(
            ErrorCode.STORAGE_CORRUPT,
            f"Invalid PRAGMA user_version in '{uri_text}': {row!r}",
            remediation="Rebuild the corrupted local database under 'storage.local://'.",
        )
    return row[0]


def _stg_has_initialized_system_tables(conn: sqlite3.Connection, uri_text: str) -> bool:
    cnt_row = _stg_query_one_sql(
        conn,
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name IN ('_yscb_generation', '_yscb_watermarks')",
        (),
        uri_text,
    )
    if cnt_row is None or cnt_row[0] != 2:
        return False
    gen_row = _stg_query_one_sql(
        conn,
        "SELECT committed_gen FROM _yscb_generation WHERE singleton_id = 1",
        (),
        uri_text,
    )
    return gen_row is not None and type(gen_row[0]) is int and gen_row[0] >= 0


def _stg_verify_sqlite_files_safe(physical_path: HostPath, uri_text: str) -> None:
    raw_base = str(physical_path)
    if has_symlink_raw_path(raw_base):
        raise YscbError(
            ErrorCode.ACCESS_DENIED,
            f"Refusing SQLite path traversing symlink or reparse point for '{uri_text}': {raw_base}",
            remediation="Ensure 'storage.local://' contains only regular directories and files.",
        )
    for idx, cand in enumerate((raw_base, f"{raw_base}-wal", f"{raw_base}-shm", f"{raw_base}-journal")):
        if is_symlink_or_reparse(cand) or has_symlink_raw_path(cand):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Refusing symlink or reparse SQLite file for '{uri_text}': {cand}",
                remediation="Remove symbolic links or reparse points from 'storage.local://'.",
            )
        try:
            st = os.lstat(cand)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(st.st_mode) and idx == 0:
            raise YscbError(
                ErrorCode.STORAGE_CORRUPT,
                f"ModuleDatabase target '{uri_text}' points to a directory rather than a SQLite file.",
                remediation="Specify a database filename under 'storage.local://@/...'.",
            )
        if not stat.S_ISREG(st.st_mode):
            raise YscbError(
                ErrorCode.ACCESS_DENIED,
                f"Refusing non-regular SQLite node (FIFO/socket/device/dir) for '{uri_text}': {cand}",
                remediation="Ensure SQLite database and WAL/SHM files are regular host files.",
            )


def _stg_open_sqlite_conn(
    physical_path: HostPath,
    options: StorageOpenOptions,
    uri_text: str,
    *,
    writable: bool,
) -> sqlite3.Connection:
    _stg_verify_sqlite_files_safe(physical_path, uri_text)
    try:
        conn = sqlite3.connect(
            str(physical_path),
            timeout=options.busy_timeout_ms / 1000.0,
            isolation_level=None,
            check_same_thread=False,
        )
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, uri_text) from exc
    try:
        _stg_exec_sql(conn, f"PRAGMA busy_timeout = {options.busy_timeout_ms}", (), uri_text)
        if writable:
            wal_deadline = time.monotonic() + (options.busy_timeout_ms / 1000.0)
            wal_sleep = 0.01
            mode_row: Optional[tuple[object, ...]] = None
            while True:
                try:
                    cur_mode = _stg_query_one_sql(conn, "PRAGMA journal_mode", (), uri_text)
                    if cur_mode is not None and isinstance(cur_mode[0], str) and cur_mode[0].lower() == "wal":
                        mode_row = cur_mode
                        break
                    mode_row = _stg_query_one_sql(conn, "PRAGMA journal_mode = WAL", (), uri_text)
                    break
                except YscbError as exc:
                    if exc.detail.code != ErrorCode.TASK_TIMEOUT or time.monotonic() >= wal_deadline:
                        raise
                    time.sleep(min(wal_sleep, max(0.0, wal_deadline - time.monotonic())))
                    wal_sleep = min(0.1, wal_sleep * 2.0)
            if mode_row is None or not isinstance(mode_row[0], str) or mode_row[0].lower() != "wal":
                raise YscbError(
                    ErrorCode.STORAGE_CORRUPT,
                    f"Failed to enable WAL mode for '{uri_text}' (got {mode_row!r}).",
                    remediation="Ensure 'storage.local://' resides on a local filesystem supporting SQLite WAL.",
                )
        _stg_exec_sql(conn, "PRAGMA synchronous = NORMAL", (), uri_text)
        _stg_exec_sql(conn, "PRAGMA foreign_keys = ON", (), uri_text)
        _stg_exec_sql(conn, "PRAGMA temp_store = MEMORY", (), uri_text)
        if writable:
            _stg_exec_sql(
                conn,
                f"PRAGMA wal_autocheckpoint = {options.wal_autocheckpoint_pages}",
                (),
                uri_text,
            )
        else:
            _stg_exec_sql(conn, "PRAGMA query_only = ON", (), uri_text)
    except BaseException:
        _stg_safe_close_conn(conn)
        raise
    return conn


@dataclass(frozen=True, slots=True)
class StorageOpenOptions:
    busy_timeout_ms: int = 5000
    wal_autocheckpoint_pages: int = 1000
    read_only_pool_size: int = 4

    def __post_init__(self) -> None:
        require_pure_int(self.busy_timeout_ms, "StorageOpenOptions.busy_timeout_ms", min_val=0)
        require_pure_int(
            self.wal_autocheckpoint_pages,
            "StorageOpenOptions.wal_autocheckpoint_pages",
            min_val=0,
        )
        require_pure_int(
            self.read_only_pool_size,
            "StorageOpenOptions.read_only_pool_size",
            min_val=1,
            max_val=64,
        )


@dataclass(frozen=True, slots=True)
class SchemaMigration:
    """Unidirectional incremental schema migration step (downgrade strictly forbidden)."""

    version: int
    description: str
    sql_statements: tuple[str, ...] = ()
    migrate_fn: Optional[Callable[[WriteTransaction], None]] = None

    def __post_init__(self) -> None:
        require_pure_int(self.version, "SchemaMigration.version", min_val=1)
        require_pure_str(self.description, "SchemaMigration.description")
        norm_stmts = require_typed_tuple(
            self.sql_statements,
            str,
            "SchemaMigration.sql_statements",
        )
        object.__setattr__(self, "sql_statements", norm_stmts)
        if self.migrate_fn is not None and not callable(self.migrate_fn):
            raise ValueError("SchemaMigration.migrate_fn must be callable or None.")


@dataclass(slots=True)
class _StgSnapshotLease:
    conn: sqlite3.Connection
    uri_text: str
    snapshot_gen: SnapshotGen
    active: bool = True
    open_cursors: list[sqlite3.Cursor] = field(default_factory=list)


@dataclass(slots=True)
class _StgWriteLease:
    conn: sqlite3.Connection
    uri_text: str
    initial_gen: SnapshotGen
    current_gen: SnapshotGen
    bumped: bool = False
    active: bool = True


def _stg_iter_cursor_batches(
    lease: _StgSnapshotLease,
    sql: str,
    params: tuple[SqlParam, ...],
    batch_size: int,
) -> Iterator[SqlRow]:
    if not lease.active:
        raise YscbError(
            ErrorCode.TEARDOWN_ERROR,
            f"SnapshotReader for '{lease.uri_text}' is no longer active.",
        )
    try:
        cur = lease.conn.execute(sql, params)
    except sqlite3.Error as exc:
        raise _stg_translate_db_error(exc, lease.uri_text) from exc
    lease.open_cursors.append(cur)
    try:
        while True:
            if not lease.active:
                raise YscbError(
                    ErrorCode.TEARDOWN_ERROR,
                    f"SnapshotReader for '{lease.uri_text}' closed during row iteration.",
                )
            try:
                batch = cur.fetchmany(batch_size)
            except sqlite3.Error as exc:
                raise _stg_translate_db_error(exc, lease.uri_text) from exc
            if not batch:
                return
            for raw_row in batch:
                yield _stg_normalize_sql_row(raw_row)
    finally:
        if cur in lease.open_cursors:
            lease.open_cursors.remove(cur)
        try:
            cur.close()
        except sqlite3.Error:
            pass


class SnapshotReader:
    """Read-only MVCC snapshot reader releasing its WAL snapshot on context exit."""

    _lease: Optional[_StgSnapshotLease] = None

    def _active_lease(self) -> _StgSnapshotLease:
        lease = self._lease
        if lease is None or not lease.active:
            raise YscbError(
                ErrorCode.TEARDOWN_ERROR,
                "SnapshotReader is inactive outside ModuleDatabase.read_snapshot().",
            )
        return lease

    def committed_gen(self) -> SnapshotGen:
        return self._active_lease().snapshot_gen

    def get_watermark(self, key: str) -> Optional[str]:
        lease = self._active_lease()
        return _stg_read_watermark(lease.conn, key, lease.uri_text)

    def list_watermarks(self) -> dict[str, str]:
        lease = self._active_lease()
        rows = _stg_query_all_sql(
            lease.conn,
            "SELECT watermark_key, watermark_value FROM _yscb_watermarks ORDER BY watermark_key ASC",
            (),
            lease.uri_text,
        )
        out: dict[str, str] = {}
        for row in rows:
            if len(row) != 2 or type(row[0]) is not str or type(row[1]) is not str:
                raise YscbError(
                    ErrorCode.STORAGE_CORRUPT,
                    f"Corrupt row in _yscb_watermarks of '{lease.uri_text}'.",
                    remediation="Rebuild the corrupted local database under 'storage.local://'.",
                )
            out[row[0]] = row[1]
        return out

    def query_one(self, sql: str, params: SqlParams = ()) -> Optional[SqlRow]:
        lease = self._active_lease()
        clean_sql = require_pure_str(sql, "sql", non_empty=True)
        norm_params = _stg_normalize_sql_params(params)
        return _stg_query_one_sql(lease.conn, clean_sql, norm_params, lease.uri_text)

    def query_all(self, sql: str, params: SqlParams = ()) -> list[SqlRow]:
        lease = self._active_lease()
        clean_sql = require_pure_str(sql, "sql", non_empty=True)
        norm_params = _stg_normalize_sql_params(params)
        return _stg_query_all_sql(lease.conn, clean_sql, norm_params, lease.uri_text)

    def iter_rows(self, sql: str, params: SqlParams = (), *, batch_size: int = 256) -> Iterator[SqlRow]:
        lease = self._active_lease()
        clean_sql = require_pure_str(sql, "sql", non_empty=True)
        norm_params = _stg_normalize_sql_params(params)
        safe_batch = require_pure_int(batch_size, "batch_size", min_val=1)
        return _stg_iter_cursor_batches(lease, clean_sql, norm_params, safe_batch)


class _StgSnapshotReader(SnapshotReader):
    def __init__(self, lease: _StgSnapshotLease) -> None:
        self._lease = lease


class WriteTransaction:
    """Serialized BEGIN IMMEDIATE write transaction rolling back automatically on error or cancellation."""

    _lease: Optional[_StgWriteLease] = None

    def _active_lease(self) -> _StgWriteLease:
        lease = self._lease
        if lease is None or not lease.active:
            raise YscbError(
                ErrorCode.TEARDOWN_ERROR,
                "WriteTransaction is inactive outside ModuleDatabase.write_transaction().",
            )
        return lease

    @property
    def current_gen(self) -> SnapshotGen:
        return self._active_lease().current_gen

    def execute(self, sql: str, params: SqlParams = ()) -> int:
        lease = self._active_lease()
        clean_sql = require_pure_str(sql, "sql", non_empty=True)
        norm_params = _stg_normalize_sql_params(params)
        return _stg_exec_sql(lease.conn, clean_sql, norm_params, lease.uri_text)

    def executemany(self, sql: str, param_seq: Sequence[SqlParams]) -> int:
        lease = self._active_lease()
        clean_sql = require_pure_str(sql, "sql", non_empty=True)
        if isinstance(param_seq, (str, bytes, bytearray, memoryview)) or not isinstance(param_seq, Sequence):
            raise TypeError(f"param_seq must be a non-string Sequence, got {type(param_seq).__name__}")
        norm_rows = [_stg_normalize_sql_params(row_params) for row_params in param_seq]
        return _stg_exec_many_sql(lease.conn, clean_sql, norm_rows, lease.uri_text)

    def query_one(self, sql: str, params: SqlParams = ()) -> Optional[SqlRow]:
        lease = self._active_lease()
        clean_sql = require_pure_str(sql, "sql", non_empty=True)
        norm_params = _stg_normalize_sql_params(params)
        return _stg_query_one_sql(lease.conn, clean_sql, norm_params, lease.uri_text)

    def query_all(self, sql: str, params: SqlParams = ()) -> list[SqlRow]:
        lease = self._active_lease()
        clean_sql = require_pure_str(sql, "sql", non_empty=True)
        norm_params = _stg_normalize_sql_params(params)
        return _stg_query_all_sql(lease.conn, clean_sql, norm_params, lease.uri_text)

    def get_watermark(self, key: str) -> Optional[str]:
        lease = self._active_lease()
        return _stg_read_watermark(lease.conn, key, lease.uri_text)

    def set_watermark(self, key: str, value: str) -> None:
        lease = self._active_lease()
        clean_key = require_pure_str(key, "watermark key")
        if not clean_key:
            raise ValueError("watermark key must be a non-empty str.")
        clean_val = require_pure_str(value, "watermark value")
        _stg_exec_sql(
            lease.conn,
            "INSERT INTO _yscb_watermarks (watermark_key, watermark_value, updated_at_ns) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(watermark_key) DO UPDATE SET "
            "watermark_value = excluded.watermark_value, "
            "updated_at_ns = excluded.updated_at_ns",
            (clean_key, clean_val, time.time_ns()),
            lease.uri_text,
        )

    def delete_watermark(self, key: str) -> None:
        lease = self._active_lease()
        clean_key = require_pure_str(key, "watermark key")
        if not clean_key:
            raise ValueError("watermark key must be a non-empty str.")
        _stg_exec_sql(
            lease.conn,
            "DELETE FROM _yscb_watermarks WHERE watermark_key = ?",
            (clean_key,),
            lease.uri_text,
        )

    def mark_generation_bumped(self) -> SnapshotGen:
        lease = self._active_lease()
        if lease.bumped:
            return lease.current_gen
        next_gen = lease.initial_gen.next()
        _stg_exec_sql(
            lease.conn,
            "UPDATE _yscb_generation SET committed_gen = ?, updated_at_ns = ? WHERE singleton_id = 1",
            (next_gen.value, time.time_ns()),
            lease.uri_text,
        )
        lease.bumped = True
        lease.current_gen = next_gen
        return next_gen


class _StgWriteTransaction(WriteTransaction):
    def __init__(self, lease: _StgWriteLease) -> None:
        self._lease = lease


def _stg_validate_migration_plan(migrations: Sequence[SchemaMigration]) -> tuple[SchemaMigration, ...]:
    steps = require_typed_tuple(migrations, SchemaMigration, "migrations")
    for expected_ver, step in enumerate(steps, start=1):
        if step.version != expected_ver:
            raise YscbError(
                ErrorCode.SCHEMA_MIGRATION_ERROR,
                f"SchemaMigration versions must increase contiguously from 1; expected {expected_ver}, got {step.version}.",
                remediation="Supply SchemaMigration steps ordered strictly as 1, 2, ..., N without gaps or duplicates.",
            )
    return steps


def _stg_bootstrap_and_migrate(
    write_conn: sqlite3.Connection,
    steps: tuple[SchemaMigration, ...],
    uri_text: str,
) -> int:
    target_ver = len(steps)
    _stg_exec_sql(write_conn, "BEGIN IMMEDIATE", (), uri_text)
    committed = False
    try:
        db_ver = _stg_read_user_version(write_conn, uri_text)
        if db_ver > target_ver:
            raise YscbError(
                ErrorCode.SCHEMA_MIGRATION_ERROR,
                f"Database '{uri_text}' schema version ({db_ver}) exceeds supported version ({target_ver}).",
                remediation="Upgrade the module/runtime rather than downgrading a newer local database.",
            )
        if db_ver == target_ver and _stg_has_initialized_system_tables(write_conn, uri_text):
            return target_ver
        _stg_exec_sql(write_conn, _STG_CREATE_GEN_TABLE_SQL, (), uri_text)
        _stg_exec_sql(write_conn, _STG_CREATE_WATERMARKS_TABLE_SQL, (), uri_text)
        _stg_exec_sql(write_conn, _STG_INIT_GEN_ROW_SQL, (), uri_text)
        init_gen = _stg_read_committed_gen(write_conn, uri_text)
        lease = _StgWriteLease(
            conn=write_conn,
            uri_text=uri_text,
            initial_gen=init_gen,
            current_gen=init_gen,
        )
        tx: WriteTransaction = _StgWriteTransaction(lease)
        try:
            for step in steps:
                if step.version <= db_ver:
                    continue
                try:
                    for stmt_sql in step.sql_statements:
                        if stmt_sql.strip():
                            _stg_exec_sql(write_conn, stmt_sql, (), uri_text)
                    if step.migrate_fn is not None:
                        step.migrate_fn(tx)
                    _stg_exec_sql(write_conn, f"PRAGMA user_version = {step.version}", (), uri_text)
                except YscbError as exc:
                    if exc.detail.code != ErrorCode.BUSINESS_FAILURE:
                        raise
                    cause = exc.__cause__ if exc.__cause__ is not None else exc
                    raise YscbError(
                        ErrorCode.SCHEMA_MIGRATION_ERROR,
                        f"Migration to version {step.version} ({step.description}) failed on '{uri_text}': "
                        f"{safe_exception_summary(cause)}",
                        remediation="Inspect the migration SQL/callback logic or rebuild the local database.",
                    ) from cause
                except Exception as exc:
                    raise YscbError(
                        ErrorCode.SCHEMA_MIGRATION_ERROR,
                        f"Migration to version {step.version} ({step.description}) failed on '{uri_text}': "
                        f"{safe_exception_summary(exc)}",
                        remediation="Inspect the migration logic or rebuild the local database.",
                    ) from exc
        finally:
            lease.active = False
        _stg_exec_sql(write_conn, "COMMIT", (), uri_text)
        committed = True
        return target_ver
    finally:
        if not committed:
            _stg_safe_rollback(write_conn)


class ModuleDatabase:
    """Module-scoped SQLite WAL MVCC persistence engine strictly restricted to storage.local://."""

    def __init__(
        self,
        vfs: ScopedVfs,
        db_uri: SemanticUri | str,
        *,
        migrations: Sequence[SchemaMigration] = (),
        options: StorageOpenOptions = StorageOpenOptions(),
    ) -> None:
        if not isinstance(options, StorageOpenOptions):
            raise TypeError(f"options must be StorageOpenOptions, got {type(options).__name__}")
        steps = _stg_validate_migration_plan(migrations)
        bound_uri, phys = stg_verify_local_storage_target(
            vfs,
            db_uri,
            label="ModuleDatabase",
            require_non_root=True,
        )
        parent_uri = bound_uri.parent
        if parent_uri is not None and vfs.can_write(parent_uri):
            vfs.mkdir(parent_uri, parents=True)
        else:
            os.makedirs(phys.path.parent, exist_ok=True)
        uri_text = str(bound_uri)
        _stg_verify_sqlite_files_safe(phys, uri_text)
        write_conn = _stg_open_sqlite_conn(phys, options, uri_text, writable=True)
        try:
            final_ver = _stg_bootstrap_and_migrate(write_conn, steps, uri_text)
        except BaseException:
            _stg_safe_close_conn(write_conn)
            raise

        self._db_uri: SemanticUri = bound_uri
        self._uri_text: str = uri_text
        self._physical_path: HostPath = phys
        self._options: StorageOpenOptions = options
        self._schema_version: int = final_ver
        self._write_lock = threading.Lock()
        self._pool_lock = threading.Lock()
        self._pool_cond = threading.Condition(self._pool_lock)
        self._write_owner_tid: Optional[int] = None
        self._write_conn: Optional[sqlite3.Connection] = write_conn
        self._idle_readers: list[sqlite3.Connection] = []
        self._borrowed_readers: int = 0
        self._reader_counts_by_tid: dict[int, int] = {}
        self._closed: bool = False

    @property
    def db_uri(self) -> SemanticUri:
        return self._db_uri

    @property
    def physical_path(self) -> HostPath:
        return self._physical_path

    @property
    def schema_version(self) -> int:
        return self._schema_version

    @property
    def is_closed(self) -> bool:
        with self._pool_lock:
            return self._closed

    def _ensure_open(self) -> None:
        with self._pool_lock:
            if self._closed:
                raise YscbError(
                    ErrorCode.TEARDOWN_ERROR,
                    f"ModuleDatabase '{self._uri_text}' is already closed.",
                )

    def _decrement_reader_locked(self, borrower_tid: int) -> None:
        self._borrowed_readers = max(0, self._borrowed_readers - 1)
        prev_cnt = self._reader_counts_by_tid.get(borrower_tid, 0)
        if prev_cnt <= 1:
            self._reader_counts_by_tid.pop(borrower_tid, None)
        else:
            self._reader_counts_by_tid[borrower_tid] = prev_cnt - 1
        if self._closed and self._borrowed_readers == 0:
            self._pool_cond.notify_all()

    def _borrow_read_conn(self) -> tuple[sqlite3.Connection, int]:
        tid = threading.get_ident()
        with self._pool_lock:
            if self._closed:
                raise YscbError(
                    ErrorCode.TEARDOWN_ERROR,
                    f"ModuleDatabase '{self._uri_text}' is already closed.",
                )
            self._borrowed_readers += 1
            self._reader_counts_by_tid[tid] = self._reader_counts_by_tid.get(tid, 0) + 1
            if self._idle_readers:
                return (self._idle_readers.pop(), tid)
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _stg_open_sqlite_conn(
                self._physical_path,
                self._options,
                self._uri_text,
                writable=False,
            )
            with self._pool_lock:
                if not self._closed:
                    return (conn, tid)
        except BaseException:
            _stg_safe_close_conn(conn)
            with self._pool_cond:
                self._decrement_reader_locked(tid)
            raise
        _stg_safe_close_conn(conn)
        with self._pool_cond:
            self._decrement_reader_locked(tid)
        raise YscbError(
            ErrorCode.TEARDOWN_ERROR,
            f"ModuleDatabase '{self._uri_text}' closed while opening snapshot reader.",
        )

    def _return_read_conn(self, conn: sqlite3.Connection, borrower_tid: int) -> None:
        _stg_safe_rollback(conn)
        close_outside = False
        with self._pool_lock:
            if not self._closed and len(self._idle_readers) < self._options.read_only_pool_size:
                self._idle_readers.append(conn)
            else:
                close_outside = True
        if close_outside:
            _stg_safe_close_conn(conn)
        with self._pool_cond:
            self._decrement_reader_locked(borrower_tid)

    def _acquire_write_lock(self, cancel_token: Optional[CancellationToken]) -> None:
        tid = threading.get_ident()
        with self._pool_lock:
            if self._closed:
                raise YscbError(
                    ErrorCode.TEARDOWN_ERROR,
                    f"ModuleDatabase '{self._uri_text}' is already closed.",
                )
            if self._write_owner_tid == tid or self._reader_counts_by_tid.get(tid, 0) > 0:
                raise YscbError(
                    ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                    f"Nested or read-upgraded write operation on the same thread is forbidden for '{self._uri_text}'.",
                )
        while not self._write_lock.acquire(timeout=0.01):
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            self._ensure_open()

    @contextmanager
    def read_snapshot(self) -> Iterator[SnapshotReader]:
        conn, borrower_tid = self._borrow_read_conn()
        lease: Optional[_StgSnapshotLease] = None
        try:
            _stg_exec_sql(conn, "PRAGMA query_only = ON", (), self._uri_text)
            _stg_exec_sql(conn, "BEGIN DEFERRED", (), self._uri_text)
            snap_gen = _stg_read_committed_gen(conn, self._uri_text)
            lease = _StgSnapshotLease(
                conn=conn,
                uri_text=self._uri_text,
                snapshot_gen=snap_gen,
            )
            reader: SnapshotReader = _StgSnapshotReader(lease)
            yield reader
        finally:
            if lease is not None:
                lease.active = False
                for cur in list(lease.open_cursors):
                    try:
                        cur.close()
                    except sqlite3.Error:
                        pass
                lease.open_cursors.clear()
            self._return_read_conn(conn, borrower_tid)

    @contextmanager
    def write_transaction(
        self,
        *,
        cancel_token: Optional[CancellationToken] = None,
    ) -> Iterator[WriteTransaction]:
        if cancel_token is not None and not isinstance(cancel_token, CancellationToken):
            raise TypeError(f"cancel_token must be CancellationToken or None, got {type(cancel_token).__name__}")
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        self._acquire_write_lock(cancel_token)
        try:
            with self._pool_lock:
                if self._closed or self._write_conn is None:
                    raise YscbError(
                        ErrorCode.TEARDOWN_ERROR,
                        f"ModuleDatabase '{self._uri_text}' is already closed.",
                    )
                write_conn = self._write_conn
                self._write_owner_tid = threading.get_ident()
            try:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                _stg_exec_sql(write_conn, "BEGIN IMMEDIATE", (), self._uri_text)
                committed = False
                lease: Optional[_StgWriteLease] = None
                try:
                    init_gen = _stg_read_committed_gen(write_conn, self._uri_text)
                    lease = _StgWriteLease(
                        conn=write_conn,
                        uri_text=self._uri_text,
                        initial_gen=init_gen,
                        current_gen=init_gen,
                    )
                    tx: WriteTransaction = _StgWriteTransaction(lease)
                    yield tx
                    if cancel_token is not None:
                        cancel_token.raise_if_cancelled()
                    lease.active = False
                    _stg_exec_sql(write_conn, "COMMIT", (), self._uri_text)
                    committed = True
                finally:
                    if lease is not None:
                        lease.active = False
                    if not committed:
                        _stg_safe_rollback(write_conn)
            finally:
                with self._pool_lock:
                    self._write_owner_tid = None
        finally:
            self._write_lock.release()

    def committed_gen(self) -> SnapshotGen:
        with self.read_snapshot() as reader:
            return reader.committed_gen()

    def get_watermark(self, key: str) -> Optional[str]:
        with self.read_snapshot() as reader:
            return reader.get_watermark(key)

    def checkpoint(self, *, truncate: bool = False) -> tuple[int, int]:
        require_pure_bool(truncate, "truncate")
        self._acquire_write_lock(None)
        try:
            with self._pool_lock:
                if self._closed or self._write_conn is None:
                    raise YscbError(
                        ErrorCode.TEARDOWN_ERROR,
                        f"ModuleDatabase '{self._uri_text}' is already closed.",
                    )
                write_conn = self._write_conn
            mode = "TRUNCATE" if truncate else "PASSIVE"
            row = _stg_query_one_sql(write_conn, f"PRAGMA wal_checkpoint({mode})", (), self._uri_text)
            if row is None or len(row) < 3 or type(row[1]) is not int or type(row[2]) is not int:
                return (0, 0)
            total_frames = max(0, row[1])
            checkpointed_frames = max(0, row[2])
            return (total_frames, checkpointed_frames)
        finally:
            self._write_lock.release()

    def verify_integrity(self) -> bool:
        with self.read_snapshot() as reader:
            integrity_rows = reader.query_all("PRAGMA integrity_check")
            if len(integrity_rows) != 1 or integrity_rows[0] != ("ok",):
                return False
            fk_rows = reader.query_all("PRAGMA foreign_key_check")
            return len(fk_rows) == 0

    def close(self) -> None:
        tid = threading.get_ident()
        with self._pool_cond:
            if self._write_owner_tid == tid:
                raise YscbError(
                    ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                    f"Cannot close ModuleDatabase '{self._uri_text}' from inside an active write_transaction().",
                )
            if self._reader_counts_by_tid.get(tid, 0) > 0:
                raise YscbError(
                    ErrorCode.ILLEGAL_LOCK_REENTRANCY,
                    f"Cannot close ModuleDatabase '{self._uri_text}' from inside an active read_snapshot().",
                )
            self._closed = True
            idle_conns = list(self._idle_readers)
            self._idle_readers.clear()
            while self._borrowed_readers > 0:
                self._pool_cond.wait()
        for r_conn in idle_conns:
            _stg_safe_close_conn(r_conn)
        with self._write_lock:
            with self._pool_lock:
                write_conn = self._write_conn
                self._write_conn = None
            _stg_safe_close_conn(write_conn)

    def __enter__(self) -> ModuleDatabase:
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)
        self.close()
