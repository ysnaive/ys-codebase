"""Immutable local package mirror store (.mirror/<mod>/<ver>.zip and offline index.json cache)."""

from __future__ import annotations

import os
import stat
from typing import Optional

from core.filesystem.fs import (
    assert_no_symlink_raw_path,
    atomic_write_json,
    has_symlink_raw_path,
    is_symlink_or_reparse,
    read_json_dict,
    resolve_contained_subpath,
    try_resolve_contained_subpath,
)
from core.foundation.primitives import HostPath, ModuleId, SemVer4
from core.packaging.installer.models import (
    RemoteModuleIndex,
    ins_assert_not_reserved_module_id,
    ins_encode_remote_index,
    ins_parse_remote_index,
    ins_verify_zip_archive,
)


class MirrorStore:
    """Immutable local package mirror (.mirror/<mod>/<ver>.zip and offline index.json cache)."""

    def __init__(self, *, yscb_root: HostPath) -> None:
        if not isinstance(yscb_root, HostPath):
            raise ValueError(f"MirrorStore.yscb_root must be HostPath, got {yscb_root!r}")
        assert_no_symlink_raw_path(str(yscb_root))
        self._yscb_root = yscb_root
        self._mirror_root = resolve_contained_subpath(yscb_root, ".mirror")

    def has_package(self, module_id: ModuleId, version: SemVer4) -> bool:
        pkg_path = self.get_package_path(module_id, version)
        raw_path = str(pkg_path)
        if is_symlink_or_reparse(raw_path) or has_symlink_raw_path(raw_path):
            return False
        try:
            st = os.lstat(raw_path)
        except OSError:
            return False
        return stat.S_ISREG(st.st_mode)

    def get_package_path(self, module_id: ModuleId, version: SemVer4) -> HostPath:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"MirrorStore.get_package_path requires ModuleId, got {module_id!r}")
        if not isinstance(version, SemVer4):
            raise ValueError(f"MirrorStore.get_package_path requires SemVer4, got {version!r}")
        ins_assert_not_reserved_module_id(module_id, label="MirrorStore.get_package_path module_id")
        return resolve_contained_subpath(self._mirror_root, module_id.value, f"{version}.zip")

    def verify_zip_integrity(
        self,
        zip_path: HostPath,
        *,
        expected_sha256: Optional[str] = None,
        ignore_sha256: bool = False,
    ) -> None:
        ins_verify_zip_archive(
            zip_path,
            expected_sha256=expected_sha256,
            ignore_sha256=ignore_sha256,
        )

    def save_index_cache(self, index: RemoteModuleIndex) -> None:
        if not isinstance(index, RemoteModuleIndex):
            raise ValueError(f"MirrorStore.save_index_cache requires RemoteModuleIndex, got {index!r}")
        ins_assert_not_reserved_module_id(index.module_id, label="MirrorStore.save_index_cache module_id")
        idx_path = resolve_contained_subpath(self._mirror_root, index.module_id.value, "index.json")
        atomic_write_json(idx_path, ins_encode_remote_index(index))

    def load_index_cache(self, module_id: ModuleId) -> Optional[RemoteModuleIndex]:
        if not isinstance(module_id, ModuleId):
            raise ValueError(f"MirrorStore.load_index_cache requires ModuleId, got {module_id!r}")
        ins_assert_not_reserved_module_id(module_id, label="MirrorStore.load_index_cache module_id")
        idx_path = try_resolve_contained_subpath(self._mirror_root, module_id.value, "index.json")
        if idx_path is None:
            return None
        raw_doc = read_json_dict(idx_path)
        if raw_doc is None:
            return None
        return ins_parse_remote_index(raw_doc, module_id)
