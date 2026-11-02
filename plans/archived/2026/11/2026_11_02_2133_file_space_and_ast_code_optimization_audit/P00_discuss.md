# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：file-space 與 ast 模組業務代碼五維度靜態診斷與重構審計  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_2133_file_space_and_ast_code_optimization_audit  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：`/blind-subagent /code-optimizer 審計本次系列計畫 file-space 和 ast 的內容` $\to$ `立即原地升級實作執行 Mode A 無損重構 /auto`
- **核心目標**：針對 `ys_codebase/source/file-space/`（Layer 1 空間與指紋底座）與 `ys_codebase/source/ast/`（Layer 2 靜態語法樹、雙層分部符號與呼叫拓撲核心引擎）兩個模組，透過 `/blind-subagent` 無上下文盲眼子代理執行 `/code-optimizer` 五維度（`D1`~`D5`）靜態診斷、死代碼雙重查證（`ast callers` + `knowledge-db search`）與 `S1`~`S6` 外科手術重構評估，產出 `R01_code_optimization_audit.md`，並原地升級執行 `Mode A` 無損重構。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `module:ast` 呼叫拓撲（`ast outline / callers / callees / impact`）與 `module:knowledge-db` 全文檢索（`knowledge-db search`）進行雙重引用查證。
- **邊界排除 (Explicitly Excluded)**：外部 CLI 指令契約（`yscb.py file-space ...` 與 `yscb.py ast ...`）與核心業務引擎契約（`FileSpaceManager`、`FingerprintScanner`、`ASTEngine`）保持 100% 行為無損，嚴禁破壞既有測試語意；自動化測試集僅配合 `Mode A` 過渡別名拔除而對齊至單一正統入口（Single Canonical Entry）。
- **架構影響範圍**：`ys_codebase/source/file-space/`、`ys_codebase/source/ast/`（以及跨模組呼叫方 `ys_codebase/source/knowledge-db/`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 檢視範圍定錨**：鎖定多模組範圍（`ys_codebase/source/file-space/` 與 `ys_codebase/source/ast/`），遵循包含式三層範圍探索策略（完整涵蓋兩模組內部各業務檔案之 `S1`~`S6` 微觀分析、模組內跨檔耦合拓撲與跨模組入口契約）。
- **[P00:DR-02] 生命週期與相容性模式 (`Mode A`)**：經開發者拍板採用 **`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`**——強制單一正統入口（Single Canonical Entry），零容忍清理過渡別名、薄轉發層、孤兒死代碼與工單註解噪音，並盤點需同步更新之內部/跨模組與測試呼叫點。
- **[P00:DR-03] 代理執行軌道 (`軌道 2B/3B 盲眼子代理`)**：依開發者顯式指定 `/blind-subagent`，分別針對 `module:file-space` 與 `module:ast` 平行派發兩個獨立的零錨定盲眼子代理（嚴守 `BlindSubagentStandards.md` 黑盒隔離與誠實收斂鐵律，嚴禁違反四大防過度設計紅線強湊問題），匯流完成跨模組交叉查驗後落檔 `R01_code_optimization_audit.md`。
- **[P00:DR-04] 原地升級執行 `Mode A` 無損重構 (`/auto`)**：經開發者審閱 `R01_code_optimization_audit.md` 後拍板選擇出口 A「立即原地升級實作 (`/auto`)」，將計畫類型由 `Research` 升級為 `Refactor`，依據 `R01` 審計處方連續完成 `P01-05_auto.md` 規格、`S1`~`S5` 外科手術重構與 `P06_test_plan.md` 測試守門驗收。

---

## 3. 開放議題與確認紀錄

- 前置三維度定錨（範圍：`file-space` + `ast`、模式：`Mode A`、軌道：`/blind-subagent` 平行盲審）已全數確認，進入步驟 2 執行盲眼診斷與 `R01_code_optimization_audit.md` 落檔。

