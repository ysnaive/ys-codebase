# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_10_14_1554_downstream_onboarding_and_ux_guidance  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 「接下來我想完善各模組的下游使用者引導 (UX DX)，你先評估看看當前的教學引導做得如何?」
  2. 「ABC 全做」（涵蓋維度 A：門面與隨包文檔全面翻新、維度 B：CLI 生命週期互動式下一步引導 Next Steps Banner、維度 C：未初始化狀態之自癒引導 Actionable Error Hints）。
- **核心目標**：
  1. **維度 A — 門面與隨包文檔全面翻新 (`README.md` + `docs/README.md` + 5 大 `source/*/README.md`)**：
     - 根目錄 `README.md` 與 `docs/README.md` 補齊 5 大核心模組全景（納入 `server` 模組），更新為 `python yscb.py init` 標準單檔自舉流程、修正 `knowledge-db`（`spaces.<name>.include`、`model download`、`index`）與 `agents-workflow`（`init --default`、純 Skill `.agents/skills/` 架構）的最新安裝與設定教學，並完善各模組之 AI Agent Pre-flight Check 提示框。
     - 翻新 `ys_codebase/source/{core,dev,server,knowledge-db,agents-workflow}/README.md`（隨模組安裝打包至下游 `.modules/<mod>/README.md` 的唯一隨包手冊），統一補齊「下游 5 分鐘快速上手 (Quickstart)」、「正確組態設定指南 (`config.project.json` / `config.local.json`)」與「常見情境 Cookbook」。
  2. **維度 B — CLI 生命週期互動式「下一步引導 (Next Steps Banner)」**：
     - 於 `yscb.py` 的 `cmd_init` 完成全新初始化時，輸出結構化 `[Next Steps]` 引導區塊（提示綁定 `project_root`、檢視狀態及安裝推薦模組 `agents-workflow`, `knowledge-db`, `server`）。
     - 於 `core.installer:Installer.cmd_install` 完成模組安裝後，支援讀取模組 `manifest.json` 之宣告式 `onboarding`（或內建模組引導提示），輸出該模組專屬的 `[Next Steps]` 快速啟動步驟與文件指引。
  3. **維度 C — 未初始化狀態之自癒引導 (Actionable Error Hints)**：
     - 當下游環境尚未配置 `core.project_root` 或 `agents-workflow` 之 `workflow.*://` 路徑（值為 `!undefined`）而調用 `uri resolve`、`uri check` 或 `agents-workflow` 計畫/發布指令時，提供可直接複製執行的修復指令提示（如 `python yscb.py config set core project_root ./` 或 `python yscb.py agents-workflow init --default`）。
- **邊界排除 (Explicitly Excluded)**：
  - 不破壞既有 CLI 自動化測試契約輸出與退出碼（所有新增引導文字均採向後相容附加，不改變既有核心狀態斷言）。
  - 不引入任何第三方套件依賴，維持 100% Python 標準庫實現。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 宣告式模組 Onboarding 引導機制 (`manifest.json` -> `onboarding`)**：
  - 於各模組 `manifest.json` 支援選填之 `"onboarding": ["step 1...", "step 2..."]` 清單（同時於 `dev` 的 `ModuleChecker` 合法欄位白名單中納管），由 `Installer.cmd_install` 在安裝成功後自動渲染 `[Next Steps]` 引導卡片，達成微內核零硬編碼耦合與擴充模組一等公民待遇。
- **[P00:DR-02] 隨包 `source/<mod>/README.md` 與知識庫 `docs/<mod>/README.md` 雙軌定位對齊**：
  - `source/<mod>/README.md` 隨 `.zip` 分發至下游 `.modules/<mod>/README.md`，定位為「下游消費者與擴充開發者的自包含實戰手冊（含 Quickstart、CLI、組態與 SDK）」；根目錄 `README.md` 定位為「全生態系初次引入與 AI Agent 安裝總綱」。
- **[P00:DR-03] 未定義 URI (`!undefined`) 結構化自癒提示**：
  - 在 `core.uri` 拋出未定義協議異常及 `uri check` 診斷報告中，依協議名稱（`project://` vs `workflow.*://`）動態附帶對應的一鍵初始化/設定 CLI 指令提示。

---

## 3. 開放議題與確認紀錄

- [x] 已確認同時涵蓋維度 A（文檔全面翻新）、維度 B（CLI Post-Init / Post-Install 下一步引導）與維度 C（未初始化自癒錯誤提示）。

