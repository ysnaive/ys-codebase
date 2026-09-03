"""test_roadmap.py — agents-workflow 模組 RoadmapManager 與 CLI roadmap 單元測試。
涵蓋 FT-01~03 與 ET-01 檢核維度。
"""
import sys
import os
import tempfile
import importlib.util
from pathlib import Path
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import require, Requirement

# 確保模組內部套件可引入
_pkg_root = Path(__file__).resolve().parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from agents_workflow.roadmap import RoadmapManager, RoadmapItem

# 確定性動態加載 agents-workflow 的 scripts/cli.py，防止沙盒多模組命名空間污染
_cli_path = _pkg_root / "scripts" / "cli.py"
_spec = importlib.util.spec_from_file_location("agents_workflow_cli", _cli_path)
_cli_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cli_module)
cmd_roadmap = _cli_module.cmd_roadmap


@require(Requirement.LOGIC)
class TestRoadmapManager(YSCBTestCase):
    """測試 RoadmapManager 與 RoadmapItem 核心能力。"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_roadmap_")
        self.roadmap_dir = Path(self.temp_dir) / "plans" / "roadmap"
        self.roadmap_dir.mkdir(parents=True, exist_ok=True)

    def test_empty_roadmap_directory(self):
        """EC-03: 目錄為空時安全返回空清單與友好提示。"""
        mgr = RoadmapManager(roadmap_dir=self.roadmap_dir)
        items = mgr.scan_roadmaps()
        self.assertEqual(len(items), 0)

        summary = mgr.format_summary_table(items)
        self.assertIn("目前無任何待啟動之 Roadmap 技術儲備", summary)

    def test_standard_roadmap_parsing(self):
        """FT-01: 標準 Roadmap 檔案 Header 與問題背景提取。"""
        doc_content = """# 技術路線圖：二進位發布包優化 (Roadmap)

> 主題：二進位發布包優化  
> 歸檔日期：2026-08-29  
> 狀態：Backlog  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在專案演進至第 100 個 Commit 時，.git 體積達 3.03 MiB。

### 1.2 核心根因
二進位 zip 無法計算 Delta Diff，造成 Git 歷史冗餘沉澱。

---

## 2. 候選架構方案對比 (Candidate Solutions)
"""
        file_path = self.roadmap_dir / "binary_optimization.md"
        file_path.write_text(doc_content, encoding="utf-8")

        mgr = RoadmapManager(roadmap_dir=self.roadmap_dir)
        items = mgr.scan_roadmaps()
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item.topic, "二進位發布包優化")
        self.assertEqual(item.status, "Backlog")
        self.assertEqual(item.date, "2026-08-29")
        self.assertTrue(item.has_valid_header)
        self.assertIn("在專案演進至第 100 個 Commit 時", item.problem_summary)
        self.assertIn("二進位 zip 無法計算 Delta Diff", item.problem_summary)

        # 測試 table 格式化
        table = mgr.format_summary_table(items)
        self.assertIn("二進位發布包優化", table)
        self.assertIn("Backlog", table)
        self.assertIn("2026-08-29", table)

        # 測試精確查找
        found = mgr.get_roadmap("二進位發布包優化")
        self.assertIsNotNone(found)
        self.assertEqual(found.filename, "binary_optimization.md")

    def test_non_standard_roadmap_fallback(self):
        """ET-01 / EC-04: 非標準格式自動 fallback 預覽不崩潰。"""
        doc_content = """# 自由構想備忘錄

這是一篇沒有標準引用標頭的長期技術筆記。
主要探討未來分散式快取的架構構想。
"""
        file_path = self.roadmap_dir / "free_idea.md"
        file_path.write_text(doc_content, encoding="utf-8")

        mgr = RoadmapManager(roadmap_dir=self.roadmap_dir)
        items = mgr.scan_roadmaps()
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item.topic, "free_idea")
        self.assertFalse(item.has_valid_header)
        self.assertIn("這是一篇沒有標準引用標頭的長期技術筆記", item.problem_summary)

    def test_cli_roadmap_invocation(self):
        """FT-02: 測試 CLI cmd_roadmap 分發。"""
        doc_content = """# 測試主題 (Roadmap)

> 主題：測試主題  
> 歸檔日期：2026-08-29  
> 狀態：Proposed  

## 1. 問題陳述
問題背景描述。
"""
        (self.roadmap_dir / "test_topic.md").write_text(doc_content, encoding="utf-8")

        ret = cmd_roadmap(["--list"])
        self.assertEqual(ret, 0)
