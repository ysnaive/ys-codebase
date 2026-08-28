"""
Unit Tests for knowledge-db KnowledgeEngine SDK Facade.
"""

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
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.exceptions import SpaceNotFoundError
from knowledge_db.schema import SpaceConfig


class TestEngine(YSCBTestCase):
    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_engine_status_and_lifecycle(self):
        """FT-01~06: 驗證 KnowledgeEngine 門面 API 全生命週期操作"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            # 建立測試源碼與文檔
            (src_dir / "controller.py").write_text(
                "class PIDController:\n    '''PID 控制器實作'''\n    def calculate(self): pass",
                encoding="utf-8",
            )
            (src_dir / "README.md").write_text(
                "# 機器人系統手冊\n本系統提供速度與位置控制演算法。",
                encoding="utf-8",
            )

            space_cfg = SpaceConfig(name="demo_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={
                    "spaces": {"demo_space": space_cfg.to_dict()},
                    "thesaurus": [["演算法", "algorithm"]],
                },
            )

            # 1. status 驗證 (FT-01)
            st = engine.status()
            self.assertEqual(st["total_spaces"], 1)
            self.assertIn("demo_space", st["spaces"])
            self.assertEqual(st["spaces"]["demo_space"]["cached_files"], 0)

            # 2. scan 驗證 (FT-02)
            diffs = engine.scan(space="demo_space")
            self.assertEqual(len(diffs["demo_space"].added), 2)

            # 3. bundle 驗證 (FT-03)
            bundles = engine.bundle(space="demo_space")
            self.assertEqual(len(bundles), 1)
            self.assertEqual(bundles[0].space_name, "demo_space")
            self.assertGreaterEqual(len(bundles[0].symbols), 2)

            # 4. build_index 驗證 (FT-04)
            indices = engine.build_index(space="demo_space")
            self.assertIn("demo_space", indices)
            idx_file = storage_dir / "indices" / "demo_space.index.json"
            self.assertTrue(idx_file.exists())

            # 5. search 驗證 (FT-05)
            results = engine.search("PIDController", space="demo_space")
            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0].symbol.name, "PIDController")

            # 6. clean 驗證 (FT-06)
            engine.clean(space="demo_space")
            self.assertFalse(idx_file.exists())
            st_after = engine.status()
            self.assertEqual(st_after["spaces"]["demo_space"]["cached_files"], 0)

    @require(Requirement.LOGIC | Requirement.ISOLATED_SANDBOX)
    def test_engine_search_and_lazy_indexing(self):
        """FT-05: 驗證未手動建置索引時 search 自動觸發懶建置 (Lazy Indexing, EC-01)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            (src_dir / "motor.py").write_text("class MotorGroup: pass", encoding="utf-8")

            space_cfg = SpaceConfig(name="motor_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                contributes_data={"spaces": {"motor_space": space_cfg.to_dict()}},
            )

            # 直接呼叫 search，應自動懶建置並返回結果
            results = engine.search("MotorGroup", space="motor_space")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].symbol.name, "MotorGroup")

    @require(Requirement.LOGIC)
    def test_non_existent_space_error(self):
        """ET-01: 驗證操作不存在空間拋出 SpaceNotFoundError (EC-02)"""
        engine = KnowledgeEngine()
        with self.assertRaises(SpaceNotFoundError):
            engine.scan(space="non_existent_12345")
