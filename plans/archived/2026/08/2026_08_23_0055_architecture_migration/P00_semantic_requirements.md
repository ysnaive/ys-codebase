# 語意化需求書 (Semantic Requirements)

> 功能名稱：架構轉型遷移、SOP 規範對齊、Dogfooding 流水線與 Changelog 防呆加固 (Architecture Transition, SOP Sync, Dogfooding & Changelog Guardrails)  
> 建立日期：2026-08-23  
> 計畫類型：Refactor / Architecture  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Refactor / Architecture] 語意化需求

> 相關調研報告參照：
> - [R01_architecture_migration.md](./R01_architecture_migration.md) (架構轉型完備性驗證、地毯式掃描、SOP 對齊與 Changelog 加固)
> - [R02_dogfooding_pipeline_guardrails.md](./R02_dogfooding_pipeline_guardrails.md) (Dogfooding 自引用標準作業流水線與防呆紀律)

### 現況痛點 (Current Pain Points)

- **痛點 1 (純靜態 Workflow 痛點已透過新工具鏈克服，但 SOP 文檔尚未全面聯動)**：專案已成功開發並驗證 100% 零依賴的 `ys-codebase` 模組化工具庫（含 `yscb_installer.py`, `yscb_cli.py`, `yscb_core` SDK, 2x2 設定協定, 語意 URI 協定, IDE 工作流生成器等），但在現有 SOP 工作流文件（如 `Review.md`、`DocumentationStandards.md`、`NewPlan.md`、`AGENTS.md`）中，部分新增定式命令（如 `docs audit`、`docs new-topic`、`ext list/show`）尚未顯式寫入操作步驟中，開發者與 Agent 缺少直接調度指引。
- **痛點 2 (Dogfooding 自引用環境下的 Agent 混淆與覆蓋風險)**：本專案同時具備源碼開發空間 (`:/ys_codebase/`)、測試空間 (`:/test/`) 與自引用消費空間 (`:/` 下的 `modules/` 及 `.agents/`)。Agent 容易誤將修改直接寫入 `modules/` 或根目錄腳本，導致下次執行 `build` 或 `install` 時改動被無聲覆蓋 (Silent Overwrite)；或改了源碼卻未執行完整閉環同步。
- **痛點 3 (changelog.md 建立時機滯後與驗證工具盲區)**：`NewPlan.md` Phase 0 未強制同時初始化 `changelog.md`，且 `verify_plan.py` 忽略檢查 `changelog.md`，導致計畫內部事件與決策日誌容易被遺忘或延遲建立。
- **痛點 4 (中央標準庫與 IDE 工作流的一致性)**：在模組 source (`ys_codebase/source/agents-workflow/`)、自引用安裝產物 (`modules/agents-workflow/`) 與 IDE 整合目錄 (`.agents/workflows/`) 之間，需確保 SOP 文件微調後能透過標準構建與生成流程無損同步，保持 100% 一致。

### 期望演進形態 (Desired End State)

- **期望狀態 1 (SOP 定式工具鏈無縫閉環)**：
  - **`Review.md`**：步驟 2 引入 `ext list/show`，步驟 3 引入 `docs audit` 自動化死鏈/Frontmatter 檢查。
  - **`DocumentationStandards.md`**：追加「🛠️ 知識庫定式維護工具鏈」章節 (`docs init`, `docs audit`, `docs new-topic`)。
  - **`NewPlan.md`**：Phase 0 步驟 1/2 強制載明「建立目錄時必須【同時】建立 `P00` 與 `changelog.md`」；Phase 4/7 融入 `docs new-topic` 生成指引；目錄與結案規範融入 `archive` 指令。
  - **`AGENTS.md` / `AGENTS.template.md`**：定式作業 CLI 指令清單補齊 `<docs|ext>`，明確區隔計畫日誌與全域日誌。
- **期望狀態 2 (Dogfooding 雙層防禦體系落地)**：
  - **支柱一（靜態公理）**：將三層空間權限邊界（空間 ① 源碼開發 `:/ys_codebase/` ➔ 空間 ② 測試驗證 `:/test/` ➔ 空間 ③ 自引用消費 `:/`）與標準四步流水線正式寫入 [AGENTS.md](file:///H:/UseFolder/CodeRepo/ys_codebase/AGENTS.md) 專案特化規範（第 4 節）與 [docs/_project/CONTRIBUTING.md](file:///H:/UseFolder/CodeRepo/ys_codebase/docs/_project/CONTRIBUTING.md)。
  - **支柱二（動態守門）**：新建 `extensions/dogfooding_pipeline_ext.md` 專案特化擴充，提供 Stage 1~4 全流程 Checklist 驗收規範。
- **期望狀態 3 (定式驗證工具加固與盲區消除)**：
  - 更新 `verify_plan.py`，將 `changelog.md` 納入剛性存在性與標頭格式檢查，若缺失則回報 Warning/Error。
- **期望狀態 4 (構建、打包與回歸測試 100% 驗證)**：
  - 更新源碼庫中的工作流與腳本後，重新執行 `python yscb_cli.py installer build agents-workflow` 與 `--ide-antigravity` 生成，並維持 23 項自動化回歸測試 100% 通過。

### 不可破壞的約束 (Hard Constraints)

- **約束 1 (零外部依賴與向後相容)**：所有文檔更新與工具調用指引嚴禁引入任何 Python 第三方庫，維持純標準庫實現。
- **約束 2 (SOP 核心紀律不變量)**：維持「零臆測、可追溯、分級管控」、「嚴禁連發」、「嚴禁空降實作」、「Checkpoint 強制等待」與「Local-First 排查保護」等核心紀律 100% 不變。
- **約束 3 (Dogfooding 空間邊界鐵律)**：`modules/**` 與 `.agents/**` 視為唯讀發布物，任何源碼變更 100% 只能在 `ys_codebase/` 進行，並必須透過 `run_regression.py` 驗證後才可更新自引用產物。

---

## ❓ 開放議題紀錄 (Open Questions / Issues)

- [x] **議題 1 (地毯式掃描)**：經地毯式掃描 9 大工作流、15 份模板與 5 份全域規範，已確認模板本身完全健全，優化聚焦於 4 份核心規範文件（`Review.md`、`DocumentationStandards.md`、`NewPlan.md`、`AGENTS.md`）之定式工具指引聯動。
- [x] **議題 2 (Dogfooding 規範確立)**：已完成 R02 調研，明確制定三層空間邊界與標準四步閉環流水線（源碼 ➔ build ➔ regression ➔ install / ide-gen）。
- [x] **議題 3 (雙層防禦落地方案)**：確立透過「AGENTS.md 專案特化規範 (第 4 節) + 新建 extensions/dogfooding_pipeline_ext.md (動態 Checkpoint)」進行雙層防禦。
- [x] **議題 4 (Changelog 防呆加固)**：確立在 `NewPlan.md` Phase 0 強制伴隨初始化 `changelog.md`，並於 `verify_plan.py` 消除檢查盲區。

---

## 📝 變更歷史 (Revision History)

| 日期 | 版本 | 變更說明 | 變更者 |
| :--- | :--- | :--- | :--- |
| 2026-08-23 | v0.1 | 初始化 Phase 0 語意化需求草稿與 R01 調研報告關聯 | Agent |
| 2026-08-23 | v0.2 | 完成全量工作流與模板地毯式掃描，收斂 4 份核心文件微調方案併入 R01 與 P00 | Agent |
| 2026-08-23 | v0.3 | 完成 R02 Dogfooding 自引用流水線調研與雙層防禦落地方案確認 | Agent |
| 2026-08-23 | v1.0 | 開發者確認 P00 語意需求定稿 (Confirmed)，進入分流層級判定 | Agent |
| 2026-08-23 | v1.1 | 納入 changelog.md Phase 0 剛性伴隨初始化與 verify_plan.py 工具加固需求 | Agent |
