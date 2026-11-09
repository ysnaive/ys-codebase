"""
LocalSandboxTransport: 100% offline filesystem-backed simulation of Google Drive REST API v3 semantics.
"""
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core import vfs

from .config import (
    GDriveFileNotFoundError,
    GDrivePathError,
    GDriveTransportError,
    GDriveUnsupportedMimeError,
    normalize_remote_rel_path,
)
from .transport import (
    FOLDER_MIME_TYPE,
    SANDBOX_META_FILENAME,
    SHORTCUT_MIME_TYPE,
    AbstractSyncTransport,
    ChangeRecord,
    RemoteEntry,
    is_unsupported_google_workspace_mime,
)


def _compute_md5_and_size(file_path: Path) -> Tuple[str, int]:
    """Compute (md5_hex, size_bytes) for a sandbox physical file without redundant SHA-256."""
    md5_hasher = hashlib.md5()
    total_size = 0
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            total_size += len(chunk)
            md5_hasher.update(chunk)
    return md5_hasher.hexdigest(), total_size


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
                except (OSError, ValueError):
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

    def _sync_filesystem_into_meta(self, *, persist: bool = True) -> Dict[str, Any]:
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
                    md5_hex, sz = _compute_md5_and_size(abs_f)
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

        if changed and persist:
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
                st = phys.stat()
                cur_mtime_ns = int(st.st_mtime_ns)
                cur_size = int(st.st_size)
                if cur_mtime_ns != mtime_ns or cur_size != size or not md5:
                    md5, size = _compute_md5_and_size(phys)
                    mtime_ns = cur_mtime_ns
                    info["md5"] = md5
                    info["size"] = size
                    info["mtime_ns"] = mtime_ns

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
                        st = target_phys.stat()
                        cur_mtime_ns = int(st.st_mtime_ns)
                        cur_size = int(st.st_size)
                        t_mtime_ns = int(target_info.get("mtime_ns") or 0)
                        t_size = int(target_info.get("size") or -1)
                        t_md5 = str(target_info.get("md5") or "")
                        if cur_mtime_ns == t_mtime_ns and cur_size == t_size and t_md5:
                            md5 = t_md5
                            size = cur_size
                            mtime_ns = cur_mtime_ns
                        else:
                            md5, size = _compute_md5_and_size(target_phys)
                            mtime_ns = cur_mtime_ns
                            target_info["md5"] = md5
                            target_info["size"] = size
                            target_info["mtime_ns"] = mtime_ns
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
                if bool(older.get("is_dir")) or older.get("mime_type") == FOLDER_MIME_TYPE:
                    continue
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
        self,
        remote_path: str = "",
        recursive: bool = False,
        *,
        deduplicate: bool = True,
    ) -> List[RemoteEntry]:
        norm_prefix = normalize_remote_rel_path(remote_path)
        with self._lock:
            meta = self._sync_filesystem_into_meta(persist=deduplicate)
            if deduplicate:
                items = self._deduplicate_same_path_items(meta)
            else:
                items = meta.get("items", {})

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
            meta = self._sync_filesystem_into_meta(persist=False)
            items = meta.get("items", {})
            candidates: List[Dict[str, Any]] = []
            for info in items.values():
                if info.get("rel_path") == norm:
                    if not info.get("is_shortcut") and not is_unsupported_google_workspace_mime(
                        str(info.get("mime_type") or "")
                    ):
                        if not self._phys_path(norm).exists():
                            continue
                    candidates.append(info)
            if not candidates:
                return None
            candidates.sort(
                key=lambda x: (int(x.get("mtime_ns") or 0), str(x.get("file_id") or "")),
                reverse=True,
            )
            return self._build_entry(candidates[0], items)

    def get_entry_by_id(self, file_id: str) -> Optional[RemoteEntry]:
        with self._lock:
            meta = self._sync_filesystem_into_meta(persist=False)
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

        with self._lock:
            dst = self._phys_path(norm)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            md5_hex, sz = _compute_md5_and_size(dst)
            mtime_ns = int(dst.stat().st_mtime_ns)
            guessed_mime, _ = mimetypes.guess_type(dst.name)
            mime = guessed_mime or "application/octet-stream"

            meta = self._ensure_meta()
            items = meta["items"]

            target_fid: Optional[str] = None
            if in_place_file_id and in_place_file_id in items:
                target_fid = in_place_file_id
            else:
                stale_shortcut_fids: List[str] = []
                for fid, info in items.items():
                    if info.get("rel_path") == norm:
                        if info.get("is_shortcut"):
                            stale_shortcut_fids.append(fid)
                        elif target_fid is None:
                            target_fid = fid
                for sc_fid in stale_shortcut_fids:
                    items.pop(sc_fid, None)

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

    def download_file(
        self,
        remote_path: str,
        local_path: Path,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry:
        norm = normalize_remote_rel_path(remote_path)
        entry = (
            entry_hint
            if (entry_hint is not None and entry_hint.rel_path == norm)
            else self.get_entry(norm)
        )
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

        with self._lock:
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

    def trash_file(
        self, remote_path: str, file_id: Optional[str] = None
    ) -> bool:
        norm = normalize_remote_rel_path(remote_path)
        if not norm and not file_id:
            raise GDrivePathError("Cannot trash root directory.")
        with self._lock:
            entry: Optional[RemoteEntry] = None
            if file_id:
                entry = self.get_entry_by_id(file_id)
            if entry is None and norm:
                entry = self.get_entry(norm)
            if entry is None:
                return False

            effective_norm = norm or entry.rel_path
            if not effective_norm:
                return False

            self.mkdir(".trash")
            meta = self._ensure_meta()
            items = meta["items"]
            info = items.get(entry.file_id)
            if not info:
                return False

            trash_rel = f".trash/{entry.file_id}_{entry.name}"
            if not entry.is_shortcut and not is_unsupported_google_workspace_mime(entry.mime_type):
                src_phys = self._phys_path(effective_norm)
                dst_phys = self._phys_path(trash_rel)
                dst_phys.parent.mkdir(parents=True, exist_ok=True)
                if src_phys.exists():
                    shutil.move(str(src_phys), str(dst_phys))

            if entry.is_dir:
                prefix = f"{effective_norm}/"
                for child_info in items.values():
                    c_rel = str(child_info.get("rel_path") or "")
                    if c_rel.startswith(prefix):
                        child_info["rel_path"] = f"{trash_rel}/{c_rel[len(prefix):]}"

            info["rel_path"] = trash_rel
            info["name"] = Path(trash_rel).name
            self._save_meta(meta)
            return True

    def move_file(
        self,
        src_remote_path: str,
        dst_remote_path: str,
        entry_hint: Optional[RemoteEntry] = None,
    ) -> RemoteEntry:
        src_norm = normalize_remote_rel_path(src_remote_path)
        dst_norm = normalize_remote_rel_path(dst_remote_path)
        if not src_norm or not dst_norm:
            raise GDrivePathError("move_file requires non-empty src and dst paths.")

        with self._lock:
            entry = (
                entry_hint
                if (entry_hint is not None and entry_hint.rel_path == src_norm)
                else self.get_entry(src_norm)
            )
            if entry is None:
                raise GDriveFileNotFoundError(f"Source path not found: '{src_norm}'")

            dst_parent = Path(dst_norm).parent.as_posix()
            if dst_parent and dst_parent != ".":
                self.mkdir(dst_parent)

            meta = self._ensure_meta()
            items = meta["items"]
            src_prefix = f"{src_norm}/"
            dst_prefix = f"{dst_norm}/"
            for fid, existing in list(items.items()):
                if fid == entry.file_id:
                    continue
                ex_rel = str(existing.get("rel_path") or "")
                if ex_rel == dst_norm or (entry.is_dir and ex_rel.startswith(dst_prefix)):
                    del items[fid]

            info = items.get(entry.file_id)
            if info is None:
                raise GDriveFileNotFoundError(f"Source path not found: '{src_norm}'")
            if not entry.is_shortcut and not is_unsupported_google_workspace_mime(entry.mime_type):
                src_phys = self._phys_path(src_norm)
                dst_phys = self._phys_path(dst_norm)
                dst_phys.parent.mkdir(parents=True, exist_ok=True)
                if src_phys.exists() and src_phys != dst_phys:
                    if dst_phys.is_dir():
                        shutil.rmtree(dst_phys)
                    elif dst_phys.exists():
                        dst_phys.unlink()
                    shutil.move(str(src_phys), str(dst_phys))

            if entry.is_dir:
                for child_info in items.values():
                    c_rel = str(child_info.get("rel_path") or "")
                    if c_rel.startswith(src_prefix):
                        child_info["rel_path"] = f"{dst_norm}/{c_rel[len(src_prefix):]}"

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
