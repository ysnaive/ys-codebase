"""
Unit tests for AST Engine P3 polish remediations:
- T-28: UnifiedSymbol.from_dict MemberInfo deduplication and .line / .line_number compatibility
- T-29: TopologyLinker deque BFS & pre-indexed inheritance/method maps in expand_contract_symbol_ids
- T-34: SnippetExtractor mtime_ns file line cache and invalidation on file update
- T-35: Pre-sorted enclosing symbol resolution in extract_call_sites
"""

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

_AST_ROOT = str(Path(__file__).resolve().parents[1])
if _AST_ROOT not in sys.path:
    sys.path.insert(0, _AST_ROOT)

from ast_engine.linker import TopologyLinker, expand_contract_symbol_ids
from ast_engine.parsers.python_ast import PythonASTParser
from ast_engine.resolver import SnippetExtractor
from ast_engine.schema import MemberInfo, UnifiedSymbol
from dev.testing import Requirement, YSCBTestCase, require


class TestASTEnginePolish(YSCBTestCase):
    """Tests for T-28, T-29, T-34, and T-35 in ast_engine."""

    def setUp(self):
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="yscb_ast_polish_test_"))

    def tearDown(self):
        if hasattr(self, "temp_dir") and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    @require(Requirement.LOGIC)
    def test_t28_unified_symbol_from_dict_children_member_info(self):
        """T-28: Verify UnifiedSymbol.from_dict deserializes children/members as Tuple[MemberInfo, ...] with line_number and line properties."""
        member = MemberInfo(
            name="compute",
            kind="method",
            signature="def compute(self, x: int) -> int",
            line_number=42,
            visibility="public",
            docstring="Compute value",
        )
        sym = UnifiedSymbol(
            id="sym_cls",
            name="Calculator",
            kind="class",
            file_path="src/calc.py",
            line_number=10,
            end_line=60,
            language="python",
            children=(member,),
            members=(member,),
        )
        restored = UnifiedSymbol.from_dict(sym.to_dict())
        self.assertEqual(len(restored.children), 1)
        self.assertIsInstance(restored.children[0], MemberInfo)
        self.assertIs(restored.children, restored.members)
        self.assertEqual(restored.children[0].line_number, 42)
        self.assertEqual(restored.children[0].line, 42)

        # Verify legacy dict format with 'line' instead of 'line_number'
        legacy_dict = sym.to_dict()
        legacy_dict["children"] = [
            {
                "name": "legacy_fn",
                "kind": "method",
                "line": 77,
                "end_line": 80,
                "signature": "def legacy_fn()",
            }
        ]
        legacy_dict.pop("members", None)
        restored_legacy = UnifiedSymbol.from_dict(legacy_dict)
        self.assertEqual(len(restored_legacy.children), 1)
        self.assertIsInstance(restored_legacy.children[0], MemberInfo)
        self.assertEqual(restored_legacy.children[0].line_number, 77)
        self.assertEqual(restored_legacy.children[0].line, 77)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_t29_linker_inheritance_cache_and_deque_bfs(self):
        """T-29: Verify TopologyLinker pre-indexes inheritance/methods and expand_contract_symbol_ids expands base and derived methods."""
        base_cls = UnifiedSymbol(
            id="cls_base",
            name="BaseService",
            kind="class",
            file_path="svc.py",
            line_number=1,
            end_line=10,
            language="python",
        )
        sub_cls = UnifiedSymbol(
            id="cls_sub",
            name="SubService",
            kind="class",
            file_path="svc.py",
            line_number=12,
            end_line=25,
            language="python",
            metadata={"base_types": ["BaseService"]},
        )
        base_method = UnifiedSymbol(
            id="m_base_run",
            name="BaseService.run",
            kind="method",
            file_path="svc.py",
            line_number=3,
            end_line=6,
            language="python",
            metadata={"parent_scope": "BaseService", "short_name": "run"},
        )
        sub_method = UnifiedSymbol(
            id="m_sub_run",
            name="SubService.run",
            kind="method",
            file_path="svc.py",
            line_number=15,
            end_line=20,
            language="python",
            metadata={"parent_scope": "SubService", "short_name": "run"},
        )
        symbols = [base_cls, sub_cls, base_method, sub_method]
        linker = TopologyLinker(symbols)
        self.assertIn("BaseService", linker._base_derived)
        self.assertIn("SubService", linker._base_derived["BaseService"])
        self.assertIn(("BaseService", "run"), linker._methods_by_class_and_short)
        self.assertIn(("SubService", "run"), linker._methods_by_class_and_short)

        expanded = expand_contract_symbol_ids(linker.symbols_map, [base_method])
        self.assertIn("m_base_run", expanded)
        self.assertIn("m_sub_run", expanded)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_t34_snippet_extractor_mtime_ns_cache_invalidation(self):
        """T-34: Verify ast_engine SnippetExtractor caches file lines by mtime_ns and refreshes when file is modified."""
        target_file = self.temp_dir / "sample.py"
        target_file.write_text("line_one = 1\nline_two = 2\nline_three = 3\n", encoding="utf-8")

        extractor = SnippetExtractor(project_root=self.temp_dir)
        snip1 = extractor.extract(str(target_file), line_number=2, end_line=2, context_before=0, context_after=0)
        self.assertIsNotNone(snip1)
        self.assertIn("line_two = 2", snip1.content)
        self.assertEqual(len(extractor._file_lines_cache), 1)

        # Modify file and bump mtime_ns explicitly to guarantee change across fast filesystems
        st_old = target_file.stat()
        target_file.write_text("line_one = 1\nline_two = 222\nline_three = 3\n", encoding="utf-8")
        os.utime(target_file, ns=(st_old.st_atime_ns, st_old.st_mtime_ns + 1_000_000))

        snip2 = extractor.extract(str(target_file), line_number=2, end_line=2, context_before=0, context_after=0)
        self.assertIsNotNone(snip2)
        self.assertIn("line_two = 222", snip2.content)
        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_t35_extract_call_sites_presorted_enclosing_symbol(self):
        """T-35: Verify extract_call_sites resolves the smallest enclosing symbol span without mutating kind order."""
        code = (
            "class Outer:\n"
            "    def inner_method(self):\n"
            "        helper_call()\n"
        )
        driver = PythonASTParser()
        syms = driver.parse("test_mod.py", code, space="code")
        sites = driver.extract_call_sites("test_mod.py", code, space="code", symbols=syms)
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].callee_name, "helper_call")
        self.assertTrue(sites[0].caller_member_name.endswith("inner_method"))
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
