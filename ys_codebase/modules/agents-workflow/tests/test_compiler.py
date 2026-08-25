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
        self.assertIn("BEGIN_HTML_ANNOTATION", token_values)
        self.assertIn("END_HTML_ANNOTATION", token_values)

    def test_ft_02_single_artifact_replace_resolution(self):
        """FT-02: 驗證工廠編譯器多輪遞迴狀態機解算與 replace 自注入。"""
        raw_text = "# Requirements Spec\n\n__@{PHASEXX_STANDARD_HEADER}__\n\n## 1. FR\n"
        inserts = [
            {
                "type": "const",
                "token": "PHASEXX_STANDARD_HEADER",
                "value": "> 功能名稱：Test Feature\n> 狀態：Confirmed",
                "mode": "replace"
            }
        ]
        
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("__@{PHASEXX_STANDARD_HEADER}__", resolved)
        self.assertIn("> 功能名稱：Test Feature", resolved)
        self.assertIn("> 狀態：Confirmed", resolved)
        self.assertIn("## 1. FR", resolved)

    def test_ft_03_multi_module_below_above_injection_and_purge(self):
        """FT-03: 驗證多模組以 below/above 向同一 Token 追加注入，且 Step 3 乾淨移除標籤。"""
        raw_text = "# Standards\n\n__@{RULES}__\n\nEnd of Doc"
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
        self.assertNotIn("__@{RULES}__", resolved)
        self.assertIn("RULE-01: Above Rule", resolved)
        self.assertIn("RULE-02: Below Rule", resolved)
        # Verify order: above is before below
        pos_above = resolved.find("RULE-01: Above Rule")
        pos_below = resolved.find("RULE-02: Below Rule")
        self.assertLess(pos_above, pos_below)

    def test_ft_04_uri_tag_preserved(self):
        """FT-04: 驗證 __#{uri}__ 標籤在物化解算階段 100% 保持原樣不被破壞。"""
        raw_text = "Doc with link: __#{module.root://agents-workflow/assets/standards/DocumentationStandards.md}__ and __@{TOKEN}__"
        inserts = [
            {"type": "const", "token": "TOKEN", "value": "Resolved Value", "mode": "replace"}
        ]
        
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertIn("__#{module.root://agents-workflow/assets/standards/DocumentationStandards.md}__", resolved)
        self.assertIn("Resolved Value", resolved)
        self.assertNotIn("__@{TOKEN}__", resolved)

    def test_ft_05_whitespace_tolerance(self):
        """FT-05: 驗證大括號內部微量空格容錯識別 (__@{ TOKEN }__)。"""
        raw_text = "Anchor: __@{ CUSTOM_TOKEN }__"
        inserts = [
            {"type": "const", "token": "CUSTOM_TOKEN", "value": "Tolerance Passed", "mode": "replace"}
        ]
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertNotIn("__@{ CUSTOM_TOKEN }__", resolved)
        self.assertIn("Tolerance Passed", resolved)

    def test_ft_06_cli_commands_and_hook(self):
        """FT-06: 驗證 compile, tokens, list 指令與 hook 正常執行。"""
        # tokens
        tokens_code = cli.main(["tokens"])
        self.assertEqual(tokens_code, 0)

        # list
        list_code = cli.main(["list"])
        self.assertEqual(list_code, 0)

        # compile
        compile_code = cli.main(["compile"])
        self.assertEqual(compile_code, 0)

        # hook
        if hook_core and hasattr(hook_core, "on_reload"):
            hook_core.on_reload(None)

    def test_et_01_unmatched_token_purged_safely(self):
        """ET-01: 驗證無匹配 Insert 時 Token 標籤被乾淨移除，不殘留也不崩潰。"""
        raw_text = "Before\n__@{NON_EXISTENT_TOKEN}__\nAfter"
        resolved = self.compiler.resolve_single_artifact(raw_text, [])
        self.assertNotIn("__@{NON_EXISTENT_TOKEN}__", resolved)
        self.assertIn("Before", resolved)
        self.assertIn("After", resolved)

    def test_et_02_recursive_multi_pass(self):
        """ET-02: 驗證新注入內容包含子 Token 時能多輪收斂展開。"""
        raw_text = "Start -> __@{PARENT}__ -> End"
        inserts = [
            {
                "type": "const",
                "token": "PARENT",
                "value": "ParentContent(__@{CHILD}__)",
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
        self.assertNotIn("__@{PARENT}__", resolved)
        self.assertNotIn("__@{CHILD}__", resolved)
        self.assertIn("ParentContent(ChildValue)", resolved)

    def test_et_03_legacy_html_comment_ignored(self):
        """ET-03: 驗證舊的 HTML 註解格式不再被視為錨點進行展開，作為純文字保留。"""
        raw_text = "Legacy: <!-- __PHASEXX_STANDARD_HEADER__ -->"
        inserts = [
            {"type": "const", "token": "PHASEXX_STANDARD_HEADER", "value": "New Header", "mode": "replace"}
        ]
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertIn("<!-- __PHASEXX_STANDARD_HEADER__ -->", resolved)
        self.assertNotIn("New Header", resolved)

    def test_et_04_self_referential_deadlock_prevention(self):
        """ET-04: 驗證注入內容包含同名 Token 時不會陷入無窮遞迴死鎖。"""
        raw_text = "Anchor: __@{LOOP}__"
        inserts = [
            {"type": "const", "token": "LOOP", "value": "Value with __@{LOOP}__", "mode": "replace"}
        ]
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertIn("Value with", resolved)

    def test_ft_07_html_annotation_tokens_resolution(self):
        """FT-07: 驗證 BEGIN_HTML_ANNOTATION 與 END_HTML_ANNOTATION 替換為 <!-- 與 -->。"""
        raw_text = "__@{BEGIN_HTML_ANNOTATION}__ slide __@{END_HTML_ANNOTATION}__"
        inserts = [
            {"type": "const", "token": "BEGIN_HTML_ANNOTATION", "value": "<!--", "mode": "replace"},
            {"type": "const", "token": "END_HTML_ANNOTATION", "value": "-->", "mode": "replace"}
        ]
        resolved = self.compiler.resolve_single_artifact(raw_text, inserts)
        self.assertEqual(resolved, "<!-- slide -->")


if __name__ == "__main__":
    unittest.main()
