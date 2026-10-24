# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_roadmap_and_todo_refactoring  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `RoadmapItem` | `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Public | Roadmap 專題結構化資料模型（擴充 `scope` 與 `trigger` 欄位）。 |
| `RoadmapManager` | `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Public | 掃描、過濾與物理搬移立項 (`promote_roadmap`) 策略路線圖。 |
| `TodoItem` | `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Public | `TODO.md` 單筆待辦結構化資料模型（`todo_id`, `title`, `date`, `scope`, `note`, `raw_block`）。 |
| `TodoManager` | `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Public | 管理 `plans/roadmap/TODO.md` 之單行免讀盲寫追加 (`add_todo`)、過濾列表 (`list_todos`) 與單/多筆原子剪切立項 (`promote_todos`)。 |
| `PlanStatusResolver` | `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py` | Public | 定義 `ORIGIN_SEED_FILES = {"roadmap.md", "todo.md"}` 並支援 `Seeded` 狀態解析與下一步領航。 |
| `PlanScanner` | `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` | Public | `get_plan_info` 識別僅含 `roadmap.md` / `todo.md` 之 `Seeded` 計畫目錄。 |
| `PlanVerifier` | `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Public | 識別計畫目錄內 `roadmap.md` / `todo.md` 為前置源頭背景資產，執行輕量安全檢核並豁免模板章節鏡像与終態強制。 |
| `roadmap`, `todo` | `ys_codebase/source/agents-workflow/scripts/cli.py` | Public | CLI 頂層命令入口函式（符合 `CmdBags` 1:1 對稱性契約）。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
@dataclass
class RoadmapItem:
    topic: str
    filename: str
    path: Path
    title: str
    status: str
    date: str
    problem_summary: str
    has_valid_header: bool
    scope: str = ""
    trigger: str = ""


@dataclass
class TodoItem:
    todo_id: str          # 標準化大寫 ID，如 'TODO-01'
    number: int           # 整數編號，如 1
    title: str            # 待辦動作標題
    date: str             # 建立日期 YYYY-MM-DD
    scope: str            # 目標範疇
    note: str             # 備忘與解法要點
    raw_block: str        # 原始 Markdown 區塊文本


class RoadmapManager:
    def __init__(
        self,
        roadmap_dir: Optional[Path] = None,
        plans_dir: Optional[Path] = None,
        host_dir: Optional[str] = None,
    ) -> None: ...

    def scan_roadmaps(self, status_filter: Optional[str] = None) -> List[RoadmapItem]:
        """
        Pre-conditions: status_filter 若提供，以不區分大小寫比對 RoadmapItem.status。
        Post-conditions: 自動跳過檔名為 'TODO.md' (不分大小寫) 之集中式帳本，回傳依日期倒序之清單。
        """

    def promote_roadmap(
        self,
        topic_or_file: str,
        model: str = "Unknown",
        target_plan: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        Pre-conditions: topic_or_file 非空且非 'TODO.md'；匹配單一有效路線圖檔案。
        Post-conditions:
          - 若未指定 target_plan：建立 plans/YYYY_MM_DD_HHMM_<stem>/ 目錄。
          - 若指定 target_plan：解析並定位既有計畫或 sub_XX 目錄。
          - 使用 shutil.move 將原檔搬移為 target_dir/roadmap.md。
          - 呼叫 PlanVerifier.append_changelog_entry 以當輪 model (預設 'Unknown') 初始化/追加 changelog.md。
          - 回傳 {'success': True, 'plan_dir': Path, 'roadmap_path': Path, 'source_path': Path, 'model': str, 'message': str}。
        """


class TodoManager:
    SLUG_PATTERN = re.compile(r"^[a-z0-9_]+$")

    def __init__(
        self,
        roadmap_dir: Optional[Path] = None,
        plans_dir: Optional[Path] = None,
        host_dir: Optional[str] = None,
    ) -> None: ...

    @property
    def todo_file(self) -> Path:
        """回傳 self.roadmap_dir / 'TODO.md'。"""

    def add_todo(
        self,
        title: str,
        scope: str = "general",
        note: str = "無",
        model: str = "Unknown",
    ) -> TodoItem:
        """
        Pre-conditions: title 非空白字串。
        Post-conditions:
          - 若 TODO.md 不存在則自動建立父目錄並寫入初始模板。
          - 讀取頂部 '> 最後分配編號：N' 與現存最大編號，計算 next_num = max(N, max_existing) + 1。
          - 更新頂部 '> 更新日期：'、'> 最後分配編號：{next_num}' 與 '> 模型：{model}'。
          - 於檔尾追加 ### [TODO-{next_num:02d}] 結構化區塊並回傳 TodoItem。
        """

    def list_todos(self, scope_keyword: Optional[str] = None) -> List[TodoItem]:
        """
        Pre-conditions: 無（若 TODO.md 不存在則回傳空列表 []）。
        Post-conditions: 解析所有 ### [TODO-XX] 區塊，若提供 scope_keyword 則不區分大小寫過濾 scope/title/note。
        """

    def format_todo_table(self, items: Optional[List[TodoItem]] = None) -> str:
        """格式化輸出 ASCII 摘要對照表。"""

    def promote_todos(
        self,
        todo_ids: List[str],
        slug: Optional[str] = None,
        model: str = "Unknown",
        target_plan: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        Pre-conditions:
          - todo_ids 非空，且所有指定 ID 皆存在於 TODO.md 中（正規化支援 '1', '01', 'TODO-01', '[TODO-01]'）。
          - 若未指定 target_plan，slug 必填且必須匹配 ^[a-z0-9_]+$。
        Post-conditions:
          - 自 TODO.md 原子移除目標區塊（保持 '> 最後分配編號：' 不變）並寫回 TODO.md。
          - 建立 plans/YYYY_MM_DD_HHMM_{slug}/（或定位 target_plan），寫入 todo.md（若目標已有 todo.md 則追加條目）。
          - 呼叫 PlanVerifier.append_changelog_entry 初始化/追加 changelog.md。
          - 回傳 {'success': True, 'plan_dir': Path, 'todo_path': Path, 'promoted_ids': List[str], 'model': str, 'message': str}。
        """
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `promote_roadmap` 與 `promote_todos` 遭遇參數不合法（如 `--slug` 含非小寫英數底線、找不到指定 `TODO-ID` 或 `<topic>` 模糊匹配多檔）時，不拋出未捕獲例外，統一回傳 `{"success": False, "error": "<含 Fix Hint 之明確錯誤訊息>"}`，由 `scripts/cli.py` 印出並回傳退出碼 `1`（且保證原子性：失敗時絕不破壞原 `TODO.md` 或殘留空計畫資料夾）。
- **階段決策紀錄**：
  - **`[P03:DR-01]` `todo_ids` 彈性輸入正規化**：`TodoManager.normalize_todo_id(raw_id)` 支援將 `"1"`, `"01"`, `"todo-1"`, `"TODO-01"`, `"[TODO-01]"` 統一正規化為標準整數編號與 `"TODO-01"`，提升 Agent 與開發者命令列輸入容錯度。
  - **`[P03:DR-02]` 預設子命令無縫相容**：`python yscb.py agents-workflow todo`（未帶子命令時）預設等同 `todo list`；`python yscb.py agents-workflow roadmap`（未帶子命令或帶 `list` 時）預設列出策略路線圖摘要表並支援 `--status <val>`。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Level 1 (Templates & Assets Base)
  ├── ys_codebase/source/agents-workflow/assets/templates/todo.md (New)
  └── ys_codebase/source/agents-workflow/assets/templates/roadmap.md (Modify)
        │
        ▼
Level 2 (Core Python Engines: Backlog & Plans Whitelist)
  ├── ys_codebase/source/agents-workflow/agents_workflow/roadmap.py (TodoItem, TodoManager, RoadmapManager.promote_roadmap)
  ├── ys_codebase/source/agents-workflow/agents_workflow/plans/status.py (ORIGIN_SEED_FILES & Seeded state)
  ├── ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py (Seeded track & status display)
  └── ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py (roadmap.md / todo.md whitelist validation)
        │
        ▼
Level 3 (CLI Entry, Contributes & Skills Integration)
  ├── ys_codebase/source/agents-workflow/scripts/cli.py (def roadmap, def todo)
  ├── ys_codebase/source/agents-workflow/contributes/core.json (roadmap & todo command specs)
  ├── ys_codebase/source/agents-workflow/contributes/agents-workflow.json (export todo skill & todo.md template)
  └── ys_codebase/source/agents-workflow/assets/skills/{todo,roadmap,new-plan,development-sop,discuss,research,yscb-cli-guide}/SKILL.md
        │
        ▼
Level 4 (Unit Tests, Docs & @build Dogfooding Verification)
  ├── ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py
  └── docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}
```

