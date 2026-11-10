"""
Atomic cloud operations and dual-mode transport layer (LocalSandboxTransport & GoogleDriveApiTransport).

Enforces 100% original file type preservation (no Google Workspace document conversion)
and resolves Google Drive Shortcuts to their target file metadata.
"""
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
import contextvars
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from http.client import HTTPSConnection
import json
import mimetypes
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request
import uuid

from core import uri
from core import vfs

from .auth_flow import (
    DRIVE_DEFAULT_SCOPE,
    OAUTH_AUTH_URL,
    OAUTH_TOKEN_URL,
    build_oauth_authorize_url,
    exchange_oauth_code_for_token,
    extract_code_from_input,
    load_oauth_client_config,
    run_oauth_loopback_flow,
)
from .config import (
    GDriveConfig,
    GDriveConfigError,
    GDriveError,
    GDriveFileNotFoundError,
    GDrivePathError,
    GDriveTransportError,
    GDriveUnsupportedMimeError,
    normalize_remote_rel_path,
)

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
GOOGLE_APPS_MIME_PREFIX = "application/vnd.google-apps."
SANDBOX_META_FILENAME = ".yscb_sandbox_meta.json"


def _parse_rfc3339_ns(ts_str: str) -> int:
    """Parse an RFC 3339 timestamp string into epoch nanoseconds (0 on invalid/empty input)."""
    if not ts_str:
        return 0
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1_000_000_000)
    except ValueError:
        return 0


def compute_local_hashes(file_path: Path) -> Tuple[str, str, int]:
    """
    Compute (md5_hex, sha256_hex, size_bytes) for a local file.
    """
    md5_hasher = hashlib.md5()
    sha_hasher = hashlib.sha256()
    total_size = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            total_size += len(chunk)
            md5_hasher.update(chunk)
            sha_hasher.update(chunk)
    return md5_hasher.hexdigest(), sha_hasher.hexdigest(), total_size


def is_unsupported_google_workspace_mime(mime_type: str) -> bool:
    """
    Return True if mime_type is a Google Workspace cloud-native document/sheet/slide/drawing
    (i.e. starts with application/vnd.google-apps. and is neither folder nor shortcut).
    """
    if not mime_type or not mime_type.startswith(GOOGLE_APPS_MIME_PREFIX):
        return False
    return mime_type not in (FOLDER_MIME_TYPE, SHORTCUT_MIME_TYPE)


@dataclass(frozen=True)
class RemoteEntry:
    """
    Metadata representation of a remote item (file, directory, or shortcut).
    """

    rel_path: str
    name: str
    file_id: str
    mime_type: str
    is_dir: bool = False
    size: int = 0
    md5: str = ""
    mtime_ns: int = 0
    parent_id: str = ""
    is_shortcut: bool = False
    target_file_id: str = ""
    target_mime_type: str = ""
    dangling_shortcut: bool = False
    skipped_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RemoteEntry":
        return cls(
            rel_path=str(data.get("rel_path") or ""),
            name=str(data.get("name") or ""),
            file_id=str(data.get("file_id") or ""),
            mime_type=str(data.get("mime_type") or "application/octet-stream"),
            is_dir=bool(data.get("is_dir", False)),
            size=int(data.get("size") or 0),
            md5=str(data.get("md5") or ""),
            mtime_ns=int(data.get("mtime_ns") or 0),
            parent_id=str(data.get("parent_id") or ""),
            is_shortcut=bool(data.get("is_shortcut", False)),
            target_file_id=str(data.get("target_file_id") or ""),
            target_mime_type=str(data.get("target_mime_type") or ""),
            dangling_shortcut=bool(data.get("dangling_shortcut", False)),
            skipped_reason=str(data.get("skipped_reason") or ""),
        )


@dataclass(frozen=True)
class ChangeRecord:
    """
    Incremental change record returned by AbstractSyncTransport.list_changes().
    """

    file_id: str
    removed: bool = False
    entry: Optional[RemoteEntry] = None
    parent_id: str = ""
    name: str = ""
    mime_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AbstractSyncTransport(ABC):
    """
    Abstract base interface for atomic Google Drive / Sandbox operations.
    """

    @abstractmethod
    def list_files(
        self,
        remote_path: str = "",
        recursive: bool = False,
        *,
        deduplicate: bool = True,
    ) -> List[RemoteEntry]:
        """List files, directories, and shortcuts under remote_path."""

    @abstractmethod
    def get_entry(self, remote_path: str) -> Optional[RemoteEntry]:
        """Retrieve a single RemoteEntry by its relative path, or None if not found."""

    @abstractmethod
    def get_entry_by_id(self, file_id: str) -> Optional[RemoteEntry]:
        """Retrieve a single RemoteEntry by its file_id, or None if not found."""

    @abstractmethod
    def mkdir(self, remote_path: str) -> RemoteEntry:
        """Recursively create directories along remote_path and return the leaf folder entry."""

    @abstractmethod
    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        in_place_file_id: Optional[str] = None,
    ) -> RemoteEntry:
        """
        Upload local_path to remote_path preserving original file bytes and type.
        If in_place_file_id is provided, updates that exact file_id in place (PATCH).
        """

    @abstractmethod
    def download_file(
        self,
        remote_path: str,
        local_path: Path,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry:
        """
        Download remote_path (or the target of a shortcut) into local_path preserving original bytes.
        Raises GDriveUnsupportedMimeError if target is a cloud-native Google Workspace item.
        """

    @abstractmethod
    def trash_file(
        self, remote_path: str, file_id: Optional[str] = None
    ) -> bool:
        """Move the item at remote_path into .trash/ (returns True if moved, False if not found)."""

    @abstractmethod
    def move_file(
        self,
        src_remote_path: str,
        dst_remote_path: str,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry:
        """Move or rename an item from src_remote_path to dst_remote_path preserving its file_id."""

    @abstractmethod
    def create_shortcut(
        self, target_file_id: str, shortcut_remote_path: str
    ) -> RemoteEntry:
        """Create a Google Drive Shortcut at shortcut_remote_path pointing to target_file_id."""

    def reset_scan_state(self) -> None:
        """Reset per-run scanned prefix tracking before a new synchronization pass."""
        return None

    def warm_folder_cache(self, entries: Dict[str, RemoteEntry]) -> None:
        """Pre-populate known remote directory entries into the transport folder cache."""
        return None

    def release_thread_resources(self) -> None:
        """Release any thread-local transport resources (such as pooled HTTPS connections) before worker exit."""
        return None

    def close(self) -> None:
        """Release any open transport connections or resources."""
        return None

    def get_start_page_token(self) -> str:
        """Retrieve the starting page token for incremental change tracking."""
        return ""

    def list_changes(
        self, page_token: str
    ) -> Tuple[List[ChangeRecord], str]:
        """List incremental changes since page_token and return (changes, new_start_page_token)."""
        return [], ""


class GoogleDriveApiTransport(AbstractSyncTransport):
    """
    Pure Python stdlib (urllib.request) client for Google Drive REST API v3.
    Supports OAuth2 token refresh, atomic file operations, and Shortcut target resolution.
    """

    DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
    DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
    FILE_FIELDS = (
        "id,name,mimeType,size,md5Checksum,modifiedTime,parents,"
        "shortcutDetails(targetId,targetMimeType)"
    )

    def __init__(self, config: GDriveConfig) -> None:
        self.config = config
        if not config.root_folder_id:
            raise GDriveConfigError(
                "root_folder_id is empty. Configure 'root_folder_id' in config://gdrive-support/ "
                "or pass --sandbox-dir for local sandbox operations."
            )
        self.root_folder_id = config.root_folder_id
        self._access_token: Optional[str] = None
        self._token_expiry_epoch: float = 0.0
        self._folder_cache: Dict[str, RemoteEntry] = {}
        self._scanned_prefixes: set[str] = set()
        self._cache_lock = threading.RLock()
        self._token_lock = threading.RLock()
        self._conn_lock = threading.RLock()
        self._conn_pool: Dict[str, List[HTTPSConnection]] = {}
        self._tls_conn_dicts: List[Dict[str, HTTPSConnection]] = []
        self._tls = threading.local()

    def reset_scan_state(self) -> None:
        with self._cache_lock:
            self._scanned_prefixes.clear()

    def warm_folder_cache(self, entries: Dict[str, RemoteEntry]) -> None:
        if not entries:
            return
        with self._cache_lock:
            for rel_p, entry in entries.items():
                norm = normalize_remote_rel_path(rel_p)
                if norm and entry.is_dir and entry.file_id:
                    self._folder_cache[norm] = entry

    def _invalidate_cache_path(self, norm_path: str) -> None:
        with self._cache_lock:
            if not norm_path:
                self._folder_cache.clear()
                return
            prefix = f"{norm_path}/"
            for k in [
                k for k in self._folder_cache if k == norm_path or k.startswith(prefix)
            ]:
                self._folder_cache.pop(k, None)

    def _get_https_conn(self, host: str) -> HTTPSConnection:
        conns: Optional[Dict[str, HTTPSConnection]] = getattr(self._tls, "conns", None)
        if conns is None:
            conns = {}
            self._tls.conns = conns
        conn = conns.get(host)
        if conn is None:
            with self._conn_lock:
                pooled = self._conn_pool.get(host)
                if pooled:
                    conn = pooled.pop()
                if conns not in self._tls_conn_dicts:
                    self._tls_conn_dicts.append(conns)
            if conn is None:
                conn = HTTPSConnection(host, timeout=60)
            conns[host] = conn
        return conn

    def release_thread_resources(self) -> None:
        self._release_thread_conns_to_pool()

    def _release_thread_conns_to_pool(self) -> None:
        """Return thread-local HTTPSConnections from short-lived worker threads to the instance pool."""
        conns: Optional[Dict[str, HTTPSConnection]] = getattr(self._tls, "conns", None)
        if not conns:
            return
        with self._conn_lock:
            for host, conn in list(conns.items()):
                conns.pop(host, None)
                self._conn_pool.setdefault(host, []).append(conn)
            try:
                self._tls_conn_dicts.remove(conns)
            except ValueError:
                pass

    def _drop_https_conn(self, host: str) -> None:
        conns: Optional[Dict[str, HTTPSConnection]] = getattr(self._tls, "conns", None)
        if conns and host in conns:
            try:
                conns.pop(host).close()
            except OSError:
                pass

    def close(self) -> None:
        """Deterministically close all open thread-local and pooled HTTPS connections."""
        closed_conns: set[int] = set()

        def _safe_close_conn(conn_obj: Any) -> None:
            cid = id(conn_obj)
            if cid in closed_conns:
                return
            closed_conns.add(cid)
            try:
                conn_obj.close()
            except OSError:
                pass

        cur_conns: Optional[Dict[str, HTTPSConnection]] = getattr(self._tls, "conns", None)
        if cur_conns:
            for host in list(cur_conns.keys()):
                _safe_close_conn(cur_conns.pop(host))

        with self._conn_lock:
            for t_dict in self._tls_conn_dicts:
                for host in list(t_dict.keys()):
                    _safe_close_conn(t_dict.pop(host))
            self._tls_conn_dicts.clear()
            for host, pool_list in list(self._conn_pool.items()):
                while pool_list:
                    _safe_close_conn(pool_list.pop())
            self._conn_pool.clear()

    def _clear_cached_token(self) -> None:
        with self._token_lock:
            self._access_token = None
            self._token_expiry_epoch = 0.0

    def _resolve_uri_path(self, raw_uri: str) -> Path:
        from .config import resolve_local_path_with_vcwd

        return resolve_local_path_with_vcwd(raw_uri)

    def _ensure_access_token(self) -> str:
        with self._token_lock:
            now = time.time()
            if self._access_token and now < self._token_expiry_epoch - 60:
                return self._access_token

            token_path = self._resolve_uri_path(self.config.token_uri)
            if not token_path.is_file():
                raise GDriveTransportError(
                    f"OAuth token file not found at '{token_path.as_posix()}'. "
                    "Run 'python yscb.py gdrive auth' to authorize."
                )
            token_data = json.loads(token_path.read_text(encoding="utf-8"))
            access_token = str(token_data.get("access_token") or "")
            expiry = float(token_data.get("expiry_epoch") or 0.0)
            if access_token and now < expiry - 60:
                self._access_token = access_token
                self._token_expiry_epoch = expiry
                return access_token

            refresh_token = str(token_data.get("refresh_token") or "")
            client_id = str(token_data.get("client_id") or "")
            client_secret = str(token_data.get("client_secret") or "")
            if not client_id or not client_secret:
                cred_path = self._resolve_uri_path(self.config.credentials_uri)
                if cred_path.is_file():
                    client_id, client_secret = load_oauth_client_config(cred_path)
            if not (refresh_token and client_id and client_secret):
                raise GDriveTransportError(
                    "Stored OAuth token is expired and lacks refresh credentials."
                )

            payload = urllib.parse.urlencode(
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                OAUTH_TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    refreshed = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                try:
                    exc.close()
                except Exception:
                    pass
                raise GDriveTransportError(f"Failed to refresh OAuth2 token: {exc}") from exc
            except Exception as exc:
                raise GDriveTransportError(f"Failed to refresh OAuth2 token: {exc}") from exc

            self._access_token = str(refreshed["access_token"])
            expires_in = float(refreshed.get("expires_in", 3600))
            self._token_expiry_epoch = time.time() + expires_in
            token_data["access_token"] = self._access_token
            token_data["expiry_epoch"] = self._token_expiry_epoch
            token_data.pop("client_secret", None)
            vfs.write_json(token_path, token_data, indent=2, encoding="utf-8", atomic=True)
            try:
                os.chmod(token_path, 0o600)
            except OSError:
                pass
            return self._access_token

    def _request_json(
        self,
        method: str,
        url: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        token = self._ensure_access_token()
        req_headers = {"Authorization": f"Bearer {token}", "Connection": "keep-alive"}
        if body is not None:
            req_headers["Content-Length"] = str(len(body))
        if headers:
            req_headers.update(headers)

        parsed = urllib.parse.urlsplit(url)
        host = parsed.netloc
        path_with_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")

        backoff = 1.0
        refreshed_on_401 = False
        for attempt in range(4):
            try:
                conn = self._get_https_conn(host)
                conn.request(method, path_with_query, body=body, headers=req_headers)
                resp = conn.getresponse()
                try:
                    raw = resp.read()
                    status = resp.status
                finally:
                    try:
                        resp.close()
                    except Exception:
                        pass
                if 200 <= status < 300:
                    return json.loads(raw.decode("utf-8")) if raw else {}
                if status == 401 and not refreshed_on_401 and attempt < 3:
                    refreshed_on_401 = True
                    self._clear_cached_token()
                    token = self._ensure_access_token()
                    req_headers["Authorization"] = f"Bearer {token}"
                    continue
                if status in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                err_body = raw.decode("utf-8", errors="replace")
                if status == 404:
                    raise GDriveFileNotFoundError(f"Drive API 404: {err_body}")
                raise GDriveTransportError(f"Drive API HTTP {status}: {err_body}")
            except (GDriveFileNotFoundError, GDriveTransportError):
                raise
            except Exception as exc:
                self._drop_https_conn(host)
                if attempt < 3:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise GDriveTransportError(f"Drive API request failed: {exc}") from exc
        raise GDriveTransportError("Drive API request exhausted retries.")

    def _raw_to_entry(
        self,
        item: Dict[str, Any],
        rel_path: str,
        target_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> RemoteEntry:
        fid = str(item.get("id") or "")
        name = str(item.get("name") or "")
        mime = str(item.get("mimeType") or "application/octet-stream")
        is_dir = mime == FOLDER_MIME_TYPE
        is_shortcut = mime == SHORTCUT_MIME_TYPE
        parents = item.get("parents") or []
        parent_id = str(parents[0]) if parents else ""

        sc_details = item.get("shortcutDetails") or {}
        target_id = str(sc_details.get("targetId") or "")
        target_mime = str(sc_details.get("targetMimeType") or "")
        dangling = False
        skipped = ""

        size = int(item.get("size") or 0)
        md5 = str(item.get("md5Checksum") or "")
        mtime_ns = _parse_rfc3339_ns(str(item.get("modifiedTime") or ""))

        if is_shortcut:
            t_obj = (target_lookup or {}).get(target_id)
            if t_obj is None:
                dangling = True
                skipped = "DANGLING_SHORTCUT"
            else:
                target_mime = str(t_obj.get("mimeType") or target_mime)
                if is_unsupported_google_workspace_mime(target_mime):
                    skipped = "SKIPPED_UNSUPPORTED_MIME"
                else:
                    size = int(t_obj.get("size") or 0)
                    md5 = str(t_obj.get("md5Checksum") or "")
                    mtime_ns = _parse_rfc3339_ns(
                        str(t_obj.get("modifiedTime") or "")
                    )
        elif is_unsupported_google_workspace_mime(mime):
            skipped = "SKIPPED_UNSUPPORTED_MIME"

        return RemoteEntry(
            rel_path=rel_path,
            name=name,
            file_id=fid,
            mime_type=mime,
            is_dir=is_dir,
            size=size,
            md5=md5,
            mtime_ns=mtime_ns,
            parent_id=parent_id,
            is_shortcut=is_shortcut,
            target_file_id=target_id,
            target_mime_type=target_mime,
            dangling_shortcut=dangling,
            skipped_reason=skipped,
        )

    def _list_children_raw(self, folder_id: str) -> List[Dict[str, Any]]:
        escaped_id = folder_id.replace("'", "\\'")
        q = f"'{escaped_id}' in parents and trashed = false"
        files: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            params: Dict[str, Any] = {
                "q": q,
                "fields": f"nextPageToken,files({self.FILE_FIELDS})",
                "pageSize": 1000,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            url = f"{self.DRIVE_API_BASE}/files?{urllib.parse.urlencode(params)}"
            data = self._request_json("GET", url)
            files.extend(data.get("files") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return files

    def _resolve_shortcut_targets(
        self, raw_items: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        target_ids = sorted(
            {
                str((it.get("shortcutDetails") or {}).get("targetId") or "")
                for it in raw_items
                if it.get("mimeType") == SHORTCUT_MIME_TYPE
            }
            - {""}
        )
        if not target_ids:
            return {}

        def _fetch_target(tid: str, release_to_pool: bool = False) -> Optional[Tuple[str, Dict[str, Any]]]:
            try:
                url = (
                    f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(tid)}"
                    f"?fields={urllib.parse.quote(self.FILE_FIELDS)}&supportsAllDrives=true"
                )
                obj = self._request_json("GET", url)
                if obj and not obj.get("trashed"):
                    return tid, obj
            except GDriveFileNotFoundError:
                return None
            finally:
                if release_to_pool:
                    self._release_thread_conns_to_pool()
            return None

        resolved: Dict[str, Dict[str, Any]] = {}
        if len(target_ids) == 1:
            pair = _fetch_target(target_ids[0], release_to_pool=False)
            if pair is not None:
                resolved[pair[0]] = pair[1]
            return resolved

        with ThreadPoolExecutor(max_workers=min(8, len(target_ids))) as pool:
            futs = [
                pool.submit(contextvars.copy_context().run, _fetch_target, tid, True)
                for tid in target_ids
            ]
            for fut in as_completed(futs):
                pair = fut.result()
                if pair is not None:
                    resolved[pair[0]] = pair[1]
        return resolved

    def _resolve_folder_id_by_path(self, rel_path: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        norm = normalize_remote_rel_path(rel_path)
        if not norm:
            return self.root_folder_id, {
                "id": self.root_folder_id,
                "name": "",
                "mimeType": FOLDER_MIME_TYPE,
            }
        parts = norm.split("/")
        curr_parent = self.root_folder_id
        curr_rel = ""
        last_item: Optional[Dict[str, Any]] = None
        for idx, part in enumerate(parts):
            curr_rel = f"{curr_rel}/{part}".strip("/") if curr_rel else part
            with self._cache_lock:
                cached_folder = self._folder_cache.get(curr_rel)
            if cached_folder is not None:
                if idx < len(parts) - 1:
                    curr_parent = cached_folder.file_id
                    continue
                return cached_folder.file_id, {
                    "id": cached_folder.file_id,
                    "name": cached_folder.name,
                    "mimeType": FOLDER_MIME_TYPE,
                }
            children = self._list_children_raw(curr_parent)
            matches = [c for c in children if c.get("name") == part]
            if not matches:
                return None
            matches.sort(
                key=lambda c: _parse_rfc3339_ns(str(c.get("modifiedTime") or "")),
                reverse=True,
            )
            chosen = matches[0]
            last_item = chosen
            if chosen.get("mimeType") == FOLDER_MIME_TYPE:
                with self._cache_lock:
                    self._folder_cache[curr_rel] = self._raw_to_entry(chosen, curr_rel)
            if idx < len(parts) - 1:
                if chosen.get("mimeType") != FOLDER_MIME_TYPE:
                    return None
                curr_parent = str(chosen["id"])
        assert last_item is not None
        return str(last_item["id"]), last_item

    def list_files(
        self,
        remote_path: str = "",
        recursive: bool = False,
        *,
        deduplicate: bool = True,
    ) -> List[RemoteEntry]:
        norm = normalize_remote_rel_path(remote_path)
        resolved_folder = self._resolve_folder_id_by_path(norm)
        if resolved_folder is None:
            return []
        folder_id, _ = resolved_folder

        collected_raw: List[Tuple[str, Dict[str, Any]]] = []

        def _walk(curr_fid: str, curr_prefix: str) -> None:
            children = self._list_children_raw(curr_fid)
            by_name: Dict[str, List[Dict[str, Any]]] = {}
            for ch in children:
                by_name.setdefault(str(ch.get("name") or ""), []).append(ch)
            for name, group in by_name.items():
                group.sort(
                    key=lambda c: _parse_rfc3339_ns(str(c.get("modifiedTime") or "")),
                    reverse=True,
                )
                winner = group[0]
                if deduplicate:
                    for loser in group[1:]:
                        if loser.get("mimeType") == FOLDER_MIME_TYPE:
                            continue
                        loser_id = str(loser.get("id") or "")
                        if loser_id:
                            try:
                                t_url = (
                                    f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(loser_id)}"
                                    f"?fields=id&supportsAllDrives=true"
                                )
                                self._request_json(
                                    "PATCH",
                                    t_url,
                                    body=json.dumps({"trashed": True}).encode("utf-8"),
                                    headers={"Content-Type": "application/json; charset=utf-8"},
                                )
                            except (GDriveError, OSError):
                                pass
                child_rel = f"{curr_prefix}/{name}".strip("/") if curr_prefix else name
                collected_raw.append((child_rel, winner))
                if winner.get("mimeType") == FOLDER_MIME_TYPE:
                    with self._cache_lock:
                        self._folder_cache[child_rel] = self._raw_to_entry(winner, child_rel)
                    if recursive:
                        _walk(str(winner["id"]), child_rel)

        _walk(folder_id, norm)
        if recursive:
            with self._cache_lock:
                self._scanned_prefixes.add(norm)
        target_map = self._resolve_shortcut_targets([it for _, it in collected_raw])
        entries = [
            self._raw_to_entry(it, rel_p, target_map) for rel_p, it in collected_raw
        ]
        entries.sort(key=lambda e: e.rel_path)
        return entries

    def get_entry(self, remote_path: str) -> Optional[RemoteEntry]:
        norm = normalize_remote_rel_path(remote_path)
        with self._cache_lock:
            cached = self._folder_cache.get(norm)
        if cached is not None:
            return cached
        res = self._resolve_folder_id_by_path(norm)
        if res is None:
            return None
        _, raw_item = res
        target_map = self._resolve_shortcut_targets([raw_item])
        return self._raw_to_entry(raw_item, norm, target_map)

    def get_entry_by_id(self, file_id: str) -> Optional[RemoteEntry]:
        try:
            url = (
                f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(file_id)}"
                f"?fields={urllib.parse.quote(self.FILE_FIELDS)}&supportsAllDrives=true"
            )
            raw_item = self._request_json("GET", url)
        except GDriveFileNotFoundError:
            return None
        target_map = self._resolve_shortcut_targets([raw_item])
        return self._raw_to_entry(raw_item, str(raw_item.get("name") or ""), target_map)

    def mkdir(self, remote_path: str) -> RemoteEntry:
        norm = normalize_remote_rel_path(remote_path)
        if not norm:
            return RemoteEntry(
                rel_path="",
                name="",
                file_id=self.root_folder_id,
                mime_type=FOLDER_MIME_TYPE,
                is_dir=True,
            )
        with self._cache_lock:
            cached_leaf = self._folder_cache.get(norm)
        if cached_leaf is not None:
            return cached_leaf
        parts = norm.split("/")
        curr_parent = self.root_folder_id
        curr_rel = ""
        last_entry: Optional[RemoteEntry] = None
        for part in parts:
            curr_rel = f"{curr_rel}/{part}".strip("/") if curr_rel else part
            with self._cache_lock:
                cached_part = self._folder_cache.get(curr_rel)
            if cached_part is not None:
                last_entry = cached_part
                curr_parent = last_entry.file_id
                continue
            children = self._list_children_raw(curr_parent)
            folder_matches = [
                c
                for c in children
                if c.get("name") == part and c.get("mimeType") == FOLDER_MIME_TYPE
            ]
            if folder_matches:
                folder_matches.sort(
                    key=lambda c: _parse_rfc3339_ns(str(c.get("modifiedTime") or "")),
                    reverse=True,
                )
                chosen = folder_matches[0]
            else:
                meta_body = json.dumps(
                    {
                        "name": part,
                        "mimeType": FOLDER_MIME_TYPE,
                        "parents": [curr_parent],
                    }
                ).encode("utf-8")
                url = (
                    f"{self.DRIVE_API_BASE}/files"
                    f"?fields={urllib.parse.quote(self.FILE_FIELDS)}&supportsAllDrives=true"
                )
                chosen = self._request_json(
                    "POST",
                    url,
                    body=meta_body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
            curr_parent = str(chosen["id"])
            last_entry = self._raw_to_entry(chosen, curr_rel)
            with self._cache_lock:
                self._folder_cache[curr_rel] = last_entry
        assert last_entry is not None
        return last_entry

    def _is_under_scanned_prefix(self, norm_path: str) -> bool:
        with self._cache_lock:
            prefixes = tuple(self._scanned_prefixes)
        for pfx in prefixes:
            if not pfx or norm_path.startswith(f"{pfx}/"):
                return True
        return False

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        in_place_file_id: Optional[str] = None,
    ) -> RemoteEntry:
        from .config import resolve_local_path_with_vcwd

        src = resolve_local_path_with_vcwd(local_path)
        if not src.is_file():
            raise GDriveFileNotFoundError(f"Local file not found: '{src.as_posix()}'")
        norm = normalize_remote_rel_path(remote_path)
        if not norm:
            raise GDrivePathError("upload_file requires a non-empty remote_path.")

        parent_rel = Path(norm).parent.as_posix()
        parent_id = self.root_folder_id
        if parent_rel and parent_rel != ".":
            parent_entry = self.mkdir(parent_rel)
            parent_id = parent_entry.file_id

        target_fid = in_place_file_id
        if not target_fid and not self._is_under_scanned_prefix(norm):
            existing = self.get_entry(norm)
            if existing and not existing.is_dir and not existing.is_shortcut:
                target_fid = existing.file_id

        guessed_mime, _ = mimetypes.guess_type(src.name)
        mime = guessed_mime or "application/octet-stream"
        file_bytes = src.read_bytes()

        if target_fid:
            url = (
                f"{self.DRIVE_UPLOAD_BASE}/files/{urllib.parse.quote(target_fid)}"
                f"?uploadType=media&fields={urllib.parse.quote(self.FILE_FIELDS)}&supportsAllDrives=true"
            )
            try:
                updated = self._request_json(
                    "PATCH",
                    url,
                    body=file_bytes,
                    headers={"Content-Type": mime},
                )
                return self._raw_to_entry(updated, norm)
            except GDriveFileNotFoundError:
                self._invalidate_cache_path(norm)
                target_fid = None

        boundary = f"yscb_boundary_{uuid.uuid4().hex}"
        meta_json = json.dumps({"name": Path(norm).name, "parents": [parent_id]}).encode(
            "utf-8"
        )
        multipart_body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        ).encode("utf-8") + meta_json + (
            f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        url = (
            f"{self.DRIVE_UPLOAD_BASE}/files"
            f"?uploadType=multipart&fields={urllib.parse.quote(self.FILE_FIELDS)}&supportsAllDrives=true"
        )
        created = self._request_json(
            "POST",
            url,
            body=multipart_body,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )
        return self._raw_to_entry(created, norm)

    def download_file(
        self,
        remote_path: str,
        local_path: Path,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry:
        norm = normalize_remote_rel_path(remote_path)
        entry = (
            entry_hint
            if (entry_hint is not None and entry_hint.file_id)
            else self.get_entry(norm)
        )
        if entry is None:
            raise GDriveFileNotFoundError(f"Remote file not found: '{norm}'")
        if entry.is_dir:
            raise GDrivePathError(f"Cannot download directory '{norm}'.")
        if entry.dangling_shortcut:
            raise GDriveFileNotFoundError(
                f"Shortcut '{norm}' points to missing target '{entry.target_file_id}'."
            )
        effective_mime = entry.target_mime_type if entry.is_shortcut else entry.mime_type
        if is_unsupported_google_workspace_mime(effective_mime):
            raise GDriveUnsupportedMimeError(
                f"Remote item '{norm}' has unsupported Google Workspace MIME '{effective_mime}'."
            )

        download_fid = entry.target_file_id if entry.is_shortcut else entry.file_id
        url = (
            f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(download_fid)}"
            "?alt=media&supportsAllDrives=true"
        )
        from .config import resolve_local_path_with_vcwd

        dst = resolve_local_path_with_vcwd(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
        backoff = 1.0
        refreshed_on_401 = False
        for attempt in range(4):
            token = self._ensure_access_token()
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {token}"}, method="GET"
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp, open(
                    tmp_dst, "wb"
                ) as out_f:
                    shutil.copyfileobj(resp, out_f)
                vfs.robust_replace(str(tmp_dst), str(dst))
                return entry
            except urllib.error.HTTPError as exc:
                try:
                    exc.close()
                except Exception:
                    pass
                if tmp_dst.exists():
                    vfs.remove(str(tmp_dst), missing_ok=True)
                if exc.code == 401 and not refreshed_on_401 and attempt < 3:
                    refreshed_on_401 = True
                    self._clear_cached_token()
                    continue
                if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                if exc.code == 404:
                    raise GDriveFileNotFoundError(
                        f"Remote file not found during download: '{norm}'"
                    ) from exc
                raise GDriveTransportError(
                    f"Failed to download '{norm}' (HTTP {exc.code}): {exc}"
                ) from exc
            except Exception as exc:
                if tmp_dst.exists():
                    vfs.remove(str(tmp_dst), missing_ok=True)
                if attempt < 3:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise GDriveTransportError(
                    f"Failed to download '{norm}': {exc}"
                ) from exc
        raise GDriveTransportError(f"Failed to download '{norm}': exhausted retries.")

    def trash_file(
        self, remote_path: str, file_id: Optional[str] = None
    ) -> bool:
        """
        Move remote_path into Google Drive's native 30-day Trash (trashed=true) without creating a .trash/ folder.
        """
        norm = normalize_remote_rel_path(remote_path)
        target_fid = str(file_id or "").strip()
        if not target_fid:
            entry = self.get_entry(norm)
            if entry is None:
                return False
            target_fid = entry.file_id
        params = urllib.parse.urlencode(
            {
                "fields": self.FILE_FIELDS,
                "supportsAllDrives": "true",
            }
        )
        url = f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(target_fid)}?{params}"
        try:
            self._request_json(
                "PATCH",
                url,
                body=json.dumps({"trashed": True}).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        except GDriveFileNotFoundError:
            self._invalidate_cache_path(norm)
            return False
        self._invalidate_cache_path(norm)
        return True

    def move_file(
        self,
        src_remote_path: str,
        dst_remote_path: str,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry:
        src_norm = normalize_remote_rel_path(src_remote_path)
        dst_norm = normalize_remote_rel_path(dst_remote_path)
        entry = (
            entry_hint
            if (entry_hint is not None and entry_hint.file_id and entry_hint.parent_id)
            else self.get_entry(src_norm)
        )
        if entry is None:
            raise GDriveFileNotFoundError(f"Source path not found: '{src_norm}'")
        dst_parent_rel = Path(dst_norm).parent.as_posix()
        new_parent_id = self.root_folder_id
        if dst_parent_rel and dst_parent_rel != ".":
            new_parent_id = self.mkdir(dst_parent_rel).file_id

        params = urllib.parse.urlencode(
            {
                "addParents": new_parent_id,
                "removeParents": entry.parent_id,
                "fields": self.FILE_FIELDS,
                "supportsAllDrives": "true",
            }
        )
        url = f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(entry.file_id)}?{params}"
        updated = self._request_json(
            "PATCH",
            url,
            body=json.dumps({"name": Path(dst_norm).name}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        self._invalidate_cache_path(src_norm)
        res_entry = self._raw_to_entry(updated, dst_norm)
        if res_entry.is_dir:
            with self._cache_lock:
                self._folder_cache[dst_norm] = res_entry
        return res_entry

    def create_shortcut(
        self, target_file_id: str, shortcut_remote_path: str
    ) -> RemoteEntry:
        norm = normalize_remote_rel_path(shortcut_remote_path)
        if not norm:
            raise GDrivePathError("shortcut_remote_path cannot be empty.")
        parent_rel = Path(norm).parent.as_posix()
        parent_id = self.root_folder_id
        if parent_rel and parent_rel != ".":
            parent_id = self.mkdir(parent_rel).file_id

        body = json.dumps(
            {
                "name": Path(norm).name,
                "mimeType": SHORTCUT_MIME_TYPE,
                "parents": [parent_id],
                "shortcutDetails": {"targetId": target_file_id},
            }
        ).encode("utf-8")
        url = (
            f"{self.DRIVE_API_BASE}/files"
            f"?fields={urllib.parse.quote(self.FILE_FIELDS)}&supportsAllDrives=true"
        )
        created = self._request_json(
            "POST",
            url,
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        target_map = self._resolve_shortcut_targets([created])
        return self._raw_to_entry(created, norm, target_map)

    def get_start_page_token(self) -> str:
        """Call GET /drive/v3/changes/startPageToken?supportsAllDrives=true and return startPageToken."""
        url = f"{self.DRIVE_API_BASE}/changes/startPageToken?supportsAllDrives=true"
        data = self._request_json("GET", url)
        token = str(data.get("startPageToken") or "").strip()
        if not token:
            raise GDriveTransportError(
                "Drive API changes/startPageToken returned an empty startPageToken."
            )
        return token

    def list_changes(
        self, page_token: str
    ) -> Tuple[List[ChangeRecord], str]:
        """
        Paginate GET /drive/v3/changes until newStartPageToken is reached.
        Returns (records, new_start_page_token).
        """
        if not page_token:
            raise GDriveTransportError("page_token cannot be empty for list_changes().")
        curr_token = page_token
        new_start_token = ""
        raw_changes: List[Dict[str, Any]] = []
        fields_spec = (
            "nextPageToken,newStartPageToken,"
            "changes(fileId,removed,file(id,name,mimeType,size,md5Checksum,"
            "modifiedTime,trashed,parents,shortcutDetails))"
        )
        while curr_token:
            params = {
                "pageToken": curr_token,
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "pageSize": 1000,
                "fields": fields_spec,
            }
            url = f"{self.DRIVE_API_BASE}/changes?{urllib.parse.urlencode(params)}"
            data = self._request_json("GET", url)
            raw_changes.extend(data.get("changes") or [])
            if data.get("newStartPageToken"):
                new_start_token = str(data["newStartPageToken"])
            curr_token = str(data.get("nextPageToken") or "")
            if not curr_token:
                break

        active_file_objs = [
            ch["file"]
            for ch in raw_changes
            if isinstance(ch.get("file"), dict)
            and not ch.get("removed")
            and not ch["file"].get("trashed")
        ]
        target_map = self._resolve_shortcut_targets(active_file_objs)

        records: List[ChangeRecord] = []
        for ch in raw_changes:
            file_obj = ch.get("file") if isinstance(ch.get("file"), dict) else {}
            fid = str(ch.get("fileId") or file_obj.get("id") or "")
            if not fid:
                continue
            is_removed = bool(ch.get("removed")) or bool(file_obj.get("trashed"))
            if is_removed:
                records.append(ChangeRecord(file_id=fid, removed=True))
                with self._cache_lock:
                    self._folder_cache = {
                        k: v for k, v in self._folder_cache.items() if v.file_id != fid
                    }
            else:
                ent = self._raw_to_entry(file_obj, "", target_map)
                if ent.is_dir:
                    with self._cache_lock:
                        self._folder_cache = {
                            k: v for k, v in self._folder_cache.items() if v.file_id != fid
                        }
                records.append(
                    ChangeRecord(
                        file_id=fid,
                        removed=False,
                        entry=ent,
                        parent_id=ent.parent_id,
                        name=ent.name,
                        mime_type=ent.mime_type,
                    )
                )
        return records, new_start_token or page_token


from .sandbox_transport import LocalSandboxTransport  # noqa: E402


def create_transport(
    config: GDriveConfig, sandbox_dir: Optional[str] = None
) -> AbstractSyncTransport:
    """
    Factory returning LocalSandboxTransport when sandbox_dir (or config.sandbox_dir) is provided,
    otherwise returning GoogleDriveApiTransport.
    """
    effective_sandbox = (sandbox_dir or config.sandbox_dir or "").strip()
    if effective_sandbox:
        from .config import resolve_local_path_with_vcwd

        resolved = resolve_local_path_with_vcwd(effective_sandbox)
        return LocalSandboxTransport(resolved)
    return GoogleDriveApiTransport(config)
