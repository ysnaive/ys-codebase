"""
YS-Codebase Unified Virtual File System (VFS).
100% Python 標準庫，生態系唯一微內核核心檔案存取體系。
提供插槽化後端、跨平台路徑正規化、同目錄原子寫入與沙盒防逃逸安全邊界。
"""

from core.vfs.base import VFSBackend
from core.vfs.os_backend import OSBackend
from core.vfs.vfs import VFS
from core.vfs.path import VirtualPath

# 全域預設單例
vfs = VFS(default_backend=OSBackend())

# 便捷頂層函式委託
read_text = vfs.read_text
write_text = vfs.write_text
read_bytes = vfs.read_bytes
write_bytes = vfs.write_bytes
read_json = vfs.read_json
write_json = vfs.write_json
exists = vfs.exists
is_file = vfs.is_file
is_dir = vfs.is_dir
listdir = vfs.listdir
makedirs = vfs.makedirs
remove = vfs.remove
rmtree = vfs.rmtree
copy = vfs.copy
move = vfs.move
atomic_write = vfs.atomic_write
open_file = vfs.open
assert_safe_path = vfs.assert_safe_path
path = vfs.path

__all__ = [
    "VFS",
    "VFSBackend",
    "OSBackend",
    "VirtualPath",
    "vfs",
    "read_text",
    "write_text",
    "read_bytes",
    "write_bytes",
    "read_json",
    "write_json",
    "exists",
    "is_file",
    "is_dir",
    "listdir",
    "makedirs",
    "remove",
    "rmtree",
    "copy",
    "move",
    "atomic_write",
    "open_file",
    "assert_safe_path",
    "path",
]
