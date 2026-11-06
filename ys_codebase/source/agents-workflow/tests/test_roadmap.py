"""test_roadmap.py — agents-workflow 模組 RoadmapManager、TodoManager 與 CLI roadmap/todo 單元測試。"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if getattr(sys.modules.get("tests"), "PKG_ROOT", None) != Path(__file__).resolve().parent.parent:
    sys.modules.pop("tests", None)

from tests import load_cli_module

_cli_module = load_cli_module("agents_workflow_cli_roadmap_test")
cmd_roadmap = _cli_module.roadmap
cmd_todo = _cli_module.todo

from agents_workflow.roadmap import RoadmapManager, TodoManager
from dev.testing.case import YSCBTestCase
from dev.testing.requirement import Requirement, require


@require(Requirement.LOGIC | Requirement.ENV)
class TestRoadmapManager(YSCBTestCase):
    """測試 RoadmapManager、TodoManager 與 CLI 複合入口核心能力。"""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="test_aw_roadmap_")
        self.plans_dir = Path(self.temp_dir) / "plans"
        self.roadmap_dir = self.plans_dir / "roadmap"
        self.roadmap_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_empty_roadmap_directory(self):
        """驗證目錄為空時安全返回空清單與友好提示。"""
        mgr = RoadmapManager(roadmap_dir=self.roadmap_dir)
        items = mgr.scan_roadmaps()
        self.assertEqual(len(items), 0)

        summary = mgr.format_summary_table(items)
        self.assertIn("目前無任何待啟動之 Roadmap 技術儲備", summary)
        self.mark_passed()

    def test_standard_roadmap_parsing(self):
        """驗證標準 Roadmap 檔案 Header、問題背景與長期願景摘要提取。"""
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

        table = mgr.format_summary_table(items)
        self.assertIn("二進位發布包優化", table)
        self.assertIn("Backlog", table)
        self.assertIn("2026-08-29", table)

        found = mgr.get_roadmap("二進位發布包優化")
        self.assertIsNotNone(found)
        self.assertEqual(found.filename, "binary_optimization.md")

        v11_doc = """# 技術路線圖：宣告式視覺化宿主 (Roadmap)

> 主題：gui_kit_host  
> 歸檔日期：2026-10-30  
> 狀態：Backlog  
> 目標範疇：module:gui-kit  
> 前置解鎖條件：結構化輸出契約就緒  
> 模型：Unknown  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：高資訊密度場景下純終端機存在認知瓶頸。
"""
        (self.roadmap_dir / "gui_kit_host.md").write_text(v11_doc, encoding="utf-8")
        v11_item = mgr.get_roadmap("gui_kit_host")
        self.assertIsNotNone(v11_item)
        self.assertIn("高資訊密度場景下純終端機存在認知瓶頸", v11_item.problem_summary)
        self.assertIsNone(mgr.get_roadmap(""))
        self.assertIsNone(mgr.get_roadmap("TODO.md"))
        self.assertIsNotNone(mgr.get_roadmap("binary_opt"))
        self.mark_passed()

    def test_non_standard_roadmap_fallback(self):
        """驗證非標準格式自動 fallback 預覽不崩潰。"""
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
        self.mark_passed()

    def test_cli_roadmap_and_todo_invocation(self):
        """驗證 CLI roadmap 與 todo 各子命令分發（隔離至測試沙盒並驗證實際輸出）。"""
        doc_content = """# 測試主題 (Roadmap)

> 主題：測試主題  
> 歸檔日期：2026-08-29  
> 狀態：Proposed  

## 1. 問題陳述
問題背景描述。
"""
        (self.roadmap_dir / "test_topic.md").write_text(doc_content, encoding="utf-8")

        def _make_roadmap_mgr(*args, **kwargs):
            return RoadmapManager(roadmap_dir=self.roadmap_dir, plans_dir=self.plans_dir)

        def _make_todo_mgr(*args, **kwargs):
            return TodoManager(roadmap_dir=self.roadmap_dir, plans_dir=self.plans_dir)

        with mock.patch.object(_cli_module, "RoadmapManager", side_effect=_make_roadmap_mgr), mock.patch.object(
            _cli_module, "TodoManager", side_effect=_make_todo_mgr
        ):
            buf_list = io.StringIO()
            with redirect_stdout(buf_list):
                self.assertEqual(cmd_roadmap(["--list"]), 0)
                self.assertEqual(cmd_roadmap(["list", "--status", "Proposed"]), 0)
            self.assertIn("測試主題", buf_list.getvalue())
            self.assertIn("Proposed", buf_list.getvalue())

            buf_detail = io.StringIO()
            with redirect_stdout(buf_detail):
                self.assertEqual(cmd_roadmap(["test_topic"]), 0)
                self.assertEqual(cmd_roadmap(["non_existent_topic"]), 1)
            self.assertIn("Topic: 測試主題 (Proposed)", buf_detail.getvalue())
            self.assertIn("not found", buf_detail.getvalue())

            buf_prom = io.StringIO()
            with redirect_stdout(buf_prom):
                self.assertEqual(cmd_roadmap(["promote"]), 1)
                self.assertEqual(cmd_roadmap(["promote", "non_existent_topic"]), 1)
                self.assertEqual(cmd_roadmap(["promote", "test_topic", "--model", "TestModel"]), 0)
            self.assertIn("[SUCCESS]", buf_prom.getvalue())

            buf_todo = io.StringIO()
            with redirect_stdout(buf_todo):
                self.assertEqual(cmd_todo([]), 0)
                self.assertEqual(cmd_todo(["add"]), 1)
                self.assertEqual(cmd_todo(["add", "CLI 待辦測試", "--scope", "agents-workflow", "--note", "備註"]), 0)
                self.assertEqual(cmd_todo(["list", "--scope", "agents-workflow"]), 0)
                self.assertEqual(cmd_todo(["promote"]), 1)
                self.assertEqual(cmd_todo(["promote", "TODO-99", "--slug", "bad_todo"]), 1)
                self.assertEqual(cmd_todo(["promote", "TODO-01", "--slug", "cli_todo_promoted"]), 0)
                self.assertEqual(cmd_todo(["unknown_action"]), 1)
            todo_out = buf_todo.getvalue()
            self.assertIn("已追加待辦條目 [TODO-01]", todo_out)
            self.assertIn("已完成待辦原子拔除並遷入計畫目錄", todo_out)
            self.assertIn("Unknown todo action", todo_out)
        self.mark_passed()

    def test_promote_roadmap_append_when_already_exists(self):
        """驗證多路線圖合流遷入同一計畫目錄時無損追加合併與無效目標目錄阻斷。"""
        r1_content = "# 路線圖一 (Roadmap)\n\n> 主題：路線圖一  \n> 狀態：Ready  \n\n內容一"
        r2_content = "# 路線圖二 (Roadmap)\n\n> 主題：路線圖二  \n> 狀態：Ready  \n\n內容二"
        (self.roadmap_dir / "r1.md").write_text(r1_content, encoding="utf-8")
        (self.roadmap_dir / "r2.md").write_text(r2_content, encoding="utf-8")

        mgr = RoadmapManager(roadmap_dir=self.roadmap_dir, plans_dir=self.plans_dir)
        bad_target = mgr.promote_roadmap("r1", target_plan="non_existent_target_plan")
        self.assertFalse(bad_target["success"])
        self.assertTrue((self.roadmap_dir / "r1.md").exists())

        res1 = mgr.promote_roadmap("r1", model="TestModel")
        self.assertTrue(res1["success"])
        self.assertFalse(res1["is_appended"])
        plan_dir = res1["plan_dir"]
        self.assertTrue((plan_dir / "roadmap.md").is_file())
        self.assertFalse((self.roadmap_dir / "r1.md").exists())

        res2 = mgr.promote_roadmap("r2", model="TestModel", target_plan=plan_dir)
        self.assertTrue(res2["success"])
        self.assertTrue(res2["is_appended"])
        self.assertFalse((self.roadmap_dir / "r2.md").exists())

        combined_text = (plan_dir / "roadmap.md").read_text(encoding="utf-8")
        self.assertIn("路線圖一", combined_text)
        self.assertIn("路線圖二", combined_text)
        self.assertIn("內容一", combined_text)
        self.assertIn("內容二", combined_text)
        self.mark_passed()

    def test_todo_add_and_monotonic_id(self):
        """驗證 todo add 免讀盲寫追加、空白標題防呆與最後分配編號單調遞增防碰撞。"""
        roadmap_dir = self.plans_dir / "roadmap_todo"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        with self.assertRaises(ValueError):
            mgr.add_todo(title="   ")

        r1 = mgr.add_todo(title="清理 compiler 死代碼", scope="agents-workflow", note="模組整理")
        self.assertEqual(r1.todo_id, "TODO-01")

        r2 = mgr.add_todo(title="補充 CLI 範例", scope="core", note="補充文檔")
        self.assertEqual(r2.todo_id, "TODO-02")

        content = mgr.todo_file.read_text(encoding="utf-8")
        self.assertIn("> 最後分配編號：2", content)

        pop_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-02"],
            slug="cleanup_batch",
            model="Unknown",
        )
        self.assertTrue(pop_res["success"])
        self.assertEqual(len(mgr.list_todos()), 0)

        self.assertEqual(TodoManager.normalize_todo_id("1"), "TODO-01")
        self.assertEqual(TodoManager.normalize_todo_id("todo-2"), "TODO-02")
        self.assertEqual(TodoManager.normalize_todo_id("[TODO-03]"), "TODO-03")
        self.assertIsNone(TodoManager.normalize_todo_id("invalid"))
        self.assertIsNone(TodoManager.normalize_todo_id("0"))

        r3 = mgr.add_todo(title="提取清空後之新條目", scope="global", note="驗證單調遞增")
        self.assertEqual(r3.todo_id, "TODO-03")
        self.mark_passed()

    def test_todo_list_and_scope_filter(self):
        """驗證 todo list 空帳本優雅返回、舊版無編號標頭相容與 --scope 過濾。"""
        roadmap_dir = self.plans_dir / "roadmap_empty"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        self.assertEqual(mgr.list_todos(), [])
        self.assertIn("目前尚無活躍之輕量待辦項目", mgr.format_todo_table())
        self.assertFalse(mgr.todo_file.exists())

        no_ledger_prom = mgr.promote_todos(todo_ids=["TODO-01"], slug="no_ledger")
        self.assertFalse(no_ledger_prom["success"])

        # 模擬舊版缺少 '> 最後分配編號：' 之 TODO.md
        roadmap_dir.mkdir(parents=True, exist_ok=True)
        mgr.todo_file.write_text("# 舊帳本\n> 狀態：Active\n\n## 待辦清單\n", encoding="utf-8")

        mgr.add_todo(title="Item A", scope="agents-workflow", note="TechDebt")
        mgr.add_todo(title="Item B", scope="knowledge-db", note="Polish")
        mgr.add_todo(title="Item C", scope="agents-workflow", note="Idea")

        aw_items = mgr.list_todos(scope_keyword="agents-workflow")
        self.assertEqual(len(aw_items), 2)
        polish_items = mgr.list_todos(scope_keyword="Polish")
        self.assertEqual(len(polish_items), 1)
        self.assertEqual(polish_items[0].todo_id, "TODO-02")
        self.assertIn("TODO-02", mgr.format_todo_table(polish_items))
        self.mark_passed()

    def test_todo_promote_batch_and_seeded_dir(self):
        """驗證 todo promote 批次原子提取、ID/slug 防呆與既有目錄合流追加。"""
        roadmap_dir = self.plans_dir / "roadmap_batch"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)
        mgr.add_todo(title="Task 1", scope="core", note="TechDebt")
        mgr.add_todo(title="Task 2", scope="core", note="Polish")
        mgr.add_todo(title="Task 3", scope="core", note="Doc")

        self.assertFalse(mgr.promote_todos(todo_ids=[], slug="valid_slug")["success"])
        self.assertFalse(mgr.promote_todos(todo_ids=["bad-token"], slug="valid_slug")["success"])

        bad_id_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-99"],
            slug="valid_slug",
        )
        self.assertFalse(bad_id_res["success"])
        self.assertEqual(len(mgr.list_todos()), 3)

        bad_slug_res = mgr.promote_todos(
            todo_ids=["TODO-01"],
            slug="Invalid-Slug!",
        )
        self.assertFalse(bad_slug_res["success"])
        self.assertEqual(len(mgr.list_todos()), 3)

        ok_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-03"],
            slug="core_cleanup_batch",
            model="Unknown",
        )
        self.assertTrue(ok_res["success"])
        remaining = mgr.list_todos()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].todo_id, "TODO-02")

        seed_dir = Path(ok_res["plan_dir"])
        self.assertTrue((seed_dir / "todo.md").is_file())
        self.assertTrue((seed_dir / "changelog.md").is_file())
        todo_seed_text = (seed_dir / "todo.md").read_text(encoding="utf-8")
        self.assertIn("TODO-01", todo_seed_text)
        self.assertIn("TODO-03", todo_seed_text)
        self.assertNotIn("TODO-02", todo_seed_text)

        # 將剩餘之 TODO-02 追加合流至同一計畫目錄
        append_res = mgr.promote_todos(
            todo_ids=["TODO-02"],
            target_plan=seed_dir,
            model="Unknown",
        )
        self.assertTrue(append_res["success"])
        self.assertIn("TODO-02", (seed_dir / "todo.md").read_text(encoding="utf-8"))
        self.mark_passed()

    def test_roadmap_status_filter_and_exclude_todo(self):
        """驗證 RoadmapManager 自動排除 TODO.md 並支援 --status 過濾與擴充欄位解析。"""
        roadmap_dir = self.plans_dir / "roadmap_filter"
        roadmap_dir.mkdir(parents=True, exist_ok=True)

        (roadmap_dir / "TODO.md").write_text("# 專案輕量待辦清單\n> 狀態：Active\n", encoding="utf-8")
        (roadmap_dir / "topic_ready.md").write_text(
            "# 路線圖 A\n\n"
            "> 主題：路線圖 A\n"
            "> 建立日期：2026-10-20\n"
            "> 狀態：Ready\n"
            "> 目標範疇：agents-workflow\n"
            "> 前置解鎖條件：完成前置模組\n"
            "> 模型：Unknown\n\n"
            "## 1. 問題陳述與根因量化 (Problem & Root Cause)\n"
            "- **現況痛點**：需要自動晉升機制。\n",
            encoding="utf-8",
        )
        (roadmap_dir / "topic_deferred.md").write_text(
            "# 路線圖 B\n\n"
            "> 主題：路線圖 B\n"
            "> 建立日期：2026-10-21\n"
            "> 狀態：Deferred\n"
            "> 目標範疇：core\n"
            "> 前置解鎖條件：無\n"
            "> 模型：Unknown\n\n"
            "## 1. 問題陳述與根因量化 (Problem & Root Cause)\n"
            "- **現況痛點**：延後評估。\n",
            encoding="utf-8",
        )

        mgr = RoadmapManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)
        all_items = mgr.scan_roadmaps()
        self.assertEqual(len(all_items), 2)
        filenames = [it.filename for it in all_items]
        self.assertNotIn("TODO.md", filenames)

        ready_items = mgr.scan_roadmaps(status_filter="Ready")
        self.assertEqual(len(ready_items), 1)
        self.assertEqual(ready_items[0].filename, "topic_ready.md")
        self.assertEqual(ready_items[0].scope, "agents-workflow")
        self.assertEqual(ready_items[0].trigger, "完成前置模組")
        self.mark_passed()

    def test_roadmap_promote_physical_move_and_model_isolation(self):
        """驗證 roadmap promote 物理移轉 (Consume-on-Promote)、模型防回溯與寫入失敗回滾保護。"""
        roadmap_dir = self.plans_dir / "roadmap_promote_test"
        roadmap_dir.mkdir(parents=True, exist_ok=True)

        (roadmap_dir / "TODO.md").write_text("# 專案輕量待辦清單\n", encoding="utf-8")
        src_roadmap = roadmap_dir / "future_arch.md"
        src_roadmap.write_text(
            "# 未來架構藍圖\n\n"
            "> 主題：未來架構藍圖\n"
            "> 建立日期：2026-09-01\n"
            "> 狀態：Ready\n"
            "> 目標範疇：agents-workflow\n"
            "> 前置解鎖條件：無\n"
            "> 模型：HistoricalOldModel-v1\n\n"
            "## 1. 問題陳述與根因量化 (Problem & Root Cause)\n"
            "- **現況痛點**：跨模組解耦。\n",
            encoding="utf-8",
        )

        mgr = RoadmapManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        todo_err = mgr.promote_roadmap("TODO")
        self.assertFalse(todo_err["success"])
        missing_err = mgr.promote_roadmap("non_existent")
        self.assertFalse(missing_err["success"])

        res = mgr.promote_roadmap(
            "future_arch",
            model="CurrentSessionModel",
        )
        self.assertTrue(res["success"])
        self.assertFalse(src_roadmap.exists())

        plan_dir = Path(res["plan_dir"])
        moved_roadmap = plan_dir / "roadmap.md"
        companion_changelog = plan_dir / "changelog.md"
        self.assertTrue(moved_roadmap.is_file())
        self.assertTrue(companion_changelog.is_file())

        self.assertIn("> 模型：HistoricalOldModel-v1", moved_roadmap.read_text(encoding="utf-8"))
        cl_text = companion_changelog.read_text(encoding="utf-8")
        self.assertIn("CurrentSessionModel", cl_text)
        self.assertNotIn("HistoricalOldModel-v1", cl_text)

        (roadmap_dir / "ambig_one.md").write_text("# 模糊一\n> 主題：模糊一\n> 歸檔日期：2026-09-01\n> 狀態：Backlog\n", encoding="utf-8")
        (roadmap_dir / "ambig_two.md").write_text("# 模糊二\n> 主題：模糊二\n> 歸檔日期：2026-09-02\n> 狀態：Backlog\n", encoding="utf-8")
        ambig_err = mgr.promote_roadmap("ambig")
        self.assertFalse(ambig_err["success"])
        self.assertIn("同時匹配多個路線圖檔案", ambig_err["error"])

        todo_mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)
        item = todo_mgr.add_todo(title="Atomic Todo Safety", scope="agents-workflow", note="keep intact on error")
        before_todo_text = todo_mgr.todo_file.read_text(encoding="utf-8")
        orig_write_text = Path.write_text
        orig_replace = os.replace

        def _fail_on_dest_todo(path_self: Path, data: str, *args, **kwargs):
            if "todo.md" in path_self.name:
                raise OSError("Simulated disk write failure on todo.md")
            return orig_write_text(path_self, data, *args, **kwargs)

        def _fail_on_replace_todo(src, dst, *args, **kwargs):
            if str(dst).endswith("todo.md"):
                raise OSError("Simulated disk write failure on todo.md")
            return orig_replace(src, dst, *args, **kwargs)

        with mock.patch.object(Path, "write_text", new=_fail_on_dest_todo), mock.patch(
            "os.replace", side_effect=_fail_on_replace_todo
        ):
            with self.assertRaises(OSError):
                todo_mgr.promote_todos([item.todo_id], slug="atomic_fail_test")

        after_todo_text = todo_mgr.todo_file.read_text(encoding="utf-8")
        self.assertEqual(before_todo_text, after_todo_text)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
