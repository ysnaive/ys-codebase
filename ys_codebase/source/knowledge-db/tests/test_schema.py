"""
Unit Tests for knowledge-db Schema, Enums, and Data Models.
"""

import os
import sys
import unittest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.exceptions import InvalidConfigError, SchemaValidationError
from knowledge_db.schema import (
    KnowledgeDBContributes,
    LanguageConfig,
    LanguageType,
    MemberInfo,
    SymbolKind,
    UnifiedSymbol,
    validate_space_weights,
)
from file_space import InvalidFileSpaceConfigError, FileSpaceConfig, FileSpaceOrigin


class TestSchema(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_ft_01_member_info_and_enums(self):
        """驗證 Enums 與 MemberInfo 模型屬性、序列化與反序列化"""
        self.assertEqual(SymbolKind.CLASS.value, "class")
        self.assertEqual(SymbolKind.DOC_HEADING_1.value, "doc_heading_1")
        self.assertEqual(LanguageType.PYTHON.value, "python")
        self.assertEqual(LanguageType.MARKDOWN.value, "markdown")
        self.assertEqual(FileSpaceOrigin.PROJECT.value, "project")
        self.assertEqual(FileSpaceOrigin.MODULE.value, "module")

        member = MemberInfo(
            name="run_cli",
            kind="method",
            signature="(self, cmd: str) -> bool",
            docstring="執行 CLI 指令",
            visibility="public",
            line_number=42,
        )
        d = member.to_dict()
        self.assertEqual(d["name"], "run_cli")
        self.assertEqual(d["kind"], "method")
        self.assertEqual(d["line_number"], 42)

        restored = MemberInfo.from_dict(d)
        self.assertEqual(restored.name, member.name)
        self.assertEqual(restored.signature, member.signature)
        self.assertEqual(restored.line_number, 42)

        with self.assertRaises(SchemaValidationError):
            MemberInfo.from_dict({"name": "only_name"})

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_02_unified_symbol_and_id_computation(self):
        """驗證 UnifiedSymbol 不可變性、SHA1 唯一 ID 計算與序列化"""
        computed_id = UnifiedSymbol.compute_id(
            space="core_symbols",
            file_path="source/core/engine.py",
            name="CoreEngine",
            kind="class",
            line_number=15,
        )
        self.assertEqual(len(computed_id), 40)
        computed_id2 = UnifiedSymbol.compute_id(
            space="core_symbols",
            file_path="source/core/engine.py",
            name="CoreEngine",
            kind="class",
            line_number=15,
        )
        self.assertEqual(computed_id, computed_id2)

        child_sym = UnifiedSymbol(
            id="child_init",
            name="init",
            kind=SymbolKind.METHOD.value,
            file_path="source/core/engine.py",
            line_number=20,
            language=LanguageType.PYTHON.value,
            signature="def init(self) -> None",
            docstring="初始化引擎",
            parent_id=computed_id,
        )
        sym = UnifiedSymbol(
            id=computed_id,
            name="CoreEngine",
            kind=SymbolKind.CLASS.value,
            file_path="source/core/engine.py",
            line_number=15,
            language=LanguageType.PYTHON.value,
            docstring="核心引擎類別",
            signature="class CoreEngine",
            children=(child_sym,),
            metadata={"tags": ["core", "engine"], "end_line": 120},
        )

        d = sym.to_dict()
        self.assertEqual(d["id"], computed_id)
        self.assertNotIn("members", d)
        self.assertNotIn("space", d)
        self.assertEqual(len(d["children"]), 1)
        self.assertEqual(d["children"][0]["name"], "init")
        self.assertEqual(d["metadata"]["tags"], ["core", "engine"])

        restored = UnifiedSymbol.from_dict(d)
        self.assertEqual(restored.id, sym.id)
        self.assertEqual(restored.name, sym.name)
        self.assertEqual(len(restored.children), 1)
        self.assertEqual(restored.children[0].name, "init")
        self.assertEqual(len(restored.members), 1)
        self.assertEqual(restored.members[0].name, "init")

        with self.assertRaises(Exception):
            sym.name = "ModifiedEngine"  # type: ignore

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_03_space_weights_and_contributes_schema(self):
        """驗證 KnowledgeDBContributes (space_weights) 與 FileSpaceConfig 校驗"""
        cfg_all = FileSpaceConfig.from_dict(
            name="project_main",
            data={
                "description": "全部檔案空間",
                "include": ["project://source"],
                "exclude": ["**/__pycache__/**"],
            },
        )
        self.assertEqual(cfg_all.file_patterns, [])
        self.assertTrue(cfg_all.is_file_included("test.py"))
        self.assertTrue(cfg_all.is_file_included("doc.md"))

        with self.assertRaises(InvalidFileSpaceConfigError):
            FileSpaceConfig.from_dict("invalid", {"include": ["project://source"], "hash_policy": "invalid_policy"})

        contributes = KnowledgeDBContributes.from_dict({
            "space_weights": {"source": 1.0, "docs": 1.2, "plans": 0.85},
            "languages": {
                "rust": {
                    "name": "Rust",
                    "extensions": [".rs"],
                    "mode": "tree_sitter",
                    "grammar": "tree_sitter_rust",
                }
            },
        })
        self.assertAlmostEqual(contributes.space_weights["docs"], 1.2)
        self.assertAlmostEqual(contributes.space_weights["plans"], 0.85)
        self.assertIn("rust", contributes.languages)

        for bad_weight in (0, 0.0, -0.5, "not_a_float", False):
            with self.assertRaises(InvalidConfigError):
                validate_space_weights({"source": bad_weight})
            with self.assertRaises(InvalidConfigError):
                KnowledgeDBContributes(space_weights={"source": bad_weight})  # type: ignore[dict-item]

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_04_universal_ast_hierarchy_and_fqn(self):
        """驗證 Universal AST 遞迴階層 (parent_id/children)、FQN 與 search_payload"""
        method_sym = UnifiedSymbol(
            id="method_hash_1",
            name="connect",
            kind=SymbolKind.METHOD.value,
            file_path="pkg/db.py",
            line_number=20,
            end_line=30,
            language=LanguageType.PYTHON.value,
            signature="def connect(self, timeout: int = 10) -> bool:",
            docstring="建立連線",
            fqn="pkg.db.DatabaseClient.connect",
            scope_path="DatabaseClient",
            parent_id="class_hash_1",
            parameters=({"name": "timeout", "type": "int", "default": 10},),
            return_type="bool",
            search_payload="DatabaseClient.connect def connect(timeout: int = 10) -> bool 建立連線",
        )

        class_sym = UnifiedSymbol(
            id="class_hash_1",
            name="DatabaseClient",
            kind=SymbolKind.CLASS.value,
            file_path="pkg/db.py",
            line_number=10,
            end_line=50,
            language=LanguageType.PYTHON.value,
            signature="class DatabaseClient:",
            docstring="資料庫客戶端",
            fqn="pkg.db.DatabaseClient",
            children=(method_sym,),
            search_payload="DatabaseClient class DatabaseClient 資料庫客戶端",
        )

        self.assertEqual(class_sym.fqn, "pkg.db.DatabaseClient")
        self.assertEqual(len(class_sym.children), 1)
        self.assertEqual(len(class_sym.members), 1)
        self.assertEqual(class_sym.children[0].name, "connect")
        self.assertEqual(class_sym.children[0].parent_id, "class_hash_1")
        self.assertEqual(class_sym.children[0].return_type, "bool")
        self.assertEqual(len(class_sym.children[0].parameters), 1)
        self.assertEqual(class_sym.children[0].parameters[0]["name"], "timeout")

        d = class_sym.to_dict()
        self.assertEqual(d["fqn"], "pkg.db.DatabaseClient")
        self.assertEqual(len(d["children"]), 1)
        self.assertEqual(d["children"][0]["fqn"], "pkg.db.DatabaseClient.connect")

        restored = UnifiedSymbol.from_dict(d)
        self.assertEqual(restored.fqn, "pkg.db.DatabaseClient")
        self.assertEqual(len(restored.children), 1)
        self.assertEqual(restored.children[0].name, "connect")
        self.assertEqual(restored.children[0].fqn, "pkg.db.DatabaseClient.connect")
        self.assertEqual(restored.children[0].parent_id, "class_hash_1")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_05_language_config_serialization(self):
        """驗證 LanguageConfig 模型與 contributes 外掛配置解析"""
        cfg_data = {
            "id": "rust",
            "name": "Rust Language",
            "extensions": [".rs"],
            "mode": "tree_sitter",
            "grammar": "tree_sitter_rust",
            "query_file": "module://my-mod/assets/queries/rust.scm",
            "custom_kinds": [{"kind": "trait", "category": "interface"}],
        }
        lang_cfg = LanguageConfig.from_dict(cfg_data)
        self.assertEqual(lang_cfg.id, "rust")
        self.assertEqual(lang_cfg.extensions, (".rs",))
        self.assertEqual(lang_cfg.mode, "tree_sitter")
        self.assertEqual(lang_cfg.grammar, "tree_sitter_rust")
        self.assertEqual(len(lang_cfg.custom_kinds), 1)

        d = lang_cfg.to_dict()
        self.assertEqual(d["id"], "rust")
        self.assertEqual(d["extensions"], [".rs"])

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
