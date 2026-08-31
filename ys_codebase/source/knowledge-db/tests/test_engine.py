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
    @require(Requirement.LOGIC)
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
            idx_file = storage_dir / "indices" / "demo_space.index.bin.gz"
            self.assertTrue(idx_file.exists())

            # 5. search 驗證 (FT-05)
            results = engine.search("PIDController", space="demo_space")
            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0].symbol.name, "PIDController")

            # 6. clean 驗證 (FT-06)
            engine.clean(space="demo_space")
            self.assertFalse(idx_file.exists())
            st_after = engine.status()
            self.assertEqual(st_after["spaces"]["demo_space"]["fingerprint_cached_files"], 0)

    @require(Requirement.LOGIC)
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
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = KnowledgeEngine(storage_dir=temp_dir)
            with self.assertRaises(SpaceNotFoundError):
                engine.scan(space="non_existent_12345")

    @require(Requirement.LOGIC)
    def test_ft_07_to_file_uri_and_formatting(self):
        """FT-07: 驗證 to_file_uri 與 format_file_link 生成標準 RFC 8089 URI 與 Markdown 標籤"""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = KnowledgeEngine(storage_dir=temp_dir)
            
            # 1. 驗證 to_file_uri 基本轉換與行號
            uri_no_line = engine.to_file_uri("source/core/core/uri.py")
            self.assertTrue(uri_no_line.startswith("file:///"))
            self.assertIn("source/core/core/uri.py", uri_no_line)
            self.assertNotIn("#L", uri_no_line)

            uri_with_line = engine.to_file_uri("source/core/core/uri.py", line=42)
            self.assertTrue(uri_with_line.endswith("#L42"))

            # 2. 驗證 format_file_link 單行與跨行標籤 (純檔名+副檔名)
            link_single = engine.format_file_link("source/core/core/uri.py", line=10)
            self.assertTrue(link_single.startswith("["))
            self.assertIn("[uri.py:L10](file:///", link_single)
            self.assertTrue(link_single.endswith("#L10)"))

            link_range = engine.format_file_link("source/core/core/uri.py", line=10, end_line=25)
            self.assertIn("[uri.py:L10-25](file:///", link_range)
            self.assertTrue(link_range.endswith("#L10)"))

    @require(Requirement.LOGIC)
    def test_compute_dynamic_snippet_lines_curve(self):
        """驗證 compute_dynamic_snippet_lines 在 4 段階梯區間之動態行數計算 (12500 預算體系)"""
        from knowledge_db.engine import compute_dynamic_snippet_lines

        # 1. 0 ~ 5000 字元: 30 行
        self.assertEqual(compute_dynamic_snippet_lines(0), 30)
        self.assertEqual(compute_dynamic_snippet_lines(2500), 30)
        self.assertEqual(compute_dynamic_snippet_lines(4999), 30)

        # 2. 5000 ~ 9000 字元: 30 -> 10 行線性遞減
        self.assertEqual(compute_dynamic_snippet_lines(5000), 30)
        self.assertEqual(compute_dynamic_snippet_lines(7000), 20)
        self.assertEqual(compute_dynamic_snippet_lines(9000), 10)

        # 3. 9000 ~ 11000 字元: 10 行
        self.assertEqual(compute_dynamic_snippet_lines(10000), 10)
        self.assertEqual(compute_dynamic_snippet_lines(10999), 10)

        # 4. 11000 ~ 12500 字元: 0 行 (強制無切片)
        self.assertEqual(compute_dynamic_snippet_lines(11000), 0)
        self.assertEqual(compute_dynamic_snippet_lines(12000), 0)
        self.assertEqual(compute_dynamic_snippet_lines(12500), 0)

    @require(Requirement.LOGIC)
    def test_format_search_output_modes_and_budget(self):
        """FT-08: 驗證 format_search_output 之 simple, detail, auto, md 模式與 12500 字元預算及保底 5 項目守門"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            for i in range(1, 40):
                lines = [f"class ServiceNode{i}:", f"    '''Docstring for service node {i}'''"]
                for m in range(1, 15):
                    lines.append(f"    def run_method_{m}(self):\n        return {m} * {i}")
                (src_dir / f"mod_{i:02d}.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

            space_cfg = SpaceConfig(name="test_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                contributes_data={"spaces": {"test_space": space_cfg.to_dict()}},
            )

            results = engine.search("ServiceNode", space="test_space", limit=40, snippet=True)
            self.assertGreaterEqual(len(results), 10)

            # 1. Simple 模式
            out_simple = engine.format_search_output(results, query="ServiceNode", detail_mode="simple", snippet=False)
            self.assertIn("清單模式", out_simple)
            self.assertIn("CLASS: ServiceNode", out_simple)
            self.assertNotIn("命中詞:", out_simple)

            # 2. Detail 模式
            out_detail = engine.format_search_output(results, query="ServiceNode", detail_mode="detail", snippet=True)
            self.assertIn("詳細模式", out_detail)
            self.assertIn("簽名:", out_detail)
            self.assertIn("代碼切片", out_detail)

            # 3. Markdown 模式
            out_md = engine.format_search_output(results, query="ServiceNode", detail_mode="simple", format_type="md")
            self.assertIn("### 🔍 知識庫檢索: `ServiceNode`", out_md)
            self.assertIn("- **#01**", out_md)

            # 4. Limit=auto 自適應斷層與 12500 字元平滑預算守門，且至少包含 5 個檔案節點
            out_auto = engine.format_search_output(results, query="ServiceNode", detail_mode="detail", snippet=True, limit_mode="auto")
            self.assertIn("#05", out_auto)
            self.assertLessEqual(len(out_auto), 16000)  # 完成當前區塊後停止




