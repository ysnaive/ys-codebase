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

from agents_workflow.roadmap import RoadmapManager, RoadmapItem, TodoManager

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
        self.plans_dir = Path(self.temp_dir) / "plans"
        self.roadmap_dir = self.plans_dir / "roadmap"
        self.roadmap_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        super().tearDown()

    def test_empty_roadmap_directory(self):
        """EC-03: 目錄為空時安全返回空清單與友好提示。"""
        mgr = RoadmapManager(roadmap_dir=self.roadmap_dir)
        items = mgr.scan_roadmaps()
        self.assertEqual(len(items), 0)

        summary = mgr.format_summary_table(items)
        self.assertIn("目前無任何待啟動之 Roadmap 技術儲備", summary)
        self.mark_passed()

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
        self.mark_passed()

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
        self.mark_passed()

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
        self.mark_passed()

    def test_promote_roadmap_append_when_already_exists(self):
        """[FR-07 / ET-05] 測試多路線圖合流遷入同一計畫目錄時無損追加合併。"""
        r1_content = "# 路線圖一 (Roadmap)\n\n> 主題：路線圖一  \n> 狀態：Ready  \n\n內容一"
        r2_content = "# 路線圖二 (Roadmap)\n\n> 主題：路線圖二  \n> 狀態：Ready  \n\n內容二"
        (self.roadmap_dir / "r1.md").write_text(r1_content, encoding="utf-8")
        (self.roadmap_dir / "r2.md").write_text(r2_content, encoding="utf-8")

        mgr = RoadmapManager(roadmap_dir=self.roadmap_dir, plans_dir=self.plans_dir)
        # 第一次遷入：建立新目錄並移入為 roadmap.md
        res1 = mgr.promote_roadmap("r1", model="TestModel")
        self.assertTrue(res1["success"])
        self.assertFalse(res1["is_appended"])
        plan_dir = res1["plan_dir"]
        self.assertTrue((plan_dir / "roadmap.md").is_file())
        self.assertFalse((self.roadmap_dir / "r1.md").exists())

        # 第二次遷入：指定同一目錄 --plan，應追加合併且移除來源檔
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
        """FT-01 & ET-04: todo add 免讀盲寫追加與 > 最後分配編號：N 單調遞增防碰撞。"""
        roadmap_dir = self.plans_dir / "roadmap_todo"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        r1 = mgr.add_todo(title="清理 compiler 死代碼", scope="agents-workflow", note="來自 sub_02")
        self.assertEqual(r1.todo_id, "TODO-01")

        r2 = mgr.add_todo(title="補充 CLI 範例", scope="core", note="補充文檔")
        self.assertEqual(r2.todo_id, "TODO-02")

        # 檢查標頭 > 最後分配編號：2
        content = mgr.todo_file.read_text(encoding="utf-8")
        self.assertIn("> 最後分配編號：2", content)

        # Pop 提取全部條目清空帳本後，再次 add_todo 必須從 TODO-03 開始，不可碰撞 TODO-01
        pop_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-02"],
            slug="cleanup_batch",
            model="Unknown",
        )
        self.assertTrue(pop_res["success"])
        self.assertEqual(len(mgr.list_todos()), 0)

        # 驗證 normalize_todo_id 正規化契約 ([P03:DR-01])
        self.assertEqual(TodoManager.normalize_todo_id("1"), "TODO-01")
        self.assertEqual(TodoManager.normalize_todo_id("todo-2"), "TODO-02")
        self.assertEqual(TodoManager.normalize_todo_id("[TODO-03]"), "TODO-03")
        self.assertIsNone(TodoManager.normalize_todo_id("invalid"))

        r3 = mgr.add_todo(title="提取清空後之新條目", scope="global", note="驗證單調遞增")
        self.assertEqual(r3.todo_id, "TODO-03")
        self.mark_passed()

    def test_todo_list_and_scope_filter(self):
        """FT-02 & ET-01: todo list 空帳本優雅返回與 --scope 過濾。"""
        roadmap_dir = self.plans_dir / "roadmap_empty"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)

        # ET-01: 尚未建立 TODO.md 時不報錯且不寫檔
        self.assertEqual(mgr.list_todos(), [])
        self.assertIn("目前尚無活躍之輕量待辦項目", mgr.format_todo_table())
        self.assertFalse(mgr.todo_file.exists())

        mgr.add_todo(title="Item A", scope="agents-workflow", note="TechDebt")
        mgr.add_todo(title="Item B", scope="knowledge-db", note="Polish")
        mgr.add_todo(title="Item C", scope="agents-workflow", note="Idea")

        aw_items = mgr.list_todos(scope_keyword="agents-workflow")
        self.assertEqual(len(aw_items), 2)
        polish_items = mgr.list_todos(scope_keyword="Polish")
        self.assertEqual(len(polish_items), 1)
        self.assertEqual(polish_items[0].todo_id, "TODO-02")
        self.mark_passed()

    def test_todo_promote_batch_and_seeded_dir(self):
        """FT-03, ET-02 & ET-03: todo promote 批次原子提取、ID/slug 防呆與 todo.md 種子生成。"""
        roadmap_dir = self.plans_dir / "roadmap_batch"
        mgr = TodoManager(roadmap_dir=roadmap_dir, plans_dir=self.plans_dir)
        mgr.add_todo(title="Task 1", scope="core", note="TechDebt")
        mgr.add_todo(title="Task 2", scope="core", note="Polish")
        mgr.add_todo(title="Task 3", scope="core", note="Doc")

        # ET-02: 包含不存在的 TODO-99 時強制阻斷且不修改原檔
        bad_id_res = mgr.promote_todos(
            todo_ids=["TODO-01", "TODO-99"],
            slug="valid_slug",
        )
        self.assertFalse(bad_id_res["success"])
        self.assertEqual(len(mgr.list_todos()), 3)

        # ET-03: 非法 slug 強制阻斷
        bad_slug_res = mgr.promote_todos(
            todo_ids=["TODO-01"],
            slug="Invalid-Slug!",
        )
        self.assertFalse(bad_slug_res["success"])
        self.assertEqual(len(mgr.list_todos()), 3)

        # FT-03: 正常打包提取 TODO-01 與 TODO-03
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
        self.mark_passed()

    def test_roadmap_status_filter_and_exclude_todo(self):
        """FT-04: RoadmapManager 自動排除 TODO.md 並支援 --status 過濾與擴充欄位解析。"""
        roadmap_dir = self.plans_dir / "roadmap_filter"
        roadmap_dir.mkdir(parents=True, exist_ok=True)

        (roadmap_dir / "TODO.md").write_text("# 專案輕量待辦清單\n> 狀態：Active\n", encoding="utf-8")
        (roadmap_dir / "topic_ready.md").write_text(
            "# 路線圖 A\n\n"
            "> 主題：路線圖 A\n"
            "> 建立日期：2026-10-20\n"
            "> 狀態：Ready\n"
            "> 目標範疇：agents-workflow\n"
            "> 前置解鎖條件：完成 sub_01\n"
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
        self.assertEqual(ready_items[0].trigger, "完成 sub_01")
        self.mark_passed()

    def test_roadmap_promote_physical_move_and_model_isolation(self):
        """FT-05 & ET-05: roadmap promote 物理移轉 (Consume-on-Promote)、模型防回溯與防呆攔截。"""
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

        # ET-05: 禁止對 TODO.md 或不存在的主題執行 roadmap promote
        todo_err = mgr.promote_roadmap("TODO")
        self.assertFalse(todo_err["success"])
        missing_err = mgr.promote_roadmap("non_existent")
        self.assertFalse(missing_err["success"])

        # FT-05: 正常執行物理移轉，傳入當輪 --model "CurrentSessionModel"
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

        # 驗證模型防回溯：roadmap.md 保留 HistoricalOldModel-v1，而 changelog.md 記載 CurrentSessionModel
        self.assertIn("> 模型：HistoricalOldModel-v1", moved_roadmap.read_text(encoding="utf-8"))
        cl_text = companion_changelog.read_text(encoding="utf-8")
        self.assertIn("CurrentSessionModel", cl_text)
        self.assertNotIn("HistoricalOldModel-v1", cl_text)

        # 測試模糊匹配多個檔案時之阻斷保護 (EC-04)
        (roadmap_dir / "ambig_one.md").write_text("# 模糊一\n> 主題：模糊一\n> 歸檔日期：2026-09-01\n> 狀態：Backlog\n", encoding="utf-8")
        (roadmap_dir / "ambig_two.md").write_text("# 模糊二\n> 主題：模糊二\n> 歸檔日期：2026-09-02\n> 狀態：Backlog\n", encoding="utf-8")
        ambig_err = mgr.promote_roadmap("ambig")
        self.assertFalse(ambig_err["success"])
        self.assertIn("同時匹配多個路線圖檔案", ambig_err["error"])
        self.mark_passed()
