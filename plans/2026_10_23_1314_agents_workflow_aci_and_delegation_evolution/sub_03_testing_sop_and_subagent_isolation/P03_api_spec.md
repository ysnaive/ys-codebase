# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_03_testing_sop_and_subagent_isolation  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (High)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `testing-sop` (Skill Frontmatter & Guide) | `assets/skills/testing-sop/SKILL.md` | Public Skill | 規範六大自動化測試鐵律、自檢清單與專案測試錨點 `__@{TESTING_SOP_STANDARDS}__` (`FR-01`) |
| `test_suite_audit_and_purification.md` | `assets/skills/testing-sop/references/test_suite_audit_and_purification.md` | Public Ref | 規範存量測試集 `T-01`~`T-06` 體檢與子系統 1:1 歸戶收斂指南 (`FR-02`) |
| `TESTING_SOP_STANDARDS` (Token Anchor) | `contributes/agents-workflow.json` | Extension Token | 供模組與專案注入專屬測試框架指令、沙盒與注意事項之錨點 (`FR-01`) |
| `RoadmapManager.promote_roadmap()` | `agents_workflow/roadmap.py` | Public Class Method | 支援將長期路線圖遷入計畫目錄，若目錄已存在 `roadmap.md` 則自動追加合併 (`FR-07`) |
| `Three-Pillar Subagent Delegation Protocol` | `research/SKILL.md`, `discuss/SKILL.md`, `auto/SKILL.md`, `phase_05/06/07.md` | Internal SOP | 規範探索（支柱一）、實作（支柱二）與審查（支柱三）之委派邊界、二振熔斷與 Single-Writer 契約 (`FR-04`~`FR-06`) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `RoadmapManager.promote_roadmap` API 簽名與規格

```python
class RoadmapManager:
    def promote_roadmap(
        self,
        topic_or_filename: str,
        model: str = "Unknown",
        target_plan: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        將長期技術路線圖 (plans/roadmap/{topic}.md) 物理遷入至新建或既有之計畫目錄存為 roadmap.md。
        若目標目錄已存在 roadmap.md (多路線圖合流子計畫情境)，則以標準分隔線無損追加合併至既有 roadmap.md 尾部，
        並自 plans/roadmap/ 刪除原檔案，自動維護目標目錄之伴隨 changelog.md。

        Args:
            topic_or_filename: 欲立項之路線圖 stem 或完整檔名 (如 'testing_sop_and_phase06_hardening_roadmap')。
            model: 當輪平台明確宣告之模型名稱 (預設 'Unknown')。
            target_plan: 指定之目標計畫目錄名稱或相對路徑 (如 'sub_03_testing_sop_and_subagent_isolation')。

        Returns:
            Dict[str, Any]: 包含 'success', 'plan_dir', 'roadmap_path', 'source_path', 'message', 'is_appended' 之結構化字典。

        Raises:
            無 (所有錯誤均透過字典回傳 success: False 與 error 訊息)。
        """
```

### 2.2 支柱二 Subagent 回傳合約規格 (Pillar 2 Structured Return Code)

```markdown
### 支柱二 Subagent 結構化回傳規格 (嚴格控制在 150~300 Tokens 內)
STATUS: <COMPLETED | MINOR_DEVIATION | MAJOR_BLOCKER | CRITICAL_BLOCKER>
TASK: <目標 [TASK-XX] 編號與簡稱>
MODIFIED_FILES: <變更檔案路徑清單>
TEST_OUTCOME: <單元測試執行指令與結果 (例：3 Passed (100%), 0 Fail)>
DEVIATION_OR_BLOCKER_NOTE: <無 | 偏差說明 | 二振失敗詳細異常現場與 Fix Hint>
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `RoadmapManager.promote_roadmap()`：若目標路徑已存在 `roadmap.md`，讀取新路線圖正文，以 `\n\n---\n\n` 追加合併至目標 `dest_roadmap`，隨後安全呼叫 `matched.path.unlink()` 移除來源；若寫盤失敗回傳 `{"success": False, "error": "..."}`。
  - 支柱二 Subagent 內部遭遇測試失敗：內部修復次數上限為 2 次，第 2 次失敗時**強制中斷並拋出 `STATUS: MAJOR_BLOCKER`**，由主視窗攔截並發起 `/discuss`，嚴禁子代理在子視窗無限試錯。
- **階段決策紀錄**：
  - **`[P03:DR-01]`**：`RoadmapManager.promote_roadmap()` 支援 `is_appended` 旗標與追加合併邏輯，與 `TodoManager.promote_todos()` 的多筆追加行為完全同構。
  - **`[P03:DR-02]`**：三支柱 Subagent 回傳格式採純文字 Key-Value 結構化回傳（150~300 Tokens），杜絕代碼傾倒與長日誌浪費主視窗 Context。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Python ACI 工具鏈補強]
  └── agents_workflow/roadmap.py (promote_roadmap 追加合併邏輯)
        └── tests/test_roadmap.py (單元測試驗證追加合併)

[Step 2: 模組宣告與匯出配置]
  └── contributes/agents-workflow.json (註冊 testing-sop 技能與 TESTING_SOP_STANDARDS 錨點)

[Step 3: testing-sop 技能建立]
  ├── assets/skills/testing-sop/SKILL.md (主檔：六大鐵律 + 自檢清單 + 錨點)
  └── assets/skills/testing-sop/references/test_suite_audit_and_purification.md (參考指南：T-01~06 體檢模型)

[Step 4: 研發規範與 SOP 連鎖引用守門植入]
  ├── assets/standards/AgentsStandards.md (§2 路由表擴充)
  ├── assets/skills/development-sop/references/phase_04_plan.md (測試定稿前連鎖觸發)
  ├── assets/skills/development-sop/references/phase_05_task.md (編測前連鎖觸發 + 支柱二協定)
  ├── assets/skills/development-sop/references/phase_06_test.md (雙重守門 + 支柱二回傳)
  ├── assets/skills/development-sop/references/phase_07_walkthrough.md (支柱三 Fresh-Eyes Review)
  └── assets/skills/development-sop/references/plan_modes.md (Fast Track FP-02 測試連鎖觸發)

[Step 5: 技能協作與 Subagent 支柱一/二委派協定植入]
  ├── assets/skills/research/SKILL.md (支柱一唯讀探索)
  ├── assets/skills/discuss/SKILL.md (支柱一唯讀探索)
  └── assets/skills/auto/SKILL.md (支柱二序列實作門檻與二振熔斷)

[Step 6: 單元測試與編譯驗收]
  ├── tests/test_plans_model_record.py (同步更新技能清單與驗證三段式描述)
  └── dev check / dev test / contributes check / compile / release --force (全量驗收)
```

