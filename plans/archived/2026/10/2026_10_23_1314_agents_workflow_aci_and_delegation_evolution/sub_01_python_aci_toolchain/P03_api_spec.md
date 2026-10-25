# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_python_aci_toolchain  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PlanStatusResolver.get_doc_header_model` | `agents_workflow/plans/status.py` | Public | 提取單一 Markdown 文件前 35 行 Blockquote 之 `> 模型：` 標頭值（排除佔位符，無則回傳 `"Unknown"`）。 |
| `PlanStatusResolver.resolve_next_action` | `agents_workflow/plans/status.py` | Public | 根據計畫（或活躍子計畫）目錄現有產物與標頭狀態，確定性推導當前階段、下一階段、應讀參考手冊路徑與行動提示。 |
| `PlanScanner.resolve_target_plan_dir` | `agents_workflow/plans/scanner.py` | Public | 解析目標計畫路徑（支援單一活躍計畫自動定位、`<plan_name>`、`<plan_name>/sub_XX` 或唯一 `sub_XX` 名稱定位）。 |
| `PlanScanner.execute_resume` | `agents_workflow/plans/scanner.py` | Public | 執行斷點領航與選配之 `--resume` `handoff.md` 原子讀取與物理刪除 (`os.unlink`)，回傳結構化領航字典與格式化字串。 |
| `PlanVerifier.verify_plan` | `agents_workflow/plans/verifier.py` | Public | 擴充支援 `phase`、`log_msg`、`log_type`、`model` 參數，執行四步檢核、伴隨檔自癒、`P01<->P06` 追溯差集比對與 `changelog.md` 冪等盲寫追加。 |
| `PlanVerifier.extract_requirement_ids` | `agents_workflow/plans/verifier.py` | Public | 剝除代碼塊、HTML 註解與 `~~...~~` 刪除線後，提取文本中之 `FR-\d+`、`EC-\d+`、`NFR-\d+` 排序集合。 |
| `PlanVerifier.append_changelog_entry` | `agents_workflow/plans/verifier.py` | Public | 免讀歷史 Context 並具備首筆 `(類型, 摘要)` 冪等防重入保護之 `changelog.md` 頂部列追加方法。 |
| `plan_status` / `plan_check` / `plan_verify` | `scripts/cli.py` | Public | CLI 入口函式，解析 `--plan`、`--resume`、`--phase`、`--log`、`--type`、`--model` 並回傳標準 Exit Code。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. agents_workflow/plans/status.py
class PlanStatusResolver:
    @classmethod
    def get_doc_header_model(cls, doc_target: Union[Path, str]) -> str:
        """
        提取文件標頭之 '> 模型：' 欄位值。
        Pre-conditions: doc_target 為有效 Path 或 Markdown 字串。
        Post-conditions: 若存在有效模型名稱且非 '[...]' 模板佔位符則原樣回傳，否則回傳 'Unknown'。
        """

    @classmethod
    def resolve_next_action(cls, plan_dir: Path) -> Dict[str, Any]:
        """
        根據目標計畫目錄推導確定性下一步行動。
        Pre-conditions: plan_dir 為存在之計畫或子計畫目錄。
        Post-conditions: 回傳字典包含:
            - target_plan_name (str): 實際定位之計畫或 relative sub_plan 名稱
            - target_plan_dir (Path): 實際定位之目錄路徑
            - mode (str): 'Full Track' | 'Fast Track' | 'Umbrella' | 'Revision' | 'Research' | 'Phase 0' | 'Unknown'
            - current_phase (str): 當前階段標識 (如 'P02', 'FP-01', 'R01' 等)
            - current_status (str): 當前階段檔案之正規化狀態
            - next_phase (str): 建議推進之下一階段標識
            - required_reference_path (str): 應讀取之 SOP 參考檔相對路徑 (如 '.agents/skills/development-sop/references/phase_03_api_spec.md')
            - next_action_hint (str): 1 行具體下一步行動指引
            - has_handoff (bool): 目標目錄或父目錄是否存在 handoff.md
        """

# 2. agents_workflow/plans/scanner.py
class PlanScanner:
    def resolve_target_plan_dir(
        self, plan_name_or_subpath: Optional[str] = None
    ) -> Tuple[Optional[Path], Optional[str]]:
        """
        解析目標計畫目錄。
        Pre-conditions: plan_name_or_subpath 可為 None (自動找唯一活躍計畫) 或指定計畫/子計畫名稱。
        Post-conditions: 回傳 (target_dir, error_msg)；若存在多個活躍計畫且未指定則回傳 (None, 多計畫提示訊息)。
        """

    def execute_resume(
        self,
        plan_name_or_subpath: Optional[str] = None,
        consume_handoff: bool = False,
    ) -> Dict[str, Any]:
        """
        執行狀態領航與 handoff.md 原子閱後即焚。
        Pre-conditions: consume_handoff=True 時僅在成功定位單一目標計畫時執行讀取並 unlink handoff.md。
        Post-conditions: 回傳包含 success, error, nav_info, handoff_consumed, handoff_path, handoff_content, formatted_output 之字典。
        """

# 3. agents_workflow/plans/verifier.py
class PlanVerifier:
    @staticmethod
    def extract_requirement_ids(markdown_text: str) -> Set[str]:
        """
        從 P01 文本提取有效需求 ID (FR-XX, EC-XX, NFR-XX)。
        Pre-conditions: 預先剝除 Fenced Code Blocks、HTML 註解與 '~~...~~' 刪除線。
        Post-conditions: 回傳大寫標準化需求 ID 集合。
        """

    def append_changelog_entry(
        self,
        target_dir: Path,
        summary: str,
        log_type: str = "PHASE",
        model: str = "Unknown",
    ) -> Tuple[bool, str]:
        """
        於 target_dir/changelog.md 表格頂部免讀盲寫插入新紀錄列 (含冪等防重入)。
        Pre-conditions: summary 非空；log_type 為 PHASE | DECISION | REVISION 等。
        Post-conditions: 若首筆資料列之 (類型, 摘要) 相同則回傳 (False, "idempotent_skipped")；否則寫入並回傳 (True, "appended")。
        """

    def verify_plan(
        self,
        plan_path_or_name: Union[str, Path],
        phase: str = "all",
        log_msg: Optional[str] = None,
        log_type: str = "PHASE",
        model: Optional[str] = None,
    ) -> PlanReport:
        """
        對指定計畫目錄執行四步檢核與自癒流水線，回傳 PlanReport (保留向後相容預設值)。
        """
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 當 `plan status --resume` 遇多個進行中計畫且未指定 `--plan` 時，不拋出未捕獲例外，而由 `execute_resume` 回傳 `success=False` 與明確提示並於 CLI 返回 Exit Code `1`（且絕不刪除任何 `handoff.md`）。
  - 當 `verify_plan` 目標目錄不存在時，於 `PlanReport` 記錄 `STRUCTURE` 類別之 `FAIL` 並附帶修復指引，拒絕執行伴隨檔初始化或日誌寫入。
- **階段決策紀錄**：
  - `[P03:DR-01]` **`verify_plan` 簽名預設值 100% 向後相容**：新增之 `phase="all"`、`log_msg=None`、`log_type="PHASE"`、`model=None` 全數具備預設值，確保 `PlanArchiver.archive_plan` 與既有測試呼叫 `verify_plan(src_dir)` 時行為 100% 相容。
  - `[P03:DR-02]` **`PlanReport` 新增元數據屬性**：於 `PlanReport` 新增選填欄位 `companion_created: List[str]` 與 `log_status: Optional[str]`（`"appended"` | `"idempotent_skipped"` | `"skipped_on_fail"` | `None`），並同步納入 `to_dict()`，方便 CLI 與 `--json` 模式直接呈現自癒與日誌寫入狀態，同時不影響既有 `passed, errors = report` 雙元素 Tuple 解構。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Layer 1 (SSOT 狀態與標頭解析基石):
  └── agents_workflow/plans/status.py (PlanStatusResolver.get_doc_header_model, resolve_next_action)
        │
        ▼
Layer 2 (掃描領航與四步檢核自癒核心):
  ├── agents_workflow/plans/scanner.py (PlanScanner.resolve_target_plan_dir, execute_resume)
  └── agents_workflow/plans/verifier.py (PlanVerifier 四步管線、伴隨檔自癒、P01<->P06 差集、--log 盲寫)
        │
        ▼
Layer 3 (CLI 門面與 Contributes 契約對齊):
  ├── contributes/core.json (plan.cmd.status, plan.cmd.check, plan.cmd.verify 參數宣告)
  └── scripts/cli.py (plan_status, plan_check, plan_verify 參數解析與輸出渲染)
        │
        ▼
Layer 4 (Skills、知識庫文檔與單元測試驗證):
  ├── assets/skills/{continue,yscb-cli-guide,development-sop}/**
  ├── docs/agents-workflow/{README,user_guide,DESIGN_NOTES}.md
  └── tests/test_plans_aci_toolchain.py
```

