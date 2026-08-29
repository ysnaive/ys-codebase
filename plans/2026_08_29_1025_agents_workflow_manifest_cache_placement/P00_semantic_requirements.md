# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：agents_workflow_manifest_cache_placement  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 計畫類型：Bug Fix  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「修復 agents-workflow 的產出快取錯置問題: 現有: 統一存放於 storage://agents-workflow/release_manifest.json。預期修正: 來源為 config.local: 儲存於 cache，使用絕對路徑；來源為 config.project: 儲存於 storage，使用 project:// 協議路徑」
- **核心目標**：
  1. **修正 Manifest 儲存空間錯置**：
     - 若 Target 來源為本機個人組態 (`config.local.json`)，其發布清單應儲存於快取空間 (`cache://agents-workflow/release_manifest.json`)，並使用本機「絕對路徑」紀錄。
     - 若 Target 來源為專案團隊組態 (`config.project.json`)，其發布清單應儲存於持久空間 (`storage://agents-workflow/release_manifest.json`)，且路徑一律使用「`project://` 語意協議路徑」紀錄，徹底杜絕本機絕對路徑污染 Git 版本庫。
  2. **支援雙來源/混合情境之發布與孤立檔案清理 (Pruning)**：
     - 當 Local 與 Project 同時存在啟用之 Targets（或切換 Target）時，正確區分並分別處理各自的快取清單與孤立檔案清理。
  3. **保持與 Core URI 協議及現有原子發布交易 100% 相容**。
  4. **全專案跨平台換行符號 (LF) 歸一化**：
     - 解決 Windows 環境下 Python 文字寫入、Zip 解壓與 Git 換行符號不一致問題，達成全平台一致純 LF。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更既有 `ArtifactCompiler` 的模板佔位符解析與 2-Stage 編譯流水線核心邏輯。
  - 不更動 `ReleaseTargetManager` 對 Local/Project 兩層 Targets 的讀寫層級判定原則。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 空間分流與路徑規範明確化**：
  - **Local Targets (Tier 1, 本機私有)**：寫入 `cache://agents-workflow/release_manifest.json`（受 Git 忽略），記錄實體絕對路徑。
  - **Project Targets (Tier 2, 團隊共用)**：寫入 `storage://agents-workflow/release_manifest.json`（受 Git 追蹤），記錄 `project://...` 相對語意路徑。
- **[P00:DR-02] 混合 Target 發布雙軌獨立 Manifest 機制**：
  - 當同時啟用 Local 與 Project 兩層 Targets 時，發布引擎分別維護兩份獨立的 Manifest：
    - `storage://agents-workflow/release_manifest.json`：僅記錄由 Project 層 Targets 所物化之檔案（使用 `project://` 語意協議路徑格式）。
    - `cache://agents-workflow/release_manifest.json`：記錄由 Local 層 Targets 所物化之檔案（使用實體絕對路徑）。
  - 各軌獨立依據各自的歷史 Manifest 進行雙階 Diff 檢核與孤立舊檔案清理 (Pruning)。
- **[P00:DR-03] 現有 Storage Manifest 即刻標準化**：
  - 將專案現存之 `ys_codebase/storage/agents-workflow/release_manifest.json` 內容中既有的絕對路徑全面標準化轉換為 `project://` 格式，徹底杜絕跨機協作與 Git diff 污染。
- **[P00:DR-04] 全專案換行符號 (LF) 剛性歸一化機制**：
  - **Git 層級防護**：於專案根目錄建立 `.gitattributes`，宣告純文字檔案一律使用 `eol=lf`。
  - **Toolchain 寫入防護**：`agents-workflow` 及生成工具寫檔時顯式指定 `newline="\n"`，杜絕 Windows Python 預設自動轉換為 `\r\n`。

---

## 3. 開放議題與確認紀錄

- [x] **開放議題 1 (混合發布情境)**：確認分別寫入兩個獨立 Manifest（`storage` 存 project targets 的 `project://` 清單，`cache` 存 local targets 的絕對路徑清單）。
- [x] **開放議題 2 (既有 Storage Manifest 處置)**：確認直接將現有 `storage/agents-workflow/release_manifest.json` 內容標準化轉換為 `project://` 格式。
- [x] **開放議題 3 (換行符號歸一化)**：確認一併納入本計畫處理（建立 `.gitattributes` 與工具鏈 `newline="\n"` 規範）。


