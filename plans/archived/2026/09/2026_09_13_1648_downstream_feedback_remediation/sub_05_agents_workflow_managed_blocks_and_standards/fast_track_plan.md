# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_05_agents_workflow_managed_blocks_and_standards  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  1. **專案特化技能宣告式擴充規範與管理區塊純粹覆寫 (Declarative Project Contributed Routing & Clean Overwrite)**：經架構評估，純文字啟發式猜測比對存在數學上的不可判定性（無法區分新版官方廢棄/整併之舊系統列與使用者自訂列，必定導致過期舊技能被永遠誤判復活）。採納方案 1，回歸 YSCB 產物工廠之宣告式本質：`_soft_merge_agents_text` 保持對管理區塊 `<!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END -->` 的單向純粹覆寫（徹底杜絕廢棄舊技能殘留），外部自訂章節（如 `## 4. 專案特化工程規範`）100% 完整保留；於 `AgentsStandards.md` 注入引導規範，指導下游專案一律透過 `config/agents-workflow/contribute.json` 宣告 `insert` 至 `AGENTS_SKILL_ROUTING` 錨點（宣告式一等公民，升級自動編譯注入，杜絕物化檔案衝突）。
  2. **ContextInit.md 引用校準 (Fix Workflow Markdown Hyperlinks)**：`source/agents-workflow/assets/workflows/ContextInit.md` 中第 21, 35, 36 行使用 `__${project://...}__` 於 Markdown 鏈接語法 (`[AGENTS.md](__${project://AGENTS.md}__)` 等)，由於 `compiler.py:resolve_stage2_uri` 中 `__${...}__` 解析為相對於 project_root 之路徑（適用於 CLI 命令列），導致物化落地於 `.agents/workflows/ContextInit.md` 時產生無相對層級之非點擊有效鏈接。改用 `__#{...}__` 解析為相對於目前檔案之相對路徑（`../../AGENTS.md` 等），確保跨工具點擊跳轉完全正常。
  3. **舊 Managed 檔案清理與發布驗證 (Stale Managed Files Cleanup & Re-release)**：驗證 `publisher.py:release_all` 於發布目標或產物異動時的雙軌（project:// 與 cache://）舊檔案清理與 lifecycle 追蹤，確保乾淨無殘留，並以全套單元測試與 dogfooding 驗證端到端流程。
- **影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/workflows/ContextInit.md` (Modify)
  - `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md` (Modify)
  - `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` (Modify)
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` (Modify)
  - `ys_codebase/source/agents-workflow/tests/test_publisher.py` (Modify)
  - `docs/agents-workflow/DESIGN_NOTES.md` (Modify, DN-AW-11)
  - `docs/agents-workflow/FACTORY_PIPELINE.md` (Modify)
- **4 大剛性守門合規檢核**：
  - [x] 代碼修改行數預計 $\le 100$ 行（核心修改原始碼淨減/純淨化，完全合規）
  - [x] Public API 契約 0 變更（維持 `_soft_merge_agents_text` 介面簽名）
  - [x] 零跨模組新依賴引入（100% Python 標準庫）
  - [x] 既有單元測試與回歸測試 100% 覆蓋守門

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：校準 `source/agents-workflow/assets/workflows/ContextInit.md` 之 Markdown 相對路徑引用標籤（由 `__${...}__` 改為 `__#{...}__`）
- [x] **TASK-02**：於 `AgentsStandards.md` 注入專案宣告式技能擴充導引，並確保 `publisher.py` 之 `_soft_merge_agents_text` 單向純粹覆寫管理區塊（徹底杜絕過期技能殘留）與 100% 保留外部自定義章節
- [x] **TASK-03**：於 `test_publisher.py` 編寫單向標準覆寫與外部章節保留測試案例，並執行全量回歸與 Dogfooding 發布驗證
- **測試案例**：
  - `FT-01`：驗證 `ContextInit.md` 編譯後 Markdown 鏈接解析為相對於目前工作流檔案的正確相對路徑 (`../../AGENTS.md`, `../../CHANGELOG.md`, `../../docs/_project/STANDARDS.md`)
  - `FT-02`：驗證 `_soft_merge_agents_text` 於發布覆寫時徹底淘汰廢棄舊技能（杜絕殭屍復活），同時 100% 保留外部自訂章節，且多次發布具備冪等性 (Idempotent)

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. **TASK-01 工作流超連結校準**：修改 `source/agents-workflow/assets/workflows/ContextInit.md` 中的 `AGENTS.md`、`CHANGELOG.md` 與 `STANDARDS.md` 引用標籤為 `__#{...}__`，經編譯落地後在 `.agents/workflows/ContextInit.md` 精準產生為 `../../AGENTS.md`、`../../CHANGELOG.md`、`../../docs/_project/STANDARDS.md`，點擊跳轉完全正常；CLI 命令仍保持 `__${...}__` 正確語意。
  2. **TASK-02 宣告式技能擴充規範與純粹軟合併**：於 `source/agents-workflow/assets/standards/AgentsStandards.md` 注入專案特化技能擴充規範導引，引導下游透過 `config/agents-workflow/contribute.json` 向 `AGENTS_SKILL_ROUTING` 錨點宣告注入；`publisher.py` 之 `_soft_merge_agents_text` 保持對管理區塊的單向純粹注入，徹底消除反向猜測比對帶來的廢棄舊技能復活風險，外部自訂規範章節 100% 原樣保留且具備冪等性。
  3. **TASK-03 單元測試與 Dogfooding 發布驗證**：於 `test_publisher.py` 擴充 `test_ft_13_soft_merge_single_source_and_external_preservation` 與 `test_ft_14_contextinit_workflow_relative_links`；於 `scanner.py` 補齊 `Passed` / `Review` 狀態解析；於 `DESIGN_NOTES.md` 登錄 `[DN-AW-11]`；於 `FACTORY_PIPELINE.md` 更新發布行為說明。
- **實機測試日誌**：
  - `python yscb.py dev test agents-workflow`：76 Total, 76 Passed, 0 Failed, 0 Skipped (68.64s)。
  - `python yscb.py dev check --all`：5 Total, 5 Passed, 0 Failed (agents-workflow, core, dev, knowledge-db, server 全數通過)。
  - `python yscb.py install agents-workflow@build`：成功安裝最新套件，自動觸發物化發布。
  - `python yscb.py agents-workflow release --force`：48 檔案成功物化發布；後續無變更發布立即命中 Stage 0 短路 (0 I/O)。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed。
- **結案狀態**：`Completed`
