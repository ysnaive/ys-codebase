"""
Unit tests for core.symbols (code.func:// protocol).
100% standard library unittest.
"""

import sys
import unittest

from core import uri, vfs
from core.symbols import (
    _RESOLVED_CALLABLE_CACHE,
    InvalidSymbolURIError,
    SymbolNotFoundError,
    clear_callable_cache,
    parse_code_func_uri,
    resolve_callable,
)
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.ENV)
class TestSymbolsProtocol(YSCBTestCase):
    """測試 code.func:// 協議解析與 Callable 加載。"""

    def setUp(self):
        super().setUp()
        clear_callable_cache()

    def test_parse_code_func_uri_success(self):
        """驗證標準 code.func:// 語法解析。"""
        mod, sub, fn = parse_code_func_uri("code.func://agents-workflow/providers:get_dynamic_context_map")
        self.assertEqual(mod, "agents-workflow")
        self.assertEqual(sub, "providers")
        self.assertEqual(fn, "get_dynamic_context_map")

        # 支援 .py 後綴與無 subpath
        mod2, sub2, fn2 = parse_code_func_uri("code.func://core/symbols.py:resolve_callable")
        self.assertEqual(mod2, "core")
        self.assertEqual(sub2, "symbols")
        self.assertEqual(fn2, "resolve_callable")

        mod3, sub3, fn3 = parse_code_func_uri("code.func://my-mod:run")
        self.assertEqual((mod3, sub3, fn3), ("my-mod", "my-mod", "run"))
        self.mark_passed()

    def test_parse_code_func_uri_invalid(self):
        """驗證無效 URI 格式防禦 (EC-01)。"""
        # 非字串
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri(123)  # type: ignore[arg-type]

        # 錯誤協議前綴
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("http://agents-workflow/providers:func")

        # 空 body 或空模組名
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("code.func://")
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("code.func:///:fn")

        # 缺少 ':' 符號
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("code.func://agents-workflow/providers")

        # 空函式名
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("code.func://agents-workflow/providers:")
        self.mark_passed()

    def test_resolve_callable_package_import(self):
        """驗證透過已加載 package / sys.modules 解析 Callable。"""
        fn = resolve_callable("code.func://core/symbols:parse_code_func_uri")
        self.assertTrue(callable(fn))
        self.assertEqual(fn, parse_code_func_uri)

        # 驗證快取命中
        fn_cached = resolve_callable("code.func://core/symbols:parse_code_func_uri")
        self.assertIs(fn, fn_cached)
        self.mark_passed()

    def test_resolve_callable_not_found(self):
        """驗證模組不存在或函式不存在防禦 (EC-02)。"""
        # 不存在的模組
        with self.assertRaises(SymbolNotFoundError):
            resolve_callable("code.func://non_existent_pkg_xyz/foo:bar", use_cache=False)

        # 模組存在但函式不存在
        with self.assertRaises(SymbolNotFoundError):
            resolve_callable("code.func://core/symbols:non_existent_func_xyz", use_cache=False)
        self.mark_passed()

    def test_resolve_callable_cache_keyed_by_yscb_root(self):
        """驗證 _RESOLVED_CALLABLE_CACHE 以 (yscb_root, uri_str) 為複合鍵。"""
        clear_callable_cache()
        fn = resolve_callable("code.func://core/symbols:parse_code_func_uri")
        self.assertTrue(callable(fn))
        expected_key = (uri.resolve_yscb_root(), "code.func://core/symbols:parse_code_func_uri")
        self.assertIn((expected_key[0], expected_key[1]), _RESOLVED_CALLABLE_CACHE)
        self.mark_passed()

    def test_resolve_callable_vfs_fallback_and_non_callable_error(self):
        """驗證 Track 2 VFS 實體路徑載入、非 callable 屬性攔截與損壞語法檔清理 sys.modules。"""
        mod_name = "mock-vfs-sym-mod"
        mod_uri = f"module.source://{mod_name}"
        try:
            vfs.makedirs(f"{mod_uri}/sub", exist_ok=True)
            vfs.write_text(
                f"{mod_uri}/sub/worker.py",
                "NOT_A_FUNC = 42\ndef run_job(x):\n    return x + 1\n",
            )
            fn = resolve_callable(f"code.func://{mod_name}/sub/worker:run_job", use_cache=False)
            self.assertEqual(fn(10), 11)

            # 驗證檔案內容變更時，resolve_callable(use_cache=True) 自動穿透快取與 Track 1 熱重載
            fn_cached_v1 = resolve_callable(f"code.func://{mod_name}/sub/worker:run_job", use_cache=True)
            self.assertEqual(fn_cached_v1(10), 11)
            vfs.write_text(
                f"{mod_uri}/sub/worker.py",
                "NOT_A_FUNC = 42\ndef run_job(x):\n    return x + 100\n",
            )
            fn_cached_v2 = resolve_callable(f"code.func://{mod_name}/sub/worker:run_job", use_cache=True)
            self.assertEqual(fn_cached_v2(10), 110)

            with self.assertRaises(SymbolNotFoundError) as ctx_nc:
                resolve_callable(f"code.func://{mod_name}/sub/worker:NOT_A_FUNC", use_cache=False)
            self.assertIn("not callable", str(ctx_nc.exception))

            # 損壞語法檔應拋出 SymbolNotFoundError 並從 sys.modules 清除殘留鍵
            broken_mod = "mock-vfs-broken-mod"
            broken_uri = f"module.source://{broken_mod}"
            vfs.makedirs(f"{broken_uri}/sub", exist_ok=True)
            vfs.write_text(f"{broken_uri}/sub/broken.py", "def broken_syntax(:\n")
            try:
                with self.assertRaises(SymbolNotFoundError):
                    resolve_callable(f"code.func://{broken_mod}/sub/broken:broken_syntax", use_cache=False)
                self.assertFalse(any("broken" in k and "mock_vfs_broken_mod" in k for k in sys.modules))
            finally:
                if vfs.exists(broken_uri):
                    vfs.rmtree(broken_uri)
        finally:
            if vfs.exists(mod_uri):
                vfs.rmtree(mod_uri)
            clear_callable_cache()
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
