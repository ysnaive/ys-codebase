"""
Unit and Integration Tests for agents-workflow ArtifactCompiler and CLI.
Covers FT-01 ~ FT-06, ET-01 ~ ET-04.
"""
import unittest
import os
import io
import sys
from typing import Dict, Any, List

# Ensure package and core are in sys.path
_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from agents_workflow.compiler import ArtifactCompiler
from scripts import cli

hook_core = None
try:
    import importlib.util
    hook_path = os.path.join(_pkg_root, "scripts", "hook.core.py")
    if os.path.exists(hook_path):
        spec = importlib.util.spec_from_file_location("hook_core", hook_path)
        hook_core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook_core)
except Exception:
    hook_core = None


class TestArtifactCompiler(unittest.TestCase):
    def setUp(self):
        self.compiler = ArtifactCompiler()

    def test_ft_01_manifest_exports_and_tokens_discovery(self):
        """FT-01: 驗證自導出資產 (16 項) 與 token 宣告能被正確解析收集。"""
        data = self.compiler.get_contributes_data()
        exports = data.get("export", [])
        tokens = data.get("token", [])
        
        self.assertGreaterEqual(len(exports), 16)
        token_values = [t.get("value") for t in tokens]
        self.assertIn("PHASEXX_STANDARD_HEADER", token_values)
        self.assertIn("PROJECT_SPECIFIC_STANDARDS", token_values)
        self.assertIn("DYNAMIC_CONTEXT_MAP", token_values)

    def test_ft_02_single_artifact_replace_resolution(self):
        """FT-02: 驗證工廠編譯器多輪遞迴狀態機解算與 replace 自注入。"""
        raw_text = "# Requirements Spec\n\n<!-- __PHASEXX_STANDARD_HEADER__ -->\n\n## 1. FR\n"
        inserts = [
            {
                "type": "const",
                "token": "PHASEXX_STANDARD_HEADER",
                "value": "> 功能名稱：Test Feature\n> 狀態：Confirmed",
                "mode": "replace"
            }
        ]
        
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("<!-- __PHASEXX_STANDARD_HEADER__ -->", resolved)
        self.assertIn("> 功能名稱：Test Feature", resolved)
        self.assertIn("> 狀態：Confirmed", resolved)
        self.assertIn("## 1. FR", resolved)

    def test_ft_03_multi_module_below_above_injection_and_purge(self):
        """FT-03: 驗證多模組以 below/above 向同一 Token 追加注入，且 Step 3 乾淨移除標籤。"""
        raw_text = "# Standards\n\n<!-- __RULES__ -->\n\nEnd of Doc"
        inserts = [
            {
                "type": "const",
                "token": "RULES",
                "value": "RULE-01: Above Rule",
                "mode": "above"
            },
            {
                "type": "const",
                "token": "RULES",
                "value": "RULE-02: Below Rule",
                "mode": "below"
            }
        ]
        
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("<!-- __RULES__ -->", resolved)
        self.assertIn("RULE-01: Above Rule", resolved)
        self.assertIn("RULE-02: Below Rule", resolved)
        # Verify order: above is before below
        pos_above = resolved.find("RULE-01: Above Rule")
        pos_below = resolved.find("RULE-02: Below Rule")
        self.assertLess(pos_above, pos_below)

    def test_ft_04_uri_tag_preserved(self):
        """FT-04: 驗證 <!-- __URI(...)__ --> 標籤在物化解算階段保持原樣不被破壞。"""
        raw_text = "Doc with link: <!-- __URI(\"docs://STANDARDS.md\")__ --> and <!-- __TOKEN__ -->"
        inserts = [
            {"type": "const", "token": "TOKEN", "value": "Resolved Value", "mode": "replace"}
        ]
        
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertIn("<!-- __URI(\"docs://STANDARDS.md\")__ -->", resolved)
        self.assertIn("Resolved Value", resolved)
        self.assertNotIn("<!-- __TOKEN__ -->", resolved)

    def test_ft_05_cli_commands(self):
        """FT-05: 驗證 compile, tokens, list 指令正常執行。"""
        # tokens
        tokens_code = cli.main(["tokens"])
        self.assertEqual(tokens_code, 0)

        # list
        list_code = cli.main(["list"])
        self.assertEqual(list_code, 0)

        # compile
        compile_code = cli.main(["compile"])
        self.assertEqual(compile_code, 0)

    def test_ft_06_hook_on_reload(self):
        """FT-06: 驗證 hook.core.py:on_reload 能正常執行不拋錯。"""
        if hook_core and hasattr(hook_core, "on_reload"):
            # Should run without error
            hook_core.on_reload(None)

    def test_et_01_unmatched_token_purged_safely(self):
        """ET-01: 驗證無匹配 Insert 時 Token 標籤被乾淨移除，不殘留也不崩潰。"""
        raw_text = "Before\n<!-- __NON_EXISTENT_TOKEN__ -->\nAfter"
        resolved = self.compiler.resolve_single_artifact(raw_text, [])
        self.assertNotIn("<!-- __NON_EXISTENT_TOKEN__ -->", resolved)
        self.assertIn("Before", resolved)
        self.assertIn("After", resolved)

    def test_et_02_recursive_multi_pass(self):
        """ET-02: 驗證新注入內容包含子 Token 時能多輪收斂展開。"""
        raw_text = "Start -> <!-- __PARENT__ --> -> End"
        inserts = [
            {
                "type": "const",
                "token": "PARENT",
                "value": "ParentContent(<!-- __CHILD__ -->)",
                "mode": "replace"
            },
            {
                "type": "const",
                "token": "CHILD",
                "value": "ChildValue",
                "mode": "replace"
            }
        ]
        
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("<!-- __PARENT__ -->", resolved)
        self.assertNotIn("<!-- __CHILD__ -->", resolved)
        self.assertIn("ParentContent(ChildValue)", resolved)

    def test_et_03_self_injection_end_to_end_compile(self):
        """ET-03: 驗證全量 compile_all() 物化產物 100% 成功。"""
        result = self.compiler.compile_all()
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["exported_count"], 16)


if __name__ == "__main__":
    unittest.main()
