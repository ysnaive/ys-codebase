"""
Unit Tests for knowledge-db Schema, Enums, and Data Models.
"""

import os
import sys
from typing import Any, Dict

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.exceptions import InvalidSpaceConfigError, SchemaValidationError
from knowledge_db.schema import (
    LanguageType,
    MemberInfo,
    SpaceConfig,
    SpaceOrigin,
    SymbolKind,
    ThesaurusConfig,
    UnifiedSymbol,
)


class TestSchema(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_ft_01_member_info_and_enums(self):
        """FT-01: 驗證 Enums 與 MemberInfo 模型屬性、序列化與反序列化"""
        # 1. Enums 驗證
        self.assertEqual(SymbolKind.CLASS.value, "class")
        self.assertEqual(SymbolKind.DOC_HEADING_1.value, "doc_heading_1")
        self.assertEqual(LanguageType.PYTHON.value, "python")
        self.assertEqual(LanguageType.MARKDOWN.value, "markdown")
        self.assertEqual(SpaceOrigin.PROJECT.value, "project")
        self.assertEqual(SpaceOrigin.CONTRIBUTED.value, "contributed")

        # 2. MemberInfo 序列化
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

        # 3. MemberInfo 反序列化
        restored = MemberInfo.from_dict(d)
        self.assertEqual(restored.name, member.name)
        self.assertEqual(restored.signature, member.signature)
        self.assertEqual(restored.line_number, 42)

        # 4. 異常反序列化防禦
        with self.assertRaises(SchemaValidationError):
            MemberInfo.from_dict({"name": "only_name"})

    @require(Requirement.LOGIC)
    def test_ft_02_unified_symbol_and_id_computation(self):
        """FT-02: 驗證 UnifiedSymbol 不可變性、SHA1 唯一 ID 計算與序列化"""
        # 1. compute_id 測試
        computed_id = UnifiedSymbol.compute_id(
            space="core_symbols",
            file_path="source/core/engine.py",
            name="CoreEngine",
            kind="class",
            line_number=15,
        )
        self.assertEqual(len(computed_id), 40)  # SHA-1 hex 長度為 40
        # 相同輸入雜湊必須完全一致
        computed_id2 = UnifiedSymbol.compute_id(
            space="core_symbols",
            file_path="source/core/engine.py",
            name="CoreEngine",
            kind="class",
            line_number=15,
        )
        self.assertEqual(computed_id, computed_id2)

        # 2. UnifiedSymbol 建立與序列化
        member = MemberInfo(name="init", kind="method", line_number=20)
        sym = UnifiedSymbol(
            id=computed_id,
            name="CoreEngine",
            kind=SymbolKind.CLASS.value,
            file_path="source/core/engine.py",
            line_number=15,
            language=LanguageType.PYTHON.value,
            docstring="核心引擎類別",
            signature="class CoreEngine",
            members=[member],
            metadata={"tags": ["core", "engine"], "end_line": 120},
        )

        d = sym.to_dict()
        self.assertEqual(d["id"], computed_id)
        self.assertEqual(len(d["members"]), 1)
        self.assertEqual(d["members"][0]["name"], "init")
        self.assertEqual(d["metadata"]["tags"], ["core", "engine"])

        # 3. 反序列化
        restored = UnifiedSymbol.from_dict(d)
        self.assertEqual(restored.id, sym.id)
        self.assertEqual(restored.name, sym.name)
        self.assertEqual(len(restored.members), 1)
        self.assertEqual(restored.members[0].name, "init")

        # 4. 不可變性測試 (frozen=True)
        with self.assertRaises(Exception):
            sym.name = "ModifiedEngine"  # type: ignore

    @require(Requirement.LOGIC)
    def test_ft_03_space_and_thesaurus_config(self):
        """FT-03: 驗證 SpaceConfig、ThesaurusConfig 與 file_patterns (EC-01)"""
        # 1. 未指定 file_patterns 預設 include all (EC-01)
        cfg_all = SpaceConfig.from_dict(
            name="project_main",
            data={
                "description": "全部檔案空間",
                "include": ["project://source"],
                "exclude": ["**/__pycache__/**"],
            },
        )
        self.assertIsNone(cfg_all.file_patterns)
        self.assertTrue(cfg_all.is_file_included("test.py"))
        self.assertTrue(cfg_all.is_file_included("doc.md"))
        self.assertTrue(cfg_all.is_file_included("any_file.custom_ext"))

        # 2. 指定 file_patterns
        cfg_pattern = SpaceConfig.from_dict(
            name="python_only",
            data={
                "include": ["project://source"],
                "file_patterns": ["*.py", "*.pyi"],
            },
        )
        self.assertEqual(cfg_pattern.file_patterns, ["*.py", "*.pyi"])
        self.assertTrue(cfg_pattern.is_file_included("main.py"))
        self.assertTrue(cfg_pattern.is_file_included("types.pyi"))
        self.assertFalse(cfg_pattern.is_file_included("readme.md"))

        # 3. 缺失 include 必填欄位拋出 InvalidSpaceConfigError
        with self.assertRaises(InvalidSpaceConfigError):
            SpaceConfig.from_dict("invalid", {"description": "no include"})

        # 4. ThesaurusConfig 解析
        th_list = [
            ["狀態機", "state_machine", "FSM"],
            ["知識庫", "knowledge_db"],
        ]
        th_cfg = ThesaurusConfig.from_dict(th_list, origin="project")
        self.assertEqual(len(th_cfg.groups), 2)
        self.assertIn("FSM", th_cfg.groups[0])
        d_th = th_cfg.to_dict()
        self.assertEqual(len(d_th["groups"]), 2)
