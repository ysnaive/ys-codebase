"""
YS-Codebase VFS 單元測試與邊界安全測試集。
測試覆蓋 OSBackend CRUD、同目錄原子寫入、沙盒防逃逸、VirtualPath 物件導向操作與 core.uri 相容轉發。
"""

import os
import json
import shutil
import tempfile
import unittest

from dev.testing.case import YSCBTestCase
from core import vfs, uri
from core.vfs import VFS, OSBackend, VirtualPath


class TestVFS(YSCBTestCase):
    """VFS 模組核心單元與邊界測試套件。"""

    def setUp(self):
        super().setUp()
        # 建立本測試專屬之隔離暫存目錄
        self.test_dir = tempfile.mkdtemp(prefix="yscb_vfs_test_")
        self.backend = OSBackend(root_dir=self.test_dir)
        self.custom_vfs = VFS(default_backend=self.backend)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
        super().tearDown()

    def test_os_backend_crud(self):
        """FT-01: OSBackend 基礎 CRUD 操作 (text, bytes, json, exists, listdir, copy, move, remove)。"""
        # 1. 寫入與讀取純文字
        txt_path = os.path.join(self.test_dir, "hello.txt")
        self.backend.write_text(txt_path, "Hello VFS World")
        self.assertTrue(self.backend.exists(txt_path))
        self.assertTrue(self.backend.is_file(txt_path))
        self.assertFalse(self.backend.is_dir(txt_path))
        self.assertEqual(self.backend.read_text(txt_path), "Hello VFS World")

        # 2. 寫入與讀取二進位
        bin_path = os.path.join(self.test_dir, "data.bin")
        self.backend.write_bytes(bin_path, b"\x00\x01\x02\xFF")
        self.assertEqual(self.backend.read_bytes(bin_path), b"\x00\x01\x02\xFF")

        # 3. 寫入與讀取 JSON
        json_path = os.path.join(self.test_dir, "config.json")
        sample_data = {"key": "value", "items": [1, 2, 3]}
        self.backend.write_json(json_path, sample_data)
        self.assertEqual(self.backend.read_json(json_path), sample_data)

        # 4. 目錄建立與列舉
        sub_dir = os.path.join(self.test_dir, "subdir")
        self.backend.makedirs(sub_dir)
        self.assertTrue(self.backend.is_dir(sub_dir))
        items = self.backend.listdir(self.test_dir)
        self.assertIn("hello.txt", items)
        self.assertIn("data.bin", items)
        self.assertIn("config.json", items)
        self.assertIn("subdir", items)

        # 5. 複製與移動
        copied_path = os.path.join(self.test_dir, "hello_copy.txt")
        self.backend.copy(txt_path, copied_path)
        self.assertTrue(self.backend.exists(copied_path))
        self.assertEqual(self.backend.read_text(copied_path), "Hello VFS World")

        moved_path = os.path.join(sub_dir, "hello_moved.txt")
        self.backend.move(copied_path, moved_path)
        self.assertFalse(self.backend.exists(copied_path))
        self.assertTrue(self.backend.exists(moved_path))

        # 6. 刪除
        self.backend.remove(moved_path)
        self.assertFalse(self.backend.exists(moved_path))
        self.backend.remove(sub_dir)
        self.assertFalse(self.backend.exists(sub_dir))
        self.mark_passed()

    def test_atomic_write(self):
        """FT-02: 驗證原子寫入確保寫入完成後原子取代且同分區無 EXDEV。"""
        target_file = os.path.join(self.test_dir, "atomic_test.txt")
        self.backend.write_text(target_file, "Initial State")

        # 使用 atomic_write 上下文覆寫
        with self.backend.atomic_write(target_file, mode="w") as f:
            f.write("Updated Atomic State")

        self.assertEqual(self.backend.read_text(target_file), "Updated Atomic State")
        self.mark_passed()

    def test_atomic_write_failure_cleanup(self):
        """ET-02: 驗證原子寫入過程中異常時臨時檔安全清理且目標檔保持完整。"""
        target_file = os.path.join(self.test_dir, "atomic_fail.txt")
        self.backend.write_text(target_file, "Pre-existing Content")

        # 模擬寫入中拋出異常
        try:
            with self.backend.atomic_write(target_file, mode="w") as f:
                f.write("Corrupted Half Written Content")
                raise RuntimeError("Simulated crash during write")
        except RuntimeError:
            pass

        # 斷言原檔案未被覆蓋破壞
        self.assertEqual(self.backend.read_text(target_file), "Pre-existing Content")

        # 斷言目錄下無殘留之 .tmp 暫存檔
        tmp_files = [f for f in os.listdir(self.test_dir) if ".tmp." in f]
        self.assertEqual(tmp_files, [], "Temporary files must be cleaned up on failure.")
        self.mark_passed()

    def test_auto_makedirs(self):
        """ET-03: 驗證目標路徑父目錄不存在時寫入能自動遞迴建立目錄。"""
        nested_file = os.path.join(self.test_dir, "deep", "nested", "path", "test.txt")
        self.backend.write_text(nested_file, "Auto Created Directory Content")
        self.assertTrue(self.backend.exists(nested_file))
        self.assertEqual(self.backend.read_text(nested_file), "Auto Created Directory Content")
        self.mark_passed()

    def test_safe_path_escape(self):
        """ET-01: 驗證 assert_safe_path 邊界防逃逸 (偵測 ../ 逃逸拋出 PermissionError)。"""
        outside_path = os.path.join(self.test_dir, "..", "outside_target.txt")
        with self.assertRaises(PermissionError):
            self.backend.assert_safe_path(outside_path)

        with self.assertRaises(PermissionError):
            self.backend.write_text(outside_path, "Exploit")
        self.mark_passed()

    def test_vfs_uri_resolution(self):
        """FT-03: 驗證 VFS 核心中樞透過 core.uri.resolve 支援語意 URI。"""
        # 使用 cache:// 協議測試
        cache_test_uri = "cache://vfs_test/demo.txt"
        vfs.write_text(cache_test_uri, "VFS URI Integration Test")
        self.assertTrue(vfs.exists(cache_test_uri))
        self.assertEqual(vfs.read_text(cache_test_uri), "VFS URI Integration Test")
        vfs.remove(cache_test_uri)
        self.assertFalse(vfs.exists(cache_test_uri))
        self.mark_passed()

    def test_virtual_path(self):
        """FT-04: 驗證 VirtualPath 物件導向介面與 / 路徑拼接。"""
        base_vp = VirtualPath(self.test_dir, vfs_instance=self.custom_vfs)
        file_vp = base_vp / "notes" / "todo.txt"

        self.assertEqual(file_vp.name, "todo.txt")
        self.assertEqual(file_vp.suffix, ".txt")

        # 寫入與讀取
        file_vp.write_text("1. Build VFS\n2. Test All")
        self.assertTrue(file_vp.exists())
        self.assertTrue(file_vp.is_file())
        self.assertEqual(file_vp.read_text(), "1. Build VFS\n2. Test All")

        # 刪除
        file_vp.unlink()
        self.assertFalse(file_vp.exists())

        # URI 形式 VirtualPath
        uri_vp = VirtualPath("cache://vfs_vp_test") / "sub" / "data.json"
        self.assertEqual(str(uri_vp), "cache://vfs_vp_test/sub/data.json")
        uri_vp.write_json({"status": "ok"})
        self.assertTrue(uri_vp.exists())
        self.assertEqual(uri_vp.read_json(), {"status": "ok"})
        uri_vp.unlink()
        self.mark_passed()

    def test_uri_compatibility_delegation(self):
        """FT-05: 驗證 core.uri 既有 IO helpers 向上相容無損轉發至 core.vfs。"""
        compat_file = os.path.join(self.test_dir, "compat.txt")
        uri.write_text(compat_file, "Compatible Content")
        self.assertTrue(uri.exists(compat_file))
        self.assertTrue(uri.isfile(compat_file))
        self.assertEqual(uri.read_text(compat_file), "Compatible Content")

        json_compat = os.path.join(self.test_dir, "compat.json")
        uri.write_json(json_compat, {"compat": True})
        self.assertEqual(uri.read_json(json_compat), {"compat": True})

        uri.remove(compat_file)
        self.assertFalse(uri.exists(compat_file))
        self.mark_passed()

    def test_cross_backend_protection(self):
        """FT-07: 驗證 VFS.copy 與 VFS.move 跨不同 Backend 時拋出 NotImplementedError。"""
        from core.vfs import VFS
        from core.vfs.os_backend import OSBackend

        custom_vfs = VFS()
        dummy = OSBackend()
        custom_vfs.register_backend("dummy://", dummy)

        src_path = os.path.join(self.test_dir, "test_src.txt")
        custom_vfs.write_text(src_path, "hello")

        with self.assertRaises(NotImplementedError):
            custom_vfs.copy(src_path, "dummy://target.txt")

        with self.assertRaises(NotImplementedError):
            custom_vfs.move(src_path, "dummy://target.txt")
        self.mark_passed()
