# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_06_agents_workflow 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `ReleaseTargetManager` 與 `ReleasePublisher` 淺拷貝防禦、空目標保留與事務回滾 (`OPT-01, 05, 06`) | `get_tier_targets()` 回傳淺拷貝、`_get_project_config()` 保留空陣列 `[]`、`sync_gitignore()` 合併雙軌 Manifest 與 `_ReleaseTransactionContext` 原子回滾。 | P0 | [P00:DR-01] |
| **FR-02** | `ArtifactCompiler` 路徑邊界匹配、原始字串快取與原子寫入 (`OPT-02, 03`) | `_lookup_deployed_abs_path` 強制 `/` 或 `://` 後綴邊界、`_resolve_insert_value` 快取預處理前字串、預編譯正則與 `.tmp` 原子寫入。 | P0 | [P00:DR-01] |
| **FR-03** | `WorkflowInitializer`、`RoadmapManager` 與 `_common.resolve_plan_uri` 防禦 (`OPT-04, 07, 08`) | 攔截 `"!"` 開頭之未定義 URI、支援 `workflow.plans://` 回退、原子寫入與 `path.stem.lower()` 模糊比對。 | P0 | [P00:DR-01] |
| **FR-04** | `PlanVerifier`、`PlanArchiver` 與 `SessionTraceEngine` 解析精準度修復 (`OPT-09~16`) | 過濾圍欄代碼塊假標題、`"<!--" in non_code_text` 精準檢查、P01<->P06 雙向追蹤、`append_changelog_entry` 轉義 `\|` 冪等性、`archive_plan` 尾斜線正規化與 4 欄 `changelog.md` 解析修復。 | P0 | [P00:DR-02] |
| **FR-05** | `scripts/cli.py`、`1.2.4.x.py` 與 `tests/` 8 檔純化及狀態隔離 (`OPT-17~18, AUD-01~32`) | `release-target --rm <target>`、`_get_str_option` 布林防呆、`ConfigStateSnapshot` 宿主環境零污染與 0 `ResourceWarning`。 | P0 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 使用者將專案 `release_targets` 設為空陣列 `[]` 以停用所有目標 | `_get_project_config()` 以 `isinstance(targets, list)` 判斷而非 `if targets:`，保留空陣列 `[]` 不被覆寫回 `['antigravity']`。 |
| **EC-02** | 計畫 Markdown 內文包含 ASCII 箭頭 `-->` 或圍欄代碼塊內含 `# comment` | `PlanVerifier` 剝除代碼塊後僅檢查 `"<!--" in non_code_text` 與非代碼塊標題，徹底消除假陽性誤報。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態規範與向後相容 | `Checker().check_module('agents-workflow')` 達成 `0 FAIL, 0 WARN`，4 支腳本頂層 `0 ast.Assign`，公開 SDK/CLI 100% 向後相容。 |
| **NFR-02** | 測試純淨度與宿主環境零污染 | 142 項單元測試於 `python3 -W error::ResourceWarning` 下 100% 通過（耗時 `13.64s`，`0 ResourceWarning`），實機 `AGENTS.md`/`CLAUDE.md` 100% 隔離還原。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開契約相容與鎖可重入性**：所有內部鎖升級與快取深拷貝均須維持公開方法簽名與單元測試 Mock 攔截點 100% 相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `agents-workflow` 現有公開模組拓撲，透過內部純函式提煉、可重入鎖保護、原子寫入回滾與測試沙盒隔離消除競態與結構膨脹。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | 落實 `OPT-02, OPT-03`（後綴邊界匹配、原始文本快取與原子寫入） |
| `ys_codebase/source/agents-workflow/agents_workflow/initializer.py` | Modify | 落實 `OPT-04`（`!undefined` URI 攔截與互動確認拆解） |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 落實 `OPT-05, OPT-06`（空陣列保留、雙軌 gitignore 與 `_ReleaseTransactionContext`） |
| `ys_codebase/source/agents-workflow/agents_workflow/roadmap.py` | Modify | 落實 `OPT-07, OPT-08`（原子寫入與 `stem` 模糊比對） |
| `ys_codebase/source/agents-workflow/agents_workflow/targets.py` | Modify | 落實 `OPT-01`（`get_tier_targets` 淺拷貝與 `_mutate_tier_target`） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_common.py` | Modify | 落實 `OPT-08`（`resolve_plan_uri` 統一防禦） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_trace_parser.py` | Modify | 落實 `OPT-16`（`_StepParseContext` 與 `thinking_excerpts` 去重） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_verifier_healer.py` | Modify | 落實 `OPT-10`（`append_changelog_entry` 轉義 `\|` 與首列冪等檢查） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/_verifier_specs.py` | Modify | 落實 `OPT-09, OPT-10`（圍欄代碼塊過濾與表頭鍵收斂） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/archiver.py` | Modify | 落實 `OPT-13`（尾斜線正規化與路徑穿越防禦） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` & `searcher.py` | Modify | 落實 `OPT-14`（`build_recovery_capsule` 拆解與正則預編譯） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` | Modify | 落實 `OPT-15`（4 欄 `changelog.md` 解析修復） |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | 落實 `OPT-09, OPT-11, OPT-12`（`<!--` 精準檢查與 P01<->P06 雙向追蹤） |
| `ys_codebase/source/agents-workflow/scripts/cli.py` & `migrations/1.2.4.x.py` | Modify | 落實 `OPT-17, OPT-18`（`--rm` 支援、`_get_str_option` 與遷移回退） |
| `ys_codebase/source/agents-workflow/tests/__init__.py` & `tests/test_*.py` (8 檔) | Modify | 落實 `AUD-01 ~ AUD-32`（`ConfigStateSnapshot` 隔離、0 `ResourceWarning` 與 142 項測試） |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 受控 CoW 雲端同步與零工單殘留**：全部 24 個修改檔案皆以受控 CoW（舊檔移入 `repo/.trash/` 後上傳原格式新檔）同步至 Google Drive，且源碼與測試內達成 0 工單編號殘留。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

維持 `agents-workflow` 對外公開 SDK 與 `scripts/cli.py` 所有子指令、選項及回傳碼契約 100% 向後相容（`Mode B`），內部私有輔助函式採單一正統入口（`Mode A`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] 已通過 Step 2 魔鬼代言人（Devil's Advocate B1/B2）反向查驗、Step 4 盲測驗收（Subagent D `PASS`）與 Step 5 零錨定二次審計（Subagent E `P0=0, P1=0, P2=0` 融斷通過）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | Modify | 於專案根目錄 `CHANGELOG.md` 登記 `sub_06_agents_workflow` 優化與修復摘要 |
| **中觀 (Meso)** | `docs/agents-workflow/README.md` | 免更 | 屬內部確定性重構與併發/邊界防禦強化，無公開架構或 CLI 語法變更 |
| **微觀 (Micro)** | `ys_codebase/source/agents-workflow/` | Modify | 清理工單編號註解並同步維護公開與內部輔助函式 Docstring |

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲測子代理 A1/A2 初審與 B1/B2 反向驗證（定案 `OPT-01 ~ OPT-18` 與 `AUD-01 ~ AUD-32`）
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C1/C2 沙盒實作、測試純化與雲端受控 CoW 同步（共 24 檔）
- [x] **TASK-03**：完成 Loop 1 Step 4 盲測子代理 D 驗收（`PASS`）與 Step 5 盲測子代理 E 零錨定融斷判定（`P0=0, P1=0, P2=0`）
- [x] **TASK-04**：完成 Phase 07 SOP Review Gate 冷眼靜態審查、三層文檔對齊與 `P07_walkthrough.md` 結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
