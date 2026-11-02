# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：全面將 `module:space` 更名為 `module:file-space`（基於 `git diff` 腳本精準掃描替換與反查驗收）  
> 建立日期：2026-11-02  
> 所屬主計畫：`2026_11_02_0339_module_space_feasibility_research`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 「接下來我突然想到 space 這個名字是不是其實不是很好? 語意不夠詳盡吧?」
  2. 「file-space 可能好一些」
  3. 「全面修改，我甚至傾向直接用腳本工具暴力搜尋 "space" 挑掉不是現在 git diff 的內容後直接用腳本替換再做後續反查驗收」
- **核心目標**：
  1. 將本計畫（`sub_01` ~ `sub_03`）新建立與遷移之 `space` 模組、套件、CLI、事件、設定檔、語意 URI、內部變數與知識庫文檔，**全面更名為 `file-space` / `file_space` / `FileSpace`**，消除單字 `space` 語意過於寬泛及與「三層空間（源碼/測試/運行空間）」混淆的問題。
  2. 採用開發者指示之**「`git diff` / 新增檔案範圍鎖定 + 自動化腳本搜尋替換 + 反查驗收」**工作流：先以腳本提取當前工作區相對於 `HEAD` 的所有新增（untracked）與已修改（modified）檔案與變更行，過濾掉不屬於本次 `git diff` 的既有詞彙（如 Markdown 縮排 `2-space`、Python `namespace` / `workspace` 等），執行結構化批量替換與目錄搬移，最後跑反向殘留掃描、模組測試與熱部署驗收。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 100% 沿用 `sub_01` ~ `sub_03` 已驗證完成之架構與邏輯，僅針對命名與識別碼進行全面重構與物理目錄遷移。
- **邊界排除 (Explicitly Excluded)**：
  - 明確排除非本次 `git diff` 範疇之歷史封存檔案（`plans/archived/`）、與檔案空間無關之原生詞彙（如 `workspace`、`namespace`、`whitespace`、`2-space`、`disk space`）以及尚未啟動之 `sub_05` (`agents-workflow` 整合)。
- **架構影響範圍**：
  - **源碼與模組目錄**：`ys_codebase/source/space/` $\to$ `ys_codebase/source/file-space/`（內部套件 `space/` $\to$ `file_space/`）。
  - **宿主與 Contributed 組態**：`ys_codebase/config/space/` $\to$ `ys_codebase/config/file-space/`、`ys_codebase/source/agents-workflow/contributes/space.json` $\to$ `contributes/file-space.json`。
  - **知識庫 모듈與鉤子**：`ys_codebase/source/knowledge-db/`（含 `manifest.json` 依賴 `file-space`、`scripts/hook.space.py` $\to$ `scripts/hook.file-space.py`、`from file_space import ...`、`file_space_weights` / `--file-space` 等全面對齊）。
  - **系統知識庫與運行環境**：`docs/space/` $\to$ `docs/file-space/`、`docs/knowledge-db/`、`yscb.config.json`，以及本機 `.modules/space` 卸載清理與 `file-space@build`、`knowledge-db@build` 重新安裝。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 全面更名對照契約（連字號 `file-space` / 底線 `file_space` / 駝峰 `FileSpace`）**：
  - **模組與 CLI 層 (`file-space`)**：模組名 `file-space`、常駐服務 `file-space-watcher`、Contributes 檔 `contributes/file-space.json`、設定目錄 `config/file-space/`、文檔目錄 `docs/file-space/`、鉤子腳本 `scripts/hook.file-space.py`、快取與語意 URI `file-space.storage://` (`cache://file-space/`)。
  - **Python Package 與符號層 (`file_space` / `FileSpace`)**：套件名 `file_space`、類別名 `FileSpaceManager` / `FileSpaceConfig` / `FileSpaceDef` / `FileSpaceOrigin` / `FileSpaceWatcherServiceWorker` / `FileSpaceError` / `FileSpaceNotFoundError` / `InvalidFileSpaceConfigError`、事件名 `on_file_space_changed`、設定鍵 `file_spaces` / `file_space_weights`、參數與屬性 `file_space` / `file_space_name` / `--file-space`。
- **[P00:DR-02] 基於 `git diff` 邊界鎖定之雙階段腳本替換與反查驗收機制**：
  - **階段 1（掃描與精準替換）**：於暫存腳本中讀取 `git status --porcelain` 與 `git diff HEAD`，僅鎖定本次新增目錄（`ys_codebase/source/space`、`ys_codebase/config/space`、`docs/space` 等）與本次修改檔案中之 `space` 相關識別符（自動排除 `workspace`、`namespace`、`whitespace`、`2-space` 等非目標詞），批次完成檔案/目錄更名與內容替換。
  - **階段 2（反查與實機驗收）**：替換後執行反向稽核腳本檢查 `git diff` 中是否仍有遺漏之裸 `space` 識別符或誤替換，並清理舊 `.modules/space` 與 `.cache/space`，實機通過 `dev check`、`dev test`（`file-space` 與 `knowledge-db`）及 `@build` 熱部署驗證。

---

## 3. 開放議題與確認紀錄

- 開發者已明確指示採用全面修改並透過腳本基於 `git diff` 範圍批量替換後反查驗收，全數需求已確認（`Confirmed`）。

