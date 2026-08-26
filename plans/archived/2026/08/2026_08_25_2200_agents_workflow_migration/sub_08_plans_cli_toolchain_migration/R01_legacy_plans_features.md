# R01: 舊版 Plans CLI 工具鏈功能調研報告 (Legacy Plans Features Survey)

> 計畫名稱：Plans CLI 工具鏈補齊與舊版功能遷移 (`sub_08_plans_cli_toolchain_migration`)  
> 調研日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 報告狀態：Completed  

---

## 1. 調研背景與目標

在 `agents-workflow` 模組從舊版架構遷移至 YSCB 微內核與一等公民語意 URI 體系後，核心骨架、模板編譯、一鍵初始化與發布交易已先行完成。本調研旨在透過 Git 歷史與代碼庫深入回溯舊版 4 大 plans 工具鏈的完整規格、演算法、安全防護與邊界條件，為本次遷移與現代化改造提供權威依據。

---

## 2. 舊版 4 大 Plans 工具鏈功能矩陣

透過對 Git 歷史 commit（`bac97ba`, `ab8fffc`, `0a0f6bf`）的調研，舊版工具鏈包含以下四大腳本與能力：

| 工具名稱 / 舊腳本 | 核心職責 | 關鍵安全防護與演算法 | 支援參數 |
| :--- | :--- | :--- | :--- |
| **1. 計畫歸檔工具**<br/>(`archive_plan.py`) | 將已完成的計畫目錄從 `plans/` 安全搬移至 `archive_plans/YYYY/MM/` | 1. 解析時間戳前綴 `YYYY_MM_` 分流至對應年/月目錄<br/>2. 檢查 `P07_walkthrough.md` / `fast_track_plan.md` / `umbrella_overview.md` 必須為 `Completed`<br/>3. 檢查全域 `CHANGELOG.md` 是否已記載本計畫<br/>4. 自動清理暫時交接檔案 `handoff.md`<br/>5. 目標已存在時阻斷覆蓋 | `<plan_name>`<br/>`--force` (強制略過完成度/CHANGELOG檢查) |
| **2. 狀態掃描矩陣**<br/>(`scan_plan_status.py`) | 結構化掃描進行中與歸檔計畫，輸出 ASCII 狀態矩陣清冊 | 1. 識別 4 大類型：`Umbrella`, `Fast Track`, `Full Track`, `Phase 0`<br/>2. 識別當前 Phase（P01 規劃~P07 完成）<br/>3. 若存在 `handoff.md` 標記為 `(Paused)`<br/>4. 支援主計畫 ➔ 子計畫 `sub_*` 兩層樹狀縮排展示 | `--all`, `-a`<br/>(包含歷史歸檔) |
| **3. 歷史與決策檢索**<br/>(`search_dev_plans.py`) | 跨進行中與歷史計畫檢索全文關鍵字或決策記錄 (DR) | 1. **DR 模式 (`--dr`)**：正則結構化擷取 `[{Phase}:DR-XX]`、`### DR-XX` 標題與結論，自動去重<br/>2. **全文模式**：檢索所有 Markdown 並提供前後行程式碼預覽 | `[query]`<br/>`--dr`<br/>`--year=<YYYY>`<br/>`--month=<MM>`<br/>`--limit=<N>` (預設 20) |
| **4. 計畫合規稽核**<br/>(`verify_plan.py`) | 稽核指定或全量 Dev Plan Markdown 文件的 Header 與格式合規性 | 1. 檢查是否殘留 `<!-- AGENT_GUIDANCE -->` 模板指引未剝除<br/>2. 檢查 Blockquote Header 元數據（`功能名稱`, `建立日期`, `狀態`）<br/>3. 遞迴稽核子計畫目錄 `sub_*` | `[plan_name]`<br/>`--all` (包含歷史歸檔) |

---

## 3. 現代化遷移重構建議 (Modernization in YSCB Architecture)

在舊版實作中，各腳本大量依賴相對路徑爬找 `.agents` 與本機檔案系統；在全新的 YSCB 微內核與 `agents-workflow` 體系中，應進行如下現代化升級：

1. **全面統一為語意 URI 尋址 (Semantic URI SSOT)**：
   - 進行中目錄：`workflow.plans://`
   - 歷史歸檔目錄：`workflow.archived://` (即 `workflow.archived://{YYYY}/{MM}/{plan_name}/`)
   - 專案根目錄：`project://` 與 `project://CHANGELOG.md`
2. **統一整合至 `agents-workflow` CLI 門面**：
   - 舊版分散的 4 個獨立腳本，統一收斂為 `agents-workflow` 的子指令：
     - `python yscb.py agents-workflow plan-archive <plan_name> [--force]` (或 `plan archive`)
     - `python yscb.py agents-workflow plan-status [--all]` (或 `plan status`)
     - `python yscb.py agents-workflow plan-search <query> [--dr] [--year=YYYY] [--month=MM]` (或 `plan search`)
     - `python yscb.py agents-workflow plan-verify [plan_name] [--all]` (或 `plan verify`)
   - 也可提供頂層門面別名或統一命名空間。
3. **支援 Python API 與 CLI 雙軌呼叫**：
   - 封裝為高內聚模組 `agents_workflow/plans/`（`archiver.py`, `scanner.py`, `searcher.py`, `verifier.py`），供程式化調用與自動化測試。

---

## 4. 調研結論收斂

舊版工具鏈的 4 大功能體系具備清晰的互補性：
- **`archive`**：負責生命週期終點的物理移轉與安全檢查；
- **`status`**：負責執行期宏觀進度掌控；
- **`search`**：負責知識與歷史決策 (DR) 追溯；
- **`verify`**：負責工程標準與元數據合規性驗收。
