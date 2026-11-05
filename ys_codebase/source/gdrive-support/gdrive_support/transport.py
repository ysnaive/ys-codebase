"""
Atomic cloud operations and dual-mode transport layer (LocalSandboxTransport & GoogleDriveApiTransport).

Enforces 100% original file type preservation (no Google Workspace document conversion)
and resolves Google Drive Shortcuts to their target file metadata.
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import html
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
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
import webbrowser

from core import uri
from core import vfs

from .config import (
    GDriveConfig,
    GDriveConfigError,
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
        self, remote_path: str = "", recursive: bool = False
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
    def download_file(self, remote_path: str, local_path: Path) -> RemoteEntry:
        """
        Download remote_path (or the target of a shortcut) into local_path preserving original bytes.
        Raises GDriveUnsupportedMimeError if target is a cloud-native Google Workspace item.
        """

    @abstractmethod
    def trash_file(self, remote_path: str) -> bool:
        """Move the item at remote_path into .trash/ (returns True if moved, False if not found)."""

    @abstractmethod
    def move_file(self, src_remote_path: str, dst_remote_path: str) -> RemoteEntry:
        """Move or rename an item from src_remote_path to dst_remote_path preserving its file_id."""

    @abstractmethod
    def create_shortcut(
        self, target_file_id: str, shortcut_remote_path: str
    ) -> RemoteEntry:
        """Create a Google Drive Shortcut at shortcut_remote_path pointing to target_file_id."""

    def get_start_page_token(self) -> str:
        """Retrieve the starting page token for incremental change tracking."""
        return ""

    def list_changes(
        self, page_token: str
    ) -> Tuple[List[ChangeRecord], str]:
        """List incremental changes since page_token and return (changes, new_start_page_token)."""
        return [], ""


class LocalSandboxTransport(AbstractSyncTransport):
    """
    100% offline filesystem-backed simulation of Google Drive REST API v3 semantics.
    Maintains a metadata sidecar (.yscb_sandbox_meta.json) to faithfully track stable file_ids,
    shortcuts, .trash/ movement, duplicate same-name resolution, and unsupported MIME simulation.
    """

    def __init__(self, sandbox_root: Path) -> None:
        self.root = Path(sandbox_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._meta_path = self.root / SANDBOX_META_FILENAME
        self._lock = threading.RLock()
        self._ensure_meta()

    def _ensure_meta(self) -> Dict[str, Any]:
        with self._lock:
            if self._meta_path.is_file():
                try:
                    data = json.loads(self._meta_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "items" in data:
                        return data
                except Exception:
                    pass
            init_data: Dict[str, Any] = {
                "root_id": "sandbox_root",
                "items": {},
            }
            self._save_meta(init_data)
            return init_data

    def _save_meta(self, data: Dict[str, Any]) -> None:
        with self._lock:
            vfs.write_json(self._meta_path, data, indent=2, encoding="utf-8", atomic=True)

    def _phys_path(self, rel_path: str) -> Path:
        norm = normalize_remote_rel_path(rel_path)
        if not norm:
            return self.root
        target = (self.root / norm).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise GDrivePathError(
                f"Sandbox path '{rel_path}' escapes sandbox root."
            ) from exc
        return target

    def _sync_filesystem_into_meta(self) -> Dict[str, Any]:
        meta = self._ensure_meta()
        items: Dict[str, Dict[str, Any]] = meta.setdefault("items", {})
        path_to_ids: Dict[str, List[str]] = {}
        for fid, info in list(items.items()):
            rel = info.get("rel_path", "")
            path_to_ids.setdefault(rel, []).append(fid)

        changed = False
        for dirpath, dirnames, filenames in os.walk(self.root):
            dir_p = Path(dirpath)
            for d in list(dirnames):
                if d == SANDBOX_META_FILENAME:
                    dirnames.remove(d)
            for fn in filenames:
                if fn == SANDBOX_META_FILENAME:
                    continue
                abs_f = dir_p / fn
                rel_f = abs_f.relative_to(self.root).as_posix()
                if rel_f not in path_to_ids:
                    fid = f"sbx_{uuid.uuid4().hex[:12]}"
                    md5_hex, _, sz = compute_local_hashes(abs_f)
                    st = abs_f.stat()
                    guessed_mime, _ = mimetypes.guess_type(abs_f.name)
                    items[fid] = {
                        "file_id": fid,
                        "rel_path": rel_f,
                        "name": abs_f.name,
                        "mime_type": guessed_mime or "application/octet-stream",
                        "is_dir": False,
                        "is_shortcut": False,
                        "target_file_id": "",
                        "size": sz,
                        "md5": md5_hex,
                        "mtime_ns": int(st.st_mtime_ns),
                    }
                    path_to_ids[rel_f] = [fid]
                    changed = True

            if dir_p != self.root:
                rel_d = dir_p.relative_to(self.root).as_posix()
                if rel_d not in path_to_ids:
                    fid = f"sbx_dir_{uuid.uuid4().hex[:10]}"
                    st = dir_p.stat()
                    items[fid] = {
                        "file_id": fid,
                        "rel_path": rel_d,
                        "name": dir_p.name,
                        "mime_type": FOLDER_MIME_TYPE,
                        "is_dir": True,
                        "is_shortcut": False,
                        "target_file_id": "",
                        "size": 0,
                        "md5": "",
                        "mtime_ns": int(st.st_mtime_ns),
                    }
                    path_to_ids[rel_d] = [fid]
                    changed = True

        if changed:
            self._save_meta(meta)
        return meta

    def inject_virtual_entry(
        self,
        rel_path: str,
        mime_type: str,
        file_id: Optional[str] = None,
        mtime_ns: Optional[int] = None,
        md5: str = "",
        size: int = 0,
    ) -> str:
        """
        Helper for sandbox testing: inject a metadata entry (e.g., unsupported Google Docs MIME
        or duplicate same-name entry) directly into sandbox metadata.
        """
        norm = normalize_remote_rel_path(rel_path)
        meta = self._ensure_meta()
        fid = file_id or f"sbx_{uuid.uuid4().hex[:12]}"
        name = Path(norm).name if norm else ""
        meta["items"][fid] = {
            "file_id": fid,
            "rel_path": norm,
            "name": name,
            "mime_type": mime_type,
            "is_dir": mime_type == FOLDER_MIME_TYPE,
            "is_shortcut": mime_type == SHORTCUT_MIME_TYPE,
            "is_virtual": True,
            "target_file_id": "",
            "size": size,
            "md5": md5,
            "mtime_ns": mtime_ns if mtime_ns is not None else time.time_ns(),
        }
        self._save_meta(meta)
        return fid

    def _build_entry(
        self, info: Dict[str, Any], items_by_id: Dict[str, Dict[str, Any]]
    ) -> RemoteEntry:
        rel_p = str(info.get("rel_path") or "")
        name = str(info.get("name") or Path(rel_p).name)
        fid = str(info.get("file_id") or "")
        mime = str(info.get("mime_type") or "application/octet-stream")
        is_dir = bool(info.get("is_dir") or mime == FOLDER_MIME_TYPE)
        is_shortcut = bool(info.get("is_shortcut") or mime == SHORTCUT_MIME_TYPE)
        target_id = str(info.get("target_file_id") or "")
        target_mime = ""
        dangling = False
        skipped = ""

        size = int(info.get("size") or 0)
        md5 = str(info.get("md5") or "")
        mtime_ns = int(info.get("mtime_ns") or 0)

        if (
            not is_dir
            and not is_shortcut
            and not info.get("is_virtual")
            and not is_unsupported_google_workspace_mime(mime)
        ):
            phys = self._phys_path(rel_p)
            if phys.is_file():
                md5, _, size = compute_local_hashes(phys)
                mtime_ns = int(phys.stat().st_mtime_ns)

        if is_shortcut:
            target_info = items_by_id.get(target_id)
            target_rel = str(target_info.get("rel_path") or "") if target_info else ""
            if (
                target_info is None
                or not target_rel
                or target_rel == ".trash"
                or target_rel.startswith(".trash/")
            ):
                dangling = True
                skipped = "DANGLING_SHORTCUT"
            else:
                target_mime = str(target_info.get("mime_type") or "")
                if is_unsupported_google_workspace_mime(target_mime):
                    skipped = "SKIPPED_UNSUPPORTED_MIME"
                else:
                    target_phys = self._phys_path(target_rel)
                    if target_phys.is_file():
                        md5, _, size = compute_local_hashes(target_phys)
                        mtime_ns = int(target_phys.stat().st_mtime_ns)
                    else:
                        md5 = str(target_info.get("md5") or "")
                        size = int(target_info.get("size") or 0)
                        mtime_ns = int(target_info.get("mtime_ns") or mtime_ns)
        elif is_unsupported_google_workspace_mime(mime):
            skipped = "SKIPPED_UNSUPPORTED_MIME"

        parent_rel = Path(rel_p).parent.as_posix()
        if parent_rel in ("", "."):
            parent_id = "sandbox_root"
        else:
            parent_id = parent_rel
            for p_info in items_by_id.values():
                if p_info.get("rel_path") == parent_rel and (
                    p_info.get("is_dir") or p_info.get("mime_type") == FOLDER_MIME_TYPE
                ):
                    parent_id = str(p_info.get("file_id") or parent_rel)
                    break

        return RemoteEntry(
            rel_path=rel_p,
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

    def _deduplicate_same_path_items(
        self, meta: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        If multiple items exist at the exact same rel_path (e.g. web Gemini created a new file
        with the same name), keep the one with the latest mtime_ns and move older ones to .trash/.
        """
        items: Dict[str, Dict[str, Any]] = meta.get("items", {})
        by_path: Dict[str, List[Dict[str, Any]]] = {}
        for info in items.values():
            rel_p = str(info.get("rel_path") or "")
            if not rel_p or rel_p == ".trash" or rel_p.startswith(".trash/"):
                continue
            by_path.setdefault(rel_p, []).append(info)

        dirty = False
        for rel_p, group in by_path.items():
            if len(group) <= 1:
                continue
            group.sort(key=lambda x: (int(x.get("mtime_ns") or 0), str(x.get("file_id") or "")), reverse=True)
            for older in group[1:]:
                old_fid = str(older.get("file_id") or "")
                trash_rel = f".trash/{old_fid}_{Path(rel_p).name}"
                older["rel_path"] = trash_rel
                if not older.get("is_shortcut") and not is_unsupported_google_workspace_mime(
                    str(older.get("mime_type") or "")
                ):
                    src_phys = self._phys_path(rel_p)
                    dst_phys = self._phys_path(trash_rel)
                    dst_phys.parent.mkdir(parents=True, exist_ok=True)
                    if src_phys.is_file() and not dst_phys.exists():
                        shutil.copy2(src_phys, dst_phys)
                dirty = True

        if dirty:
            self._save_meta(meta)
        return items

    def list_files(
        self, remote_path: str = "", recursive: bool = False
    ) -> List[RemoteEntry]:
        norm_prefix = normalize_remote_rel_path(remote_path)
        meta = self._sync_filesystem_into_meta()
        items = self._deduplicate_same_path_items(meta)

        results: List[RemoteEntry] = []
        for info in items.values():
            rel_p = str(info.get("rel_path") or "")
            if not rel_p:
                continue
            if not norm_prefix:
                if not recursive and "/" in rel_p:
                    continue
            else:
                if not rel_p.startswith(f"{norm_prefix}/"):
                    continue
                sub_rel = rel_p[len(norm_prefix) + 1 :]
                if not sub_rel:
                    continue
                if not recursive and "/" in sub_rel:
                    continue

            if not info.get("is_shortcut") and not is_unsupported_google_workspace_mime(
                str(info.get("mime_type") or "")
            ):
                phys = self._phys_path(rel_p)
                if not phys.exists():
                    continue

            results.append(self._build_entry(info, items))

        results.sort(key=lambda e: e.rel_path)
        return results

    def get_entry(self, remote_path: str) -> Optional[RemoteEntry]:
        norm = normalize_remote_rel_path(remote_path)
        if not norm:
            return RemoteEntry(
                rel_path="",
                name="",
                file_id="sandbox_root",
                mime_type=FOLDER_MIME_TYPE,
                is_dir=True,
            )
        with self._lock:
            meta = self._sync_filesystem_into_meta()
            items = self._deduplicate_same_path_items(meta)
            for info in items.values():
                if info.get("rel_path") == norm:
                    if not info.get("is_shortcut") and not is_unsupported_google_workspace_mime(
                        str(info.get("mime_type") or "")
                    ):
                        if not self._phys_path(norm).exists():
                            continue
                    return self._build_entry(info, items)
            return None

    def get_entry_by_id(self, file_id: str) -> Optional[RemoteEntry]:
        with self._lock:
            meta = self._sync_filesystem_into_meta()
            items = meta.get("items", {})
            info = items.get(file_id)
            if not info:
                return None
            return self._build_entry(info, items)

    def mkdir(self, remote_path: str) -> RemoteEntry:
        norm = normalize_remote_rel_path(remote_path)
        if not norm:
            return RemoteEntry(
                rel_path="",
                name="",
                file_id="sandbox_root",
                mime_type=FOLDER_MIME_TYPE,
                is_dir=True,
            )
        with self._lock:
            existing = self.get_entry(norm)
            if existing is not None and existing.is_dir:
                return existing

            phys = self._phys_path(norm)
            phys.mkdir(parents=True, exist_ok=True)
            meta = self._sync_filesystem_into_meta()
            items = meta.get("items", {})
            for info in items.values():
                if info.get("rel_path") == norm and info.get("is_dir"):
                    return self._build_entry(info, items)

            fid = f"sbx_dir_{uuid.uuid4().hex[:10]}"
            items[fid] = {
                "file_id": fid,
                "rel_path": norm,
                "name": phys.name,
                "mime_type": FOLDER_MIME_TYPE,
                "is_dir": True,
                "is_shortcut": False,
                "target_file_id": "",
                "size": 0,
                "md5": "",
                "mtime_ns": int(phys.stat().st_mtime_ns),
            }
            self._save_meta(meta)
            return self._build_entry(items[fid], items)

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        in_place_file_id: Optional[str] = None,
    ) -> RemoteEntry:
        src = Path(local_path).resolve()
        if not src.is_file():
            raise GDriveFileNotFoundError(f"Local file does not exist: '{src.as_posix()}'")

        norm = normalize_remote_rel_path(remote_path)
        if not norm:
            raise GDrivePathError("upload_file requires a non-empty target remote_path.")

        parent_rel = Path(norm).parent.as_posix()
        if parent_rel and parent_rel != ".":
            self.mkdir(parent_rel)

        dst = self._phys_path(norm)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        md5_hex, _, sz = compute_local_hashes(dst)
        mtime_ns = int(dst.stat().st_mtime_ns)
        guessed_mime, _ = mimetypes.guess_type(dst.name)
        mime = guessed_mime or "application/octet-stream"

        with self._lock:
            meta = self._ensure_meta()
            items = meta["items"]

            target_fid: Optional[str] = None
            if in_place_file_id and in_place_file_id in items:
                target_fid = in_place_file_id
            else:
                for fid, info in items.items():
                    if info.get("rel_path") == norm and not info.get("is_shortcut"):
                        target_fid = fid
                        break

            if target_fid is None:
                target_fid = in_place_file_id or f"sbx_{uuid.uuid4().hex[:12]}"

            items[target_fid] = {
                "file_id": target_fid,
                "rel_path": norm,
                "name": dst.name,
                "mime_type": mime,
                "is_dir": False,
                "is_shortcut": False,
                "target_file_id": "",
                "size": sz,
                "md5": md5_hex,
                "mtime_ns": mtime_ns,
            }
            self._save_meta(meta)
            return self._build_entry(items[target_fid], items)

    def download_file(self, remote_path: str, local_path: Path) -> RemoteEntry:
        norm = normalize_remote_rel_path(remote_path)
        entry = self.get_entry(norm)
        if entry is None:
            raise GDriveFileNotFoundError(f"Remote file not found: '{norm}'")
        if entry.is_dir:
            raise GDrivePathError(f"Cannot download directory '{norm}' as a single file.")
        if entry.dangling_shortcut:
            raise GDriveFileNotFoundError(
                f"Shortcut '{norm}' points to a missing target file_id '{entry.target_file_id}'."
            )
        if entry.skipped_reason == "SKIPPED_UNSUPPORTED_MIME" or is_unsupported_google_workspace_mime(
            entry.target_mime_type if entry.is_shortcut else entry.mime_type
        ):
            raise GDriveUnsupportedMimeError(
                f"Remote item '{norm}' has unsupported Google Workspace cloud-native MIME type "
                f"('{entry.target_mime_type or entry.mime_type}'). Original file types only."
            )

        meta = self._ensure_meta()
        items = meta["items"]
        if entry.is_shortcut:
            target_info = items.get(entry.target_file_id)
            if not target_info:
                raise GDriveFileNotFoundError(
                    f"Shortcut target '{entry.target_file_id}' not found."
                )
            src_phys = self._phys_path(str(target_info.get("rel_path") or ""))
        else:
            src_phys = self._phys_path(norm)

        if not src_phys.is_file():
            raise GDriveFileNotFoundError(f"Sandbox backing file missing for '{norm}'.")

        dst = Path(local_path).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
        shutil.copy2(src_phys, tmp_dst)
        os.replace(tmp_dst, dst)
        return entry

    def trash_file(self, remote_path: str) -> bool:
        norm = normalize_remote_rel_path(remote_path)
        if not norm:
            raise GDrivePathError("Cannot trash root directory.")
        entry = self.get_entry(norm)
        if entry is None:
            return False

        self.mkdir(".trash")
        meta = self._ensure_meta()
        items = meta["items"]
        info = items.get(entry.file_id)
        if not info:
            return False

        trash_rel = f".trash/{entry.file_id}_{entry.name}"
        if not entry.is_shortcut and not is_unsupported_google_workspace_mime(entry.mime_type):
            src_phys = self._phys_path(norm)
            dst_phys = self._phys_path(trash_rel)
            dst_phys.parent.mkdir(parents=True, exist_ok=True)
            if src_phys.exists():
                shutil.move(str(src_phys), str(dst_phys))

        if entry.is_dir:
            prefix = f"{norm}/"
            for child_info in items.values():
                c_rel = str(child_info.get("rel_path") or "")
                if c_rel.startswith(prefix):
                    child_info["rel_path"] = f"{trash_rel}/{c_rel[len(prefix):]}"

        info["rel_path"] = trash_rel
        info["name"] = Path(trash_rel).name
        self._save_meta(meta)
        return True

    def move_file(self, src_remote_path: str, dst_remote_path: str) -> RemoteEntry:
        src_norm = normalize_remote_rel_path(src_remote_path)
        dst_norm = normalize_remote_rel_path(dst_remote_path)
        if not src_norm or not dst_norm:
            raise GDrivePathError("move_file requires non-empty src and dst paths.")

        entry = self.get_entry(src_norm)
        if entry is None:
            raise GDriveFileNotFoundError(f"Source path not found: '{src_norm}'")

        dst_parent = Path(dst_norm).parent.as_posix()
        if dst_parent and dst_parent != ".":
            self.mkdir(dst_parent)

        meta = self._ensure_meta()
        items = meta["items"]
        for fid, existing in list(items.items()):
            if existing.get("rel_path") == dst_norm and fid != entry.file_id:
                del items[fid]

        info = items[entry.file_id]
        if not entry.is_shortcut and not is_unsupported_google_workspace_mime(entry.mime_type):
            src_phys = self._phys_path(src_norm)
            dst_phys = self._phys_path(dst_norm)
            dst_phys.parent.mkdir(parents=True, exist_ok=True)
            if src_phys.exists():
                shutil.move(str(src_phys), str(dst_phys))

        info["rel_path"] = dst_norm
        info["name"] = Path(dst_norm).name
        self._save_meta(meta)
        return self._build_entry(info, items)

    def create_shortcut(
        self, target_file_id: str, shortcut_remote_path: str
    ) -> RemoteEntry:
        norm = normalize_remote_rel_path(shortcut_remote_path)
        if not norm:
            raise GDrivePathError("shortcut_remote_path cannot be empty.")

        parent_rel = Path(norm).parent.as_posix()
        if parent_rel and parent_rel != ".":
            self.mkdir(parent_rel)

        with self._lock:
            meta = self._sync_filesystem_into_meta()
            items = meta["items"]
            target_info = items.get(target_file_id)
            if target_info is not None and target_info.get("is_dir"):
                raise GDrivePathError(
                    f"Creating a shortcut to a folder ('{target_file_id}') is forbidden."
                )

            existing_fid: Optional[str] = None
            for fid, info in items.items():
                if info.get("rel_path") == norm:
                    existing_fid = fid
                    break

            sc_fid = existing_fid or f"sbx_sc_{uuid.uuid4().hex[:10]}"
            items[sc_fid] = {
                "file_id": sc_fid,
                "rel_path": norm,
                "name": Path(norm).name,
                "mime_type": SHORTCUT_MIME_TYPE,
                "is_dir": False,
                "is_shortcut": True,
                "target_file_id": target_file_id,
                "size": 0,
                "md5": "",
                "mtime_ns": time.time_ns(),
            }
            self._save_meta(meta)
            return self._build_entry(items[sc_fid], items)

    def _capture_change_snapshot(
        self, items: Dict[str, Dict[str, Any]]
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, RemoteEntry]]:
        snap: Dict[str, Dict[str, Any]] = {}
        entries: Dict[str, RemoteEntry] = {}
        for fid, info in items.items():
            rel_p = str(info.get("rel_path") or "")
            if (
                not rel_p
                or rel_p == ".trash"
                or rel_p.startswith(".trash/")
                or bool(info.get("trashed"))
            ):
                continue
            mime = str(info.get("mime_type") or "")
            if (
                not info.get("is_shortcut")
                and not info.get("is_virtual")
                and not is_unsupported_google_workspace_mime(mime)
            ):
                phys = self._phys_path(rel_p)
                if not phys.exists():
                    continue
            entry = self._build_entry(info, items)
            entries[fid] = entry
            snap[fid] = {
                "rel_path": entry.rel_path,
                "name": entry.name,
                "mime_type": entry.mime_type,
                "is_dir": entry.is_dir,
                "size": entry.size,
                "md5": entry.md5,
                "mtime_ns": int(info.get("mtime_ns") or entry.mtime_ns)
                if entry.is_dir or entry.is_shortcut
                else entry.mtime_ns,
                "parent_id": entry.parent_id,
                "is_shortcut": entry.is_shortcut,
                "target_file_id": entry.target_file_id,
                "target_md5": (
                    entry.md5 if entry.is_shortcut and not entry.dangling_shortcut else ""
                ),
                "target_size": (
                    entry.size if entry.is_shortcut and not entry.dangling_shortcut else 0
                ),
                "target_mtime_ns": (
                    entry.mtime_ns
                    if entry.is_shortcut and not entry.dangling_shortcut
                    else 0
                ),
            }
        return snap, entries

    def _record_sandbox_snapshot(
        self, meta: Dict[str, Any], snap: Dict[str, Dict[str, Any]]
    ) -> str:
        seq = int(meta.get("change_seq") or 0) + 1
        meta["change_seq"] = seq
        token = f"sbx_{seq}"
        snapshots: Dict[str, Any] = meta.setdefault("change_snapshots", {})
        snapshots[token] = snap
        while len(snapshots) > 16:
            oldest_key = next(iter(snapshots))
            snapshots.pop(oldest_key, None)
        self._save_meta(meta)
        return token

    def get_start_page_token(self) -> str:
        with self._lock:
            meta = self._sync_filesystem_into_meta()
            items = self._deduplicate_same_path_items(meta)
            snap, _ = self._capture_change_snapshot(items)
            return self._record_sandbox_snapshot(meta, snap)

    def list_changes(
        self, page_token: str
    ) -> Tuple[List[ChangeRecord], str]:
        with self._lock:
            meta = self._sync_filesystem_into_meta()
            items = self._deduplicate_same_path_items(meta)
            snapshots: Dict[str, Dict[str, Any]] = meta.setdefault(
                "change_snapshots", {}
            )
            if not page_token or page_token not in snapshots:
                raise GDriveTransportError(
                    f"Invalid or expired sandbox page_token: {page_token}"
                )
            old_snap = snapshots[page_token]
            curr_snap, curr_entries = self._capture_change_snapshot(items)
            records: List[ChangeRecord] = []
            for fid in sorted(old_snap.keys()):
                if fid not in curr_snap:
                    records.append(ChangeRecord(file_id=fid, removed=True))
            for fid in sorted(curr_snap.keys()):
                if fid not in old_snap or curr_snap[fid] != old_snap[fid]:
                    ent = curr_entries[fid]
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
            new_token = self._record_sandbox_snapshot(meta, curr_snap)
            return records, new_token


class GoogleDriveApiTransport(AbstractSyncTransport):
    """
    Pure Python stdlib (urllib.request) client for Google Drive REST API v3.
    Supports OAuth2 token refresh, atomic file operations, and Shortcut target resolution.
    """

    DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
    DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
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
        self._token_lock = threading.RLock()
        self._tls = threading.local()

    def _invalidate_cache_path(self, norm_path: str) -> None:
        if not norm_path:
            self._folder_cache.clear()
            return
        prefix = f"{norm_path}/"
        for k in [k for k in self._folder_cache if k == norm_path or k.startswith(prefix)]:
            self._folder_cache.pop(k, None)

    def _get_https_conn(self, host: str) -> HTTPSConnection:
        conns: Dict[str, HTTPSConnection] = getattr(self._tls, "conns", None)
        if conns is None:
            conns = {}
            self._tls.conns = conns
        conn = conns.get(host)
        if conn is None:
            conn = HTTPSConnection(host, timeout=60)
            conns[host] = conn
        return conn

    def _drop_https_conn(self, host: str) -> None:
        conns: Optional[Dict[str, HTTPSConnection]] = getattr(self._tls, "conns", None)
        if conns and host in conns:
            try:
                conns.pop(host).close()
            except Exception:
                pass

    def _resolve_uri_path(self, raw_uri: str) -> Path:
        if "://" in raw_uri:
            return Path(uri.resolve(raw_uri)).resolve()
        return Path(raw_uri).resolve()

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
                self.OAUTH_TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    refreshed = json.loads(resp.read().decode("utf-8"))
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
        for attempt in range(4):
            try:
                conn = self._get_https_conn(host)
                conn.request(method, path_with_query, body=body, headers=req_headers)
                resp = conn.getresponse()
                raw = resp.read()
                status = resp.status
                if 200 <= status < 300:
                    return json.loads(raw.decode("utf-8")) if raw else {}
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
                    continue
                raise GDriveTransportError(f"Drive API request failed: {exc}") from exc
        raise GDriveTransportError("Drive API request exhausted retries.")

    @staticmethod
    def _parse_rfc3339_ns(ts_str: str) -> int:
        if not ts_str:
            return 0
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1_000_000_000)
        except Exception:
            return 0

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
        mtime_ns = self._parse_rfc3339_ns(str(item.get("modifiedTime") or ""))

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
                    mtime_ns = self._parse_rfc3339_ns(
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
        target_ids = {
            str((it.get("shortcutDetails") or {}).get("targetId") or "")
            for it in raw_items
            if it.get("mimeType") == SHORTCUT_MIME_TYPE
        }
        target_ids.discard("")
        resolved: Dict[str, Dict[str, Any]] = {}
        for tid in target_ids:
            try:
                url = (
                    f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(tid)}"
                    f"?fields={urllib.parse.quote(self.FILE_FIELDS)}&supportsAllDrives=true"
                )
                obj = self._request_json("GET", url)
                if obj and not obj.get("trashed"):
                    resolved[tid] = obj
            except GDriveFileNotFoundError:
                continue
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
            if idx < len(parts) - 1 and curr_rel in self._folder_cache:
                curr_parent = self._folder_cache[curr_rel].file_id
                continue
            children = self._list_children_raw(curr_parent)
            matches = [c for c in children if c.get("name") == part]
            if not matches:
                return None
            matches.sort(
                key=lambda c: self._parse_rfc3339_ns(str(c.get("modifiedTime") or "")),
                reverse=True,
            )
            chosen = matches[0]
            last_item = chosen
            if chosen.get("mimeType") == FOLDER_MIME_TYPE:
                self._folder_cache[curr_rel] = self._raw_to_entry(chosen, curr_rel)
            if idx < len(parts) - 1:
                if chosen.get("mimeType") != FOLDER_MIME_TYPE:
                    return None
                curr_parent = str(chosen["id"])
        assert last_item is not None
        return str(last_item["id"]), last_item

    def list_files(
        self, remote_path: str = "", recursive: bool = False
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
                    key=lambda c: self._parse_rfc3339_ns(str(c.get("modifiedTime") or "")),
                    reverse=True,
                )
                winner = group[0]
                for loser in group[1:]:
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
                        except Exception:
                            pass
                child_rel = f"{curr_prefix}/{name}".strip("/") if curr_prefix else name
                collected_raw.append((child_rel, winner))
                if winner.get("mimeType") == FOLDER_MIME_TYPE:
                    self._folder_cache[child_rel] = self._raw_to_entry(winner, child_rel)
                    if recursive:
                        _walk(str(winner["id"]), child_rel)

        _walk(folder_id, norm)
        if recursive:
            self._scanned_prefixes.add(norm)
        target_map = self._resolve_shortcut_targets([it for _, it in collected_raw])
        entries = [
            self._raw_to_entry(it, rel_p, target_map) for rel_p, it in collected_raw
        ]
        entries.sort(key=lambda e: e.rel_path)
        return entries

    def get_entry(self, remote_path: str) -> Optional[RemoteEntry]:
        norm = normalize_remote_rel_path(remote_path)
        if norm in self._folder_cache:
            return self._folder_cache[norm]
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
        if norm in self._folder_cache:
            return self._folder_cache[norm]
        parts = norm.split("/")
        curr_parent = self.root_folder_id
        curr_rel = ""
        last_entry: Optional[RemoteEntry] = None
        for part in parts:
            curr_rel = f"{curr_rel}/{part}".strip("/") if curr_rel else part
            if curr_rel in self._folder_cache:
                last_entry = self._folder_cache[curr_rel]
                curr_parent = last_entry.file_id
                continue
            children = self._list_children_raw(curr_parent)
            folder_matches = [
                c
                for c in children
                if c.get("name") == part and c.get("mimeType") == FOLDER_MIME_TYPE
            ]
            if folder_matches:
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
            self._folder_cache[curr_rel] = last_entry
        assert last_entry is not None
        return last_entry

    def _is_under_scanned_prefix(self, norm_path: str) -> bool:
        for pfx in self._scanned_prefixes:
            if not pfx or norm_path.startswith(f"{pfx}/"):
                return True
        return False

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        in_place_file_id: Optional[str] = None,
    ) -> RemoteEntry:
        src = Path(local_path).resolve()
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
            updated = self._request_json(
                "PATCH",
                url,
                body=file_bytes,
                headers={"Content-Type": mime},
            )
            return self._raw_to_entry(updated, norm)

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

    def download_file(self, remote_path: str, local_path: Path) -> RemoteEntry:
        norm = normalize_remote_rel_path(remote_path)
        entry = self.get_entry(norm)
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
        token = self._ensure_access_token()
        url = (
            f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(download_fid)}"
            "?alt=media&supportsAllDrives=true"
        )
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"}, method="GET"
        )
        dst = Path(local_path).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp_dst = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp, open(
                tmp_dst, "wb"
            ) as out_f:
                shutil.copyfileobj(resp, out_f)
            os.replace(tmp_dst, dst)
        except Exception as exc:
            if tmp_dst.exists():
                tmp_dst.unlink(missing_ok=True)
            raise GDriveTransportError(f"Failed to download '{norm}': {exc}") from exc
        return entry

    def trash_file(self, remote_path: str) -> bool:
        """
        Move remote_path into Google Drive's native 30-day Trash (trashed=true) without creating a .trash/ folder.
        """
        norm = normalize_remote_rel_path(remote_path)
        entry = self.get_entry(norm)
        if entry is None:
            return False
        params = urllib.parse.urlencode(
            {
                "fields": self.FILE_FIELDS,
                "supportsAllDrives": "true",
            }
        )
        url = f"{self.DRIVE_API_BASE}/files/{urllib.parse.quote(entry.file_id)}?{params}"
        self._request_json(
            "PATCH",
            url,
            body=json.dumps({"trashed": True}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        self._invalidate_cache_path(norm)
        return True

    def move_file(self, src_remote_path: str, dst_remote_path: str) -> RemoteEntry:
        src_norm = normalize_remote_rel_path(src_remote_path)
        dst_norm = normalize_remote_rel_path(dst_remote_path)
        entry = self.get_entry(src_norm)
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
                self._folder_cache = {
                    k: v for k, v in self._folder_cache.items() if v.file_id != fid
                }
            else:
                ent = self._raw_to_entry(file_obj, "", target_map)
                if ent.is_dir:
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


OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_DEFAULT_SCOPE = "https://www.googleapis.com/auth/drive"


def load_oauth_client_config(cred_path: Path) -> Tuple[str, str]:
    """
    Parse Google OAuth 2.0 Client ID JSON ('installed' or 'web' format) and return (client_id, client_secret).
    """
    if not cred_path.is_file():
        raise GDriveConfigError(
            f"OAuth2 client credentials file not found at '{cred_path.as_posix()}'.\n"
            "Please place your downloaded Google Cloud OAuth 2.0 Client ID JSON at this path."
        )
    try:
        raw = json.loads(cred_path.read_text(encoding="utf-8"))
        try:
            os.chmod(cred_path, 0o600)
        except OSError:
            pass
    except Exception as exc:
        raise GDriveConfigError(
            f"Invalid JSON in '{cred_path.as_posix()}': {exc}"
        ) from exc

    block = raw.get("installed") or raw.get("web") or raw
    if not isinstance(block, dict):
        raise GDriveConfigError(
            f"Unrecognized OAuth2 client credentials structure in '{cred_path.as_posix()}'."
        )
    client_id = str(block.get("client_id") or "").strip()
    client_secret = str(block.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise GDriveConfigError(
            f"Missing 'client_id' or 'client_secret' in '{cred_path.as_posix()}'."
        )
    return client_id, client_secret


def build_oauth_authorize_url(
    client_id: str,
    redirect_uri: str,
    scope: str = DRIVE_DEFAULT_SCOPE,
    state: str = "",
) -> str:
    """Build the Google OAuth 2.0 authorization URL for offline refresh_token access."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def extract_code_from_input(raw_code_or_url: str) -> str:
    """
    Accept either a raw authorization code or a full redirect URL (e.g. http://127.0.0.1:8080/?code=4/0A...&scope=...)
    and extract the 'code' value.
    """
    val = raw_code_or_url.strip()
    if val.startswith(("http://", "https://", "localhost", "127.0.0.1")) or "?code=" in val or "&code=" in val:
        parsed = urllib.parse.urlparse(val if "://" in val else f"http://{val}")
        qs = urllib.parse.parse_qs(parsed.query)
        codes = qs.get("code") or []
        if codes:
            return str(codes[0]).strip()
    return val


def exchange_oauth_code_for_token(
    client_id: str,
    client_secret: str,
    code_or_url: str,
    redirect_uri: str,
    token_path: Path,
) -> Dict[str, Any]:
    """
    Exchange an OAuth2 authorization code for access_token + refresh_token and persist atomically to token_path.
    """
    code = extract_code_from_input(code_or_url)
    if not code:
        raise GDriveTransportError("Authorization code is empty.")

    payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
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
            token_resp = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise GDriveTransportError(
            f"OAuth2 token exchange failed (HTTP {exc.code}): {err_body}"
        ) from exc
    except Exception as exc:
        raise GDriveTransportError(f"OAuth2 token exchange failed: {exc}") from exc

    existing_refresh = ""
    if token_path.is_file():
        try:
            old_data = json.loads(token_path.read_text(encoding="utf-8"))
            existing_refresh = str(old_data.get("refresh_token") or "")
        except Exception:
            existing_refresh = ""

    expires_in = float(token_resp.get("expires_in", 3600))
    stored_token: Dict[str, Any] = {
        "access_token": str(token_resp["access_token"]),
        "refresh_token": str(token_resp.get("refresh_token") or existing_refresh),
        "token_type": str(token_resp.get("token_type", "Bearer")),
        "scope": str(token_resp.get("scope", DRIVE_DEFAULT_SCOPE)),
        "expiry_epoch": time.time() + expires_in,
        "client_id": client_id,
    }
    token_path.parent.mkdir(parents=True, exist_ok=True)
    vfs.write_json(token_path, stored_token, indent=2, encoding="utf-8", atomic=True)
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
    return stored_token


def run_oauth_loopback_flow(
    cred_path: Path,
    token_path: Path,
    port: int = 0,
    open_browser: bool = True,
    timeout_sec: float = 180.0,
) -> Dict[str, Any]:
    """
    Start a temporary localhost HTTP loopback listener on 127.0.0.1:<port>, print the Google OAuth2
    consent URL, and wait for the browser redirect (or allow fallback via --code).
    """
    client_id, client_secret = load_oauth_client_config(cred_path)
    captured: Dict[str, str] = {}

    class _OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "code" in qs and qs["code"]:
                captured["code"] = qs["code"][0]
                body = (
                    "<html><body style='font-family:sans-serif;padding:2rem;'>"
                    "<h2>YS-Codebase Google Drive Authorization Successful</h2>"
                    "<p>You may close this tab and return to your terminal.</p>"
                    "</body></html>"
                ).encode("utf-8")
                self.send_response(200)
            else:
                err = (qs.get("error") or ["unknown_error"])[0]
                captured["error"] = err
                safe_err = html.escape(str(err))
                body = (
                    f"<html><body><h2>Authorization Failed: {safe_err}</h2></body></html>"
                ).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    actual_port = server.server_port
    redirect_uri = f"http://127.0.0.1:{actual_port}"
    auth_url = build_oauth_authorize_url(client_id, redirect_uri)

    print(
        f"\n[gdrive-support:auth] Open the following URL in your browser to authorize:\n\n  {auth_url}\n"
    )
    print(
        f"[gdrive-support:auth] Listening on {redirect_uri} (timeout={int(timeout_sec)}s)...\n"
        f"  (Tip: In a headless container, if your browser redirects to {redirect_uri}/?code=... and cannot connect,\n"
        f"   copy that full URL or the 'code' parameter and run:\n"
        f"   python yscb.py gdrive auth --code=\"<CODE_OR_REDIRECT_URL>\" --port={actual_port})\n",
        flush=True,
    )
    if open_browser:
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

    server.timeout = 1.0
    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline and "code" not in captured and "error" not in captured:
            server.handle_request()
    finally:
        server.server_close()

    if "error" in captured:
        raise GDriveTransportError(f"OAuth2 authorization denied: {captured['error']}")
    if "code" not in captured:
        raise GDriveTransportError(
            "Timed out waiting for OAuth2 callback on loopback server."
        )

    return exchange_oauth_code_for_token(
        client_id=client_id,
        client_secret=client_secret,
        code_or_url=captured["code"],
        redirect_uri=redirect_uri,
        token_path=token_path,
    )


def create_transport(
    config: GDriveConfig, sandbox_dir: Optional[str] = None
) -> AbstractSyncTransport:
    """
    Factory returning LocalSandboxTransport when sandbox_dir (or config.sandbox_dir) is provided,
    otherwise returning GoogleDriveApiTransport.
    """
    effective_sandbox = (sandbox_dir or config.sandbox_dir or "").strip()
    if effective_sandbox:
        resolved = (
            Path(uri.resolve(effective_sandbox)).resolve()
            if "://" in effective_sandbox
            else Path(effective_sandbox).resolve()
        )
        return LocalSandboxTransport(resolved)
    return GoogleDriveApiTransport(config)
