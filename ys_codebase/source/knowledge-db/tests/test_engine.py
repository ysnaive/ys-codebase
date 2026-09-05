"""
Unit and Workflow Tests for knowledge-db KnowledgeEngine SDK Facade.
"""

import os
from pathlib import Path
import sys
import tempfile
import unittest

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
    @require(Requirement.WORKFLOW)
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

        self.mark_passed()

    @require(Requirement.WORKFLOW)
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

            results = engine.search("MotorGroup", space="motor_space")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].symbol.name, "MotorGroup")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_non_existent_space_error(self):
        """ET-01: 驗證操作不存在空間拋出 SpaceNotFoundError (EC-02)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = KnowledgeEngine(storage_dir=temp_dir)
            with self.assertRaises(SpaceNotFoundError):
                engine.scan(space="non_existent_12345")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_ft_07_to_file_uri_and_formatting(self):
        """FT-07: 驗證 to_file_uri 與 format_file_link 生成標準 RFC 8089 URI 與 Markdown 標籤"""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = KnowledgeEngine(storage_dir=temp_dir)

            uri_no_line = engine.to_file_uri("source/core/core/uri.py")
            self.assertTrue(uri_no_line.startswith("file:///"))
            self.assertIn("source/core/core/uri.py", uri_no_line)
            self.assertNotIn("#L", uri_no_line)

            uri_with_line = engine.to_file_uri("source/core/core/uri.py", line=42)
            self.assertTrue(uri_with_line.endswith("#L42"))

            link_single = engine.format_file_link("source/core/core/uri.py", line=10)
            self.assertTrue(link_single.startswith("["))
            self.assertIn("[uri.py:L10](file:///", link_single)
            self.assertTrue(link_single.endswith("#L10)"))

            link_range = engine.format_file_link("source/core/core/uri.py", line=10, end_line=25)
            self.assertIn("[uri.py:L10-25](file:///", link_range)
            self.assertTrue(link_range.endswith("#L10)"))

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_compute_dynamic_snippet_lines_curve(self):
        """驗證 compute_dynamic_snippet_lines 在 4 段階梯區間之動態行數計算 (8000 預算體系)"""
        from knowledge_db.engine import compute_dynamic_snippet_lines

        self.assertEqual(compute_dynamic_snippet_lines(0), 30)
        self.assertEqual(compute_dynamic_snippet_lines(2500), 30)
        self.assertEqual(compute_dynamic_snippet_lines(3499), 30)

        self.assertEqual(compute_dynamic_snippet_lines(3500), 30)
        self.assertEqual(compute_dynamic_snippet_lines(4750), 20)
        self.assertEqual(compute_dynamic_snippet_lines(6000), 10)

        self.assertEqual(compute_dynamic_snippet_lines(6500), 10)
        self.assertEqual(compute_dynamic_snippet_lines(6999), 10)

        self.assertEqual(compute_dynamic_snippet_lines(7000), 0)
        self.assertEqual(compute_dynamic_snippet_lines(7500), 0)
        self.assertEqual(compute_dynamic_snippet_lines(8000), 0)

        self.mark_passed()

    @require(Requirement.WORKFLOW)
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

            out_simple = engine.format_search_output(results, query="ServiceNode", detail_mode="simple", snippet=False)
            self.assertIn("清單模式", out_simple)
            self.assertIn("CLASS: ServiceNode", out_simple)
            self.assertNotIn("命中詞:", out_simple)

            out_detail = engine.format_search_output(results, query="ServiceNode", detail_mode="detail", snippet=True)
            self.assertIn("詳細模式", out_detail)
            self.assertIn("簽名:", out_detail)
            self.assertIn("代碼切片", out_detail)

            out_md = engine.format_search_output(results, query="ServiceNode", detail_mode="simple", format_type="md")
            self.assertIn("### 🔍 知識庫檢索: `ServiceNode`", out_md)
            self.assertIn("- **#01**", out_md)

            out_auto = engine.format_search_output(results, query="ServiceNode", detail_mode="detail", snippet=True, limit_mode="auto")
            self.assertIn("#05", out_auto)
            self.assertLessEqual(len(out_auto), 10000)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_redundancy_filter(self):
        """FT-01: 驗證 UniversalRedundancyFilter 全域重複資訊剔除與保底防禦"""
        from knowledge_db.formatter import UniversalRedundancyFilter

        f = UniversalRedundancyFilter()

        # 1. 驗證 Python Docstring 區塊剔除
        py_lines = [
            (10, "def calculate_velocity(mass, acceleration):"),
            (11, '    """'),
            (12, "    計算牛頓第二運動定律速度向量。"),
            (13, '    """'),
            (14, "    force = mass * acceleration"),
            (15, "    return force"),
        ]
        purified_py = f.purify_lines(
            py_lines,
            target_line=10,
            symbol_name="calculate_velocity",
            signature="def calculate_velocity(mass, acceleration)",
            docstring_summary="計算牛頓第二運動定律速度向量。",
            language="python",
        )
        line_nums = [ln for ln, _ in purified_py]
        self.assertIn(10, line_nums)
        self.assertIn(14, line_nums)
        self.assertIn(15, line_nums)
        self.assertNotIn(11, line_nums)
        self.assertNotIn(12, line_nums)
        self.assertNotIn(13, line_nums)

        # 2. 驗證 Markdown 重疊 # Heading 剔除
        md_lines = [
            (20, "## 快速上手手冊"),
            (21, "本手冊引導您如何初始化與調用引擎。"),
            (22, "### 基本設定"),
            (23, "請確認 storage 目錄存在。"),
        ]
        purified_md = f.purify_lines(
            md_lines,
            target_line=20,
            symbol_name="快速上手手冊",
            signature="## 快速上手手冊",
            language="markdown",
        )
        md_nums = [ln for ln, _ in purified_md]
        self.assertNotIn(20, md_nums)  # 標頭與名稱重疊，應剔除
        self.assertIn(21, md_nums)
        self.assertIn(22, md_nums)

        # 3. 驗證 License 樣板與連續空行剔除
        lic_lines = [
            (1, "# SPDX-License-Identifier: MIT"),
            (2, "# Copyright (c) 2026 DeepMind Robotics"),
            (3, ""),
            (4, ""),
            (5, ""),
            (6, "class RobotBase: pass"),
        ]
        purified_lic = f.purify_lines(
            lic_lines,
            target_line=6,
            symbol_name="RobotBase",
            language="python",
        )
        lic_nums = [ln for ln, _ in purified_lic]
        self.assertNotIn(1, lic_nums)
        self.assertNotIn(2, lic_nums)
        self.assertIn(6, lic_nums)
        # 連續空行最多保留 1 行
        empty_count = sum(1 for _, txt in purified_lic if not txt.strip())
        self.assertLessEqual(empty_count, 1)

        # 4. EC-05 保底驗證：若切片全為被過濾項，保底保留 target_line
        only_doc = [
            (10, '"""'),
            (11, "純文件無代碼"),
            (12, '"""'),
        ]
        fallback = f.purify_lines(only_doc, target_line=10, docstring_summary="純文件無代碼")
        self.assertGreaterEqual(len(fallback), 1)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_8000_char_budget_decay(self):
        """FT-02: 驗證 8,000 字元預算上限與平滑衰減計算器"""
        from knowledge_db.formatter import AUTO_BUDGET_CHARS, compute_dynamic_snippet_lines

        self.assertEqual(AUTO_BUDGET_CHARS, 8000)

        # < 3500 字元: 30 行
        self.assertEqual(compute_dynamic_snippet_lines(1000), 30)
        self.assertEqual(compute_dynamic_snippet_lines(3499), 30)

        # 3500 ~ 6000 字元: 30 -> 10 線性平滑遞減
        mid_val = compute_dynamic_snippet_lines(4750)
        self.assertGreater(mid_val, 10)
        self.assertLess(mid_val, 30)

        # 6000 ~ 7000 字元: 10 行
        self.assertEqual(compute_dynamic_snippet_lines(6000), 10)
        self.assertEqual(compute_dynamic_snippet_lines(6999), 10)

        # >= 7000 字元: 0 行
        self.assertEqual(compute_dynamic_snippet_lines(7000), 0)
        self.assertEqual(compute_dynamic_snippet_lines(8500), 0)

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_indexing_pipeline_delegation(self):
        """FT-04: 驗證 IndexingPipeline 與 KnowledgeEngine 門面解耦委派"""
        from knowledge_db.pipeline import IndexingPipeline
        from knowledge_db.formatter import ResultFormatter

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            (src_dir / "service.py").write_text("class PipelineService:\n    def execute(self): return 42\n", encoding="utf-8")

            space_cfg = SpaceConfig(name="pipe_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                contributes_data={"spaces": {"pipe_space": space_cfg.to_dict()}},
            )

            self.assertIsInstance(engine.pipeline, IndexingPipeline)
            self.assertIsInstance(engine.formatter, ResultFormatter)

            # 驗證 pipeline build_unified_index
            idx = engine.build_unified_index(force=True)
            self.assertIsNotNone(idx)
            self.assertIn("PipelineService", [s.name for s in idx.symbols.values()])

            # 驗證 search 委派正常
            results = engine.search("PipelineService", space="pipe_space")
            self.assertGreaterEqual(len(results), 1)

            # 驗證 callers/callees/impact 委派正常
            callers_res = engine.act_callers("PipelineService")
            self.assertIn("callers", callers_res)

            callees_res = engine.act_callees("PipelineService")
            self.assertIn("callees", callees_res)

            impact_res = engine.act_impact("PipelineService")
            self.assertIn("layers", impact_res)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()

