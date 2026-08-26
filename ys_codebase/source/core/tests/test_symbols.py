"""
Unit tests for core.symbols (code.func:// protocol).
100% standard library unittest.
"""

import unittest
from core.symbols import (
    parse_code_func_uri,
    resolve_callable,
    clear_callable_cache,
    InvalidSymbolURIError,
    SymbolNotFoundError
)


def sample_test_func(context=None):
    """用於測試符號解析之測試函式。"""
    return f"sample_output:{getattr(context, 'name', 'no_ctx')}"


class TestSymbolsProtocol(unittest.TestCase):
    """測試 code.func:// 協議解析與 Callable 加載。"""

    def setUp(self):
        clear_callable_cache()

    def test_st_01_parse_code_func_uri_success(self):
        """ST-01: 驗證標準 code.func:// 語法解析。"""
        mod, sub, fn = parse_code_func_uri("code.func://agents-workflow/providers:get_dynamic_context_map")
        self.assertEqual(mod, "agents-workflow")
        self.assertEqual(sub, "providers")
        self.assertEqual(fn, "get_dynamic_context_map")

        # 支援 .py 後綴與無 subpath
        mod2, sub2, fn2 = parse_code_func_uri("code.func://core/symbols.py:resolve_callable")
        self.assertEqual(mod2, "core")
        self.assertEqual(sub2, "symbols")
        self.assertEqual(fn2, "resolve_callable")

    def test_st_02_parse_code_func_uri_invalid(self):
        """ST-02: 驗證無效 URI 格式防禦 (EC-01)。"""
        # 非字串
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri(123)  # type: ignore

        # 錯誤協議前綴
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("http://agents-workflow/providers:func")

        # 缺少 ':' 符號
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("code.func://agents-workflow/providers")

        # 空函式名
        with self.assertRaises(InvalidSymbolURIError):
            parse_code_func_uri("code.func://agents-workflow/providers:")

    def test_st_03_resolve_callable_package_import(self):
        """ST-01: 驗證透過已加載 package / sys.modules 解析 Callable。"""
        fn = resolve_callable("code.func://core/symbols:parse_code_func_uri")
        self.assertTrue(callable(fn))
        self.assertEqual(fn, parse_code_func_uri)

        # 驗證快取命中
        fn_cached = resolve_callable("code.func://core/symbols:parse_code_func_uri")
        self.assertIs(fn, fn_cached)

    def test_st_04_resolve_callable_not_found(self):
        """ST-03: 驗證模組不存在或函式不存在防禦 (EC-02)。"""
        # 不存在的模組
        with self.assertRaises(SymbolNotFoundError):
            resolve_callable("code.func://non_existent_pkg_xyz/foo:bar", use_cache=False)

        # 模組存在但函式不存在
        with self.assertRaises(SymbolNotFoundError):
            resolve_callable("code.func://core/symbols:non_existent_func_xyz", use_cache=False)


if __name__ == "__main__":
    unittest.main()
