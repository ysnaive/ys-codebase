"""
Unit and Workflow Tests for knowledge-db SemanticBundler and SemanticBundle.
"""

import json
import os
from pathlib import Path
import sys
import tempfile

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from knowledge_db.bundler import SemanticBundle, SemanticBundler
from knowledge_db.exceptions import KnowledgeDBError
from knowledge_db.schema import LanguageType, SpaceConfig, SymbolKind, UnifiedSymbol
from knowledge_db.space import SpaceManager


class TestBundler(YSCBTestCase):
    @require(Requirement.LOGIC)
    def test_ft_07_semantic_bundle_serialization(self):
        """FT-07: 驗證 SemanticBundle 資料模型之序列化與反序列化"""
        sym = UnifiedSymbol(
            id="abc123456",
            name="TestEngine",
            kind=SymbolKind.CLASS.value,
            file_path="src/engine.py",
            line_number=10,
            language=LanguageType.PYTHON.value,
            docstring="測試引擎",
        )
        bundle = SemanticBundle(
            version="1.0.0",
            space_name="test_space",
            created_at="2026-08-28T00:00:00Z",
            symbols=[sym],
            thesaurus=[["引擎", "engine"]],
            metadata={"total_files": 1},
        )

        d = bundle.to_dict()
        self.assertEqual(d["space_name"], "test_space")
        self.assertEqual(d["symbol_count"], 1)
        self.assertEqual(len(d["symbols"]), 1)
        self.assertEqual(d["symbols"][0]["name"], "TestEngine")

        restored = SemanticBundle.from_dict(d)
        self.assertEqual(restored.space_name, bundle.space_name)
        self.assertEqual(len(restored.symbols), 1)
        self.assertEqual(restored.symbols[0].name, "TestEngine")
        self.assertEqual(restored.thesaurus, [["引擎", "engine"]])

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_ft_08_bundler_bundle_export_and_import(self):
        """FT-08: 驗證 SemanticBundler 空間解析、原子導出與載入還原 (EC-07)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            # 建立多語言測試檔案
            (src_dir / "app.py").write_text("class MainApp: pass", encoding="utf-8")
            (src_dir / "README.md").write_text("# App Document\nDescription.", encoding="utf-8")

            space_cfg = SpaceConfig(name="multi_lang_space", include=[str(src_dir)])
            sm = SpaceManager(
                storage_dir=storage_dir,
                contributes_data={
                    "spaces": {"multi_lang_space": space_cfg.to_dict()},
                    "thesaurus": [["應用", "app", "application"]],
                },
            )

            bundler = SemanticBundler(sm)

            # 1. 執行打包
            bundle = bundler.bundle_space(space_cfg)
            self.assertEqual(bundle.space_name, "multi_lang_space")
            self.assertGreaterEqual(len(bundle.symbols), 2)
            self.assertEqual(len(bundle.thesaurus), 1)

            # 2. 導出 Bundle 檔案
            export_path = bundler.export_bundle(bundle)
            self.assertTrue(export_path.exists())

            # 3. 載入還原 Bundle 檔案
            imported_bundle = bundler.import_bundle(export_path)
            self.assertEqual(imported_bundle.space_name, "multi_lang_space")
            self.assertEqual(len(imported_bundle.symbols), len(bundle.symbols))

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_et_01_import_corrupted_bundle_error(self):
        """ET-01: 驗證載入損毀或不存在的 Bundle 檔案拋出 KnowledgeDBError (EC-05)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sm = SpaceManager(storage_dir=temp_path)
            bundler = SemanticBundler(sm)

            with self.assertRaises(KnowledgeDBError):
                bundler.import_bundle(temp_path / "non_existent.bundle.json")

            corrupt_file = temp_path / "corrupt.bundle.json"
            corrupt_file.write_text("INVALID JSON {{", encoding="utf-8")
            with self.assertRaises(KnowledgeDBError):
                bundler.import_bundle(corrupt_file)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
