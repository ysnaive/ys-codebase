"""
Unit and Workflow Tests for knowledge-db KnowledgeEngine SDK Facade.
"""

import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_root = os.path.dirname(_test_dir)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require
from file_space import FileSpaceConfig, FileSpaceNotFoundError
from knowledge_db.engine import KnowledgeEngine
from knowledge_db.retrieval import SearchResult
from tests import write_text_and_advance_mtime


class TestEngine(YSCBTestCase):
    @require(Requirement.WORKFLOW)
    def test_engine_status_and_lifecycle(self):
        """驗證 KnowledgeEngine 門面 API 全生命週期操作"""
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

            space_cfg = FileSpaceConfig(name="demo_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={
                    "spaces": {"demo_space": space_cfg.to_dict()},
                },
            )

            # 1. status 驗證
            st = engine.status()
            self.assertEqual(st["total_spaces"], 1)
            self.assertIn("demo_space", st["spaces"])
            self.assertEqual(st["spaces"]["demo_space"]["cached_files"], 2)

            # 2. bundle 驗證
            bundles = engine.bundle(space="demo_space")
            self.assertEqual(len(bundles), 1)
            self.assertEqual(bundles[0].space_name, "demo_space")
            self.assertGreaterEqual(len(bundles[0].symbols), 2)

            # 3. build_index 驗證
            indices = engine.build_index(space="demo_space")
            self.assertIn("demo_space", indices)
            idx_file = storage_dir / "indices" / "demo_space.index.bin.gz"
            self.assertTrue(idx_file.exists())

            # 4. search 驗證
            results = engine.search("PIDController", space="demo_space")
            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0].items[0].symbol.name, "PIDController")

            # 5. clean 驗證 (清除索引並重置 knowledge-db 游標)
            engine.clean(space="demo_space")
            self.assertFalse(idx_file.exists())
            st_after = engine.status()
            self.assertFalse(st_after["has_unified_index"])

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_engine_search_and_lazy_indexing(self):
        """驗證未手動建置索引時 search 自動觸發懶建置 (Lazy Indexing)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            (src_dir / "motor.py").write_text("class MotorGroup: pass", encoding="utf-8")

            space_cfg = FileSpaceConfig(name="motor_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                contributes_data={"spaces": {"motor_space": space_cfg.to_dict()}},
            )

            results = engine.search("MotorGroup", space="motor_space")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].items[0].symbol.name, "MotorGroup")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_non_existent_space_error(self):
        """驗證操作不存在空間拋出 FileSpaceNotFoundError"""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = KnowledgeEngine(storage_dir=temp_dir)
            with self.assertRaises(FileSpaceNotFoundError):
                engine.status(space="non_existent_12345")

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_to_file_uri_and_formatting(self):
        """驗證 to_file_uri、format_file_link 與 TerminalStyler 色彩樣式控制"""
        from knowledge_db.formatter import TerminalStyler

        with tempfile.TemporaryDirectory() as temp_dir:
            engine = KnowledgeEngine(storage_dir=temp_dir)

            uri_no_line = engine.to_file_uri("source/core/core/uri.py")
            self.assertTrue(uri_no_line.startswith("file:///"))
            self.assertIn("source/core/core/uri.py", uri_no_line)
            self.assertNotIn("#L", uri_no_line)

            uri_with_line = engine.to_file_uri("source/core/core/uri.py", line=42)
            self.assertTrue(uri_with_line.endswith("#L42"))

            link_default_single = engine.format_file_link(
                "source/core/core/uri.py", line=10
            )
            self.assertEqual(link_default_single, "source/core/core/uri.py:L10")
            self.assertNotIn("file:///", link_default_single)

            link_default_range = engine.format_file_link(
                "source/core/core/uri.py", line=10, end_line=25
            )
            self.assertEqual(link_default_range, "source/core/core/uri.py:L10-25")

            link_single = engine.format_file_link(
                "source/core/core/uri.py", line=10, file_uri=True
            )
            self.assertTrue(link_single.startswith("["))
            self.assertIn("[uri.py:L10](file:///", link_single)
            self.assertTrue(link_single.endswith("#L10)"))

            link_range = engine.format_file_link(
                "source/core/core/uri.py", line=10, end_line=25, file_uri=True
            )
            self.assertIn("[uri.py:L10-25](file:///", link_range)
            self.assertTrue(link_range.endswith("#L10)"))

            # 驗證 TerminalStyler TTY 與 NO_COLOR 行為
            prev_no_color = os.environ.get("NO_COLOR")
            try:
                os.environ.pop("NO_COLOR", None)
                tty_stream = SimpleNamespace(isatty=lambda: True)
                styler_on = TerminalStyler(stream=tty_stream)
                self.assertTrue(styler_on.enabled)
                self.assertIn("\033[94m", styler_on.path("a.py"))
                self.assertIn("\033[92m", styler_on.symbol("Foo"))
                self.assertIn("\033[93m", styler_on.kind("CLASS"))
                self.assertIn("\033[96m", styler_on.line("(L1)"))
                self.assertIn("\033[1;93m", styler_on.warn("warn"))
                self.assertIn("\033[1;91m", styler_on.err("err"))
                self.assertIn("\033[1m", styler_on.bold("bold"))

                os.environ["NO_COLOR"] = "1"
                styler_off = TerminalStyler(stream=tty_stream)
                self.assertFalse(styler_off.enabled)
                self.assertEqual(styler_off.path("a.py"), "a.py")
            finally:
                if prev_no_color is None:
                    os.environ.pop("NO_COLOR", None)
                else:
                    os.environ["NO_COLOR"] = prev_no_color

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_compute_dynamic_snippet_lines_and_budget_decay(self):
        """驗證 8,000 字元預算上限與 compute_dynamic_snippet_lines 四段階梯平滑衰減計算"""
        from knowledge_db.formatter import (
            AUTO_BUDGET_CHARS,
            compute_dynamic_snippet_lines,
        )

        self.assertEqual(AUTO_BUDGET_CHARS, 8000)

        # < 3500 字元: 30 行
        self.assertEqual(compute_dynamic_snippet_lines(0), 30)
        self.assertEqual(compute_dynamic_snippet_lines(1000), 30)
        self.assertEqual(compute_dynamic_snippet_lines(2500), 30)
        self.assertEqual(compute_dynamic_snippet_lines(3499), 30)

        # 3500 ~ 6000 字元: 30 -> 10 線性平滑遞減
        self.assertEqual(compute_dynamic_snippet_lines(3500), 30)
        mid_val = compute_dynamic_snippet_lines(4750)
        self.assertEqual(mid_val, 20)
        self.assertEqual(compute_dynamic_snippet_lines(6000), 10)

        # 6000 ~ 7000 字元: 10 行
        self.assertEqual(compute_dynamic_snippet_lines(6500), 10)
        self.assertEqual(compute_dynamic_snippet_lines(6999), 10)

        # >= 7000 字元: 0 行
        self.assertEqual(compute_dynamic_snippet_lines(7000), 0)
        self.assertEqual(compute_dynamic_snippet_lines(7500), 0)
        self.assertEqual(compute_dynamic_snippet_lines(8000), 0)
        self.assertEqual(compute_dynamic_snippet_lines(8500), 0)

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_format_search_output_modes_and_budget(self):
        """驗證 format_search_output 之 simple, detail, auto, md 模式與 8,000 字元預算及保底 5 項目守門"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            for i in range(1, 15):
                lines = [
                    f"class ServiceNode{i}:",
                    f"    '''Docstring for service node {i} with detailed telemetry pipeline description and configuration parameters'''",
                ]
                for m in range(1, 28):
                    lines.append(
                        f"    def run_method_{m:02d}(self, payload_value_{m:02d}: int = {m * 100}, extra_param_{m:02d}: str = 'default_token_value_{m:02d}') -> int:"
                    )
                    lines.append(
                        f"        computed_step_{m:02d} = payload_value_{m:02d} * {i} + 1234567890123456789012345678901234567890"
                    )
                    lines.append(f"        return computed_step_{m:02d}")
                (src_dir / f"mod_{i:02d}.py").write_text(
                    "\n".join(lines) + "\n", encoding="utf-8"
                )

            space_cfg = FileSpaceConfig(name="test_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                contributes_data={"spaces": {"test_space": space_cfg.to_dict()}},
            )

            results = engine.search(
                "ServiceNode", space="test_space", limit=15, snippet=True
            )
            self.assertGreaterEqual(len(results), 10)

            out_simple = engine.format_search_output(
                results, query="ServiceNode", detail_mode="simple", snippet=False
            )
            self.assertIn("清單模式", out_simple)
            self.assertIn("CLASS: ServiceNode", out_simple)
            self.assertNotIn("命中詞:", out_simple)

            out_detail = engine.format_search_output(
                results, query="ServiceNode", detail_mode="detail", snippet=True
            )
            self.assertIn("詳細模式", out_detail)
            self.assertIn("簽名:", out_detail)
            self.assertIn("代碼切片", out_detail)

            out_md_simple = engine.format_search_output(
                results,
                query="ServiceNode",
                detail_mode="simple",
                format_type="md",
                snippet=True,
            )
            self.assertIn("###  知識庫檢索: `ServiceNode`", out_md_simple)
            self.assertIn("- **#01**", out_md_simple)

            out_md_detail = engine.format_search_output(
                results[:3],
                query="ServiceNode",
                detail_mode="detail",
                format_type="md",
                snippet=True,
            )
            self.assertIn("#### #01", out_md_detail)
            self.assertIn("**代碼切片**", out_md_detail)

            out_md_auto = engine.format_search_output(
                results,
                query="ServiceNode",
                detail_mode="auto",
                format_type="md",
                snippet=True,
                limit_mode="auto",
            )
            self.assertIn("- **#01**", out_md_auto)
            self.assertIn("已達 8000 字元自適應上限", out_md_auto)

            # 驗證 8,000 字元預算截斷與保底 5 個檔案節點 (#01 ~ #05 保留，#06 被截斷)
            out_auto = engine.format_search_output(
                results,
                query="ServiceNode",
                detail_mode="detail",
                snippet=True,
                limit_mode="auto",
            )
            self.assertIn("#01", out_auto)
            self.assertIn("#05", out_auto)
            self.assertNotIn("#06", out_auto)
            self.assertIn("已達 8000 字元自適應上限", out_auto)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_redundancy_filter(self):
        """驗證 UniversalRedundancyFilter 全域重複資訊剔除與保底防禦"""
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

        # 2. 驗證 C/C++/C# /* ... */ 區塊與 // 單行重疊註解剔除
        cpp_lines = [
            (1, "/* Single-line block comment */"),
            (2, "/**"),
            (3, " * Multi-line block comment"),
            (4, " */"),
            (5, "// 執行馬達PID閉迴路控制"),
            (6, "void runMotorControl() {"),
            (7, "    step();"),
            (8, "}"),
        ]
        purified_cpp = f.purify_lines(
            cpp_lines,
            target_line=6,
            symbol_name="runMotorControl",
            signature="void runMotorControl()",
            docstring_summary="執行馬達PID閉迴路控制",
            language="cpp",
        )
        cpp_nums = [ln for ln, _ in purified_cpp]
        self.assertNotIn(2, cpp_nums)
        self.assertNotIn(3, cpp_nums)
        self.assertNotIn(4, cpp_nums)
        self.assertNotIn(5, cpp_nums)
        self.assertIn(6, cpp_nums)
        self.assertIn(7, cpp_nums)

        # 3. 驗證 Markdown 重疊 # Heading 剔除
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
        self.assertNotIn(20, md_nums)
        self.assertIn(21, md_nums)
        self.assertIn(22, md_nums)

        # 4. 驗證 License 樣板與連續空行剔除
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
        empty_count = sum(1 for _, txt in purified_lic if not txt.strip())
        self.assertLessEqual(empty_count, 1)

        # 5. 保底驗證：若切片全為被過濾項，保底保留 target_line
        only_doc = [
            (10, '"""'),
            (11, "純文件無代碼"),
            (12, '"""'),
        ]
        fallback = f.purify_lines(
            only_doc, target_line=10, docstring_summary="純文件無代碼"
        )
        self.assertGreaterEqual(len(fallback), 1)

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_indexing_pipeline_delegation(self):
        """驗證 IndexingPipeline 與 KnowledgeEngine 門面解耦委派"""
        from knowledge_db.formatter import ResultFormatter
        from knowledge_db.pipeline import IndexingPipeline

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            (src_dir / "service.py").write_text(
                "class PipelineService:\n    def execute(self): return 42\n",
                encoding="utf-8",
            )

            space_cfg = FileSpaceConfig(name="pipe_space", include=[str(src_dir)])
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

            # 驗證 callers/callees/impact 已移交至 module:ast，不再留存於 KnowledgeEngine
            self.assertFalse(hasattr(engine, "callers"))
            self.assertFalse(hasattr(engine, "callees"))
            self.assertFalse(hasattr(engine, "impact"))
            self.assertIsNotNone(engine.ast_engine)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_config_loading_priority(self):
        """驗證 KnowledgeDBConfig 載入優先級：core.config > local_config > yscb.config.local > yscb.config > project_config"""
        from knowledge_db.config import KnowledgeDBConfig

        # 1. project_config 覆蓋預設值
        cfg1 = KnowledgeDBConfig.load(
            project_config={
                "knowledge-db": {"enable_vector_search": False, "max_threads": 4}
            }
        )
        self.assertFalse(cfg1.enable_vector_search)
        self.assertEqual(cfg1.max_threads, 4)

        # 2. local_config 覆蓋 project_config
        cfg2 = KnowledgeDBConfig.load(
            project_config={
                "knowledge-db": {"enable_vector_search": False, "max_threads": 4}
            },
            local_config={
                "knowledge-db": {
                    "enable_vector_search": True,
                    "jit_vector_timeout_ms": 1800,
                    "vector_batch_size": 16,
                }
            },
        )
        self.assertTrue(cfg2.enable_vector_search)
        self.assertEqual(cfg2.max_threads, 4)
        self.assertEqual(cfg2.jit_vector_timeout_ms, 1800)
        self.assertAlmostEqual(cfg2.jit_vector_timeout_seconds, 1.8)
        self.assertEqual(cfg2.vector_batch_size, 16)

        # 3. 預設 jit_vector_timeout_ms 為 3000，並向下相容 jit_vector_timeout_seconds
        cfg_default = KnowledgeDBConfig()
        self.assertEqual(cfg_default.jit_vector_timeout_ms, 3000)
        self.assertAlmostEqual(cfg_default.jit_vector_timeout_seconds, 3.0)

        cfg_legacy = KnowledgeDBConfig.from_dict({"jit_vector_timeout_seconds": 4.5})
        self.assertEqual(cfg_legacy.jit_vector_timeout_ms, 4500)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_status_detailed_metrics_and_docstring_truncation(self):
        """驗證 engine.status() 詳細結構化指標與 Docstring 截斷"""
        from knowledge_db.embedding import format_symbol_embedding_text
        from knowledge_db.schema import UnifiedSymbol

        long_doc = "A" * 2500
        sym = UnifiedSymbol(
            id="s1",
            name="LongDocSymbol",
            kind="class",
            file_path="src/a.py",
            line_number=1,
            signature="class LongDocSymbol:",
            docstring=long_doc,
            language="python",
        )
        emb_txt = format_symbol_embedding_text(sym, max_doc_chars=1000)
        self.assertLessEqual(len(emb_txt), 1050)
        self.assertIn("LongDocSymbol", emb_txt)

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"
            (src_dir / "mod.py").write_text(
                "def alpha():\n    beta()\n\ndef beta():\n    return 1\n",
                encoding="utf-8",
            )
            sp = FileSpaceConfig(name="main_sp", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main_sp": sp.to_dict()}},
                embedding_mock_mode=True,
            )
            engine.build_unified_index(force=True)
            st = engine.status()

            self.assertIn("worker", st)
            self.assertEqual(st["worker"]["busy_elapsed_ms"], 0)
            self.assertIn("indices", st)
            self.assertGreaterEqual(st["indices"]["bm25"]["symbol_count"], 2)
            self.assertGreaterEqual(st["indices"]["bm25"]["term_count"], 2)
            self.assertNotIn("graph", st["indices"])
            self.assertGreaterEqual(st["ast_generation"], 1)
            self.assertEqual(st["acked_ast_generation"], st["ast_generation"])
            self.assertEqual(st["indices"]["vector"]["coverage_pct"], 100.0)
            self.assertEqual(st["indices"]["vector"]["missing_count"], 0)
            self.assertEqual(st["retrieval_mode"], "hybrid_rrf")
            self.assertEqual(st["jit_vector_timeout_ms"], 3000)
            self.assertIn("main_sp", st["spaces"])
            self.assertGreater(st["spaces"]["main_sp"]["head_generation"], 0)
            self.assertEqual(
                st["spaces"]["main_sp"]["acked_generation"],
                st["spaces"]["main_sp"]["head_generation"],
            )
            self.assertTrue(st["spaces"]["main_sp"]["in_sync"])

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_meta_adaptive_limit_and_status_snapshot(self):
        """驗證 status 輕量讀取 unified.meta.json 與 snap_state.entries，以及 adaptive_limit 斷層預裁切"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            (src_dir / "top_hit.py").write_text(
                "class ExactTargetAlpha:\n"
                "    '''ExactTargetAlpha ExactTargetAlpha ExactTargetAlpha'''\n"
                "    def run_alpha(self):\n"
                "        return 'ExactTargetAlpha'\n",
                encoding="utf-8",
            )
            for idx in range(1, 8):
                (src_dir / f"weak_{idx}.py").write_text(
                    f"class OtherNode{idx}:\n"
                    f"    '''mentions ExactTargetAlpha once in docstring {idx}'''\n",
                    encoding="utf-8",
                )

            space_cfg = FileSpaceConfig(name="opt_space", include=[str(src_dir)])
            engine = KnowledgeEngine(
                storage_dir=temp_path / "storage",
                contributes_data={"spaces": {"opt_space": space_cfg.to_dict()}},
            )

            # 建置索引並確認 unified.meta.json 生成
            engine.build_unified_index(force=True)
            self.assertTrue(engine.ast_engine.meta_index_path.exists())

            # 驗證 status() 優先從 snap_state.entries 讀取檔案數，不觸發 iter_space_files 磁碟遍歷
            with patch.object(
                engine.space_manager,
                "iter_space_files",
                side_effect=AssertionError("Should not walk disk"),
            ) as mock_walk:
                st = engine.status(space="opt_space")
                self.assertEqual(st["spaces"]["opt_space"]["cached_files"], 8)
                self.assertGreaterEqual(st["ast_generation"], 1)
                mock_walk.assert_not_called()

            # 驗證 adaptive_limit=True 於相對斷層處預先截斷低分長尾
            res_full = engine.search(
                "ExactTargetAlpha", space="opt_space", limit=20, adaptive_limit=False
            )
            res_adapt = engine.search(
                "ExactTargetAlpha", space="opt_space", limit=20, adaptive_limit=True
            )
            self.assertGreaterEqual(len(res_full), 5)
            self.assertLessEqual(len(res_adapt), len(res_full))
            self.assertGreaterEqual(len(res_adapt), 3)

        self.mark_passed()

    @require(Requirement.LOGIC)
    def test_worker_cold_start_watermark_and_multi_space_bundle_export(self):
        """驗證 KnowledgeDBServiceWorker 冷啟動載入 unified_index 檢出雙水位線落差，以及多空間 bundle 導出不互相覆寫。"""
        from knowledge_db.service import KnowledgeDBServiceWorker

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            sp_a_dir = temp_path / "sp_a"
            sp_b_dir = temp_path / "sp_b"
            sp_a_dir.mkdir(parents=True)
            sp_b_dir.mkdir(parents=True)
            (sp_a_dir / "mod_a.py").write_text(
                "def func_a():\n    return 1\n", encoding="utf-8"
            )
            (sp_b_dir / "mod_b.py").write_text(
                "def func_b():\n    return 2\n", encoding="utf-8"
            )

            contributes = {
                "spaces": {
                    "sp_a": FileSpaceConfig(
                        name="sp_a", include=[str(sp_a_dir)]
                    ).to_dict(),
                    "sp_b": FileSpaceConfig(
                        name="sp_b", include=[str(sp_b_dir)]
                    ).to_dict(),
                }
            }
            storage_dir = temp_path / "storage"
            eng1 = KnowledgeEngine(storage_dir=storage_dir, contributes_data=contributes)
            eng1.build_unified_index(force=True)

            # 模擬 AST 快照推進至更高代次，但磁碟 unified.index.bin.gz 的 acked_ast_generation 仍停留在舊值
            indices_dir = eng1.pipeline.get_indices_dir()
            bin_file = indices_dir / "unified.index.bin.gz"
            eng1.pipeline.unified_index.acked_ast_generation = 0
            eng1.pipeline.unified_index.save_binary(bin_file)

            # 全新冷啟動引擎（unified_index 尚未載入記憶體）由 Worker 檢查水位線
            eng_cold = KnowledgeEngine(
                storage_dir=storage_dir, contributes_data=contributes
            )
            self.assertIsNone(eng_cold.pipeline.unified_index)
            worker = KnowledgeDBServiceWorker(context={"project_root": str(temp_path)})
            worker._engine = eng_cold
            self.assertTrue(
                worker._has_pending_space_work(
                    eng_cold, eng_cold.pipeline.get_indices_dir()
                )
            )

            # 驗證多空間 bundle(space=None, export_path=...) 派生獨立檔名不覆寫
            export_base = temp_path / "exports" / "bundle_out.json"
            bundle_res = eng1.bundle(space=None, export_path=export_base)
            bundled_spaces = [b.space_name for b in bundle_res]
            self.assertIn("sp_a", bundled_spaces)
            self.assertIn("sp_b", bundled_spaces)
            exp_a = temp_path / "exports" / "bundle_out_sp_a.json"
            exp_b = temp_path / "exports" / "bundle_out_sp_b.json"
            self.assertTrue(exp_a.exists())
            self.assertTrue(exp_b.exists())
            self.assertNotEqual(
                exp_a.read_text(encoding="utf-8"), exp_b.read_text(encoding="utf-8")
            )

        self.mark_passed()

    @require(Requirement.WORKFLOW)
    def test_vector_probe_over_ten_symbols_and_timeout_degradation(self):
        """驗證 > 10 個符號熱修補之動態探針雙階段向量合併、超時熔斷降級與 aggregate=False 切片回填"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            src_dir = temp_path / "src"
            src_dir.mkdir(parents=True)
            storage_dir = temp_path / "storage"

            target_py = src_dir / "bulk_symbols.py"
            target_py.write_text(
                "def initial_func():\n    return 0\n", encoding="utf-8"
            )

            sp = FileSpaceConfig(name="main", include=[str(src_dir)])
            engine = KnowledgeEngine(
                project_root=temp_path,
                storage_dir=storage_dir,
                contributes_data={"spaces": {"main": sp.to_dict()}},
                embedding_mock_mode=True,
            )
            engine.build_unified_index(force=True)

            # 1. 修改檔案使其包含 15 個符號 (> 10)，觸發 embed_texts_probe + 剩餘 5 筆 vstack 合併
            many_funcs = "\n".join(
                f"def bulk_symbol_{i:02d}(val: int = {i}) -> int:\n"
                f"    '''Bulk symbol docstring {i}'''\n"
                f"    return val + {i}\n"
                for i in range(15)
            )
            write_text_and_advance_mtime(target_py, many_funcs)

            with engine.scanner.consume_diff(consumer_id="knowledge-db") as diff_res:
                patch_res = engine.pipeline.hot_patch_unified_index(
                    diff_res.detail, timeout_seconds=10.0
                )
            self.assertTrue(patch_res.success)
            self.assertFalse(patch_res.vector_degraded)
            self.assertEqual(len(engine.pipeline.hybrid_engine.vector_index.doc_ids), 15)

            # 2. 模擬探針預估耗時超出 timeout_seconds -> 觸發熔斷降級 vector_degraded=True
            more_funcs = many_funcs + "\ndef bulk_symbol_extra():\n    return 99\n"
            write_text_and_advance_mtime(target_py, more_funcs)
            orig_probe = engine.embedding_service.embed_texts_probe

            def _slow_probe(texts, probe_size=10, total_count=None):
                vecs, _ = orig_probe(texts, probe_size=probe_size, total_count=16)
                return vecs, 9.9

            with patch.object(
                engine.embedding_service, "embed_texts_probe", side_effect=_slow_probe
            ):
                with engine.scanner.consume_diff(
                    consumer_id="knowledge-db"
                ) as diff_res2:
                    patch_deg = engine.pipeline.hot_patch_unified_index(
                        diff_res2.detail, timeout_seconds=0.05
                    )
            self.assertTrue(patch_deg.success)
            self.assertTrue(patch_deg.vector_degraded)
            self.assertIn("已熔斷降級", patch_deg.degrade_notice or "")

            # 3. 驗證 aggregate=False 且 snippet=True 回傳原始 SearchResult 清單並附帶 code_snippet
            raw_results = engine.search(
                "bulk_symbol_01",
                space="main",
                aggregate=False,
                snippet=True,
                auto_rebuild=False,
            )
            self.assertGreaterEqual(len(raw_results), 1)
            self.assertIsInstance(raw_results[0], SearchResult)
            self.assertIsNotNone(raw_results[0].code_snippet)
            self.assertGreater(len(raw_results[0].code_snippet.lines), 0)

        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
