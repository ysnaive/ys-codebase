# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：agents-workflow 模組全面遷移與升級 (Module agents-workflow Migration & Upgrade)  
> 建立日期：2026-08-25  
> 所屬主計畫：無 (分類型主計畫 Umbrella)  
> 計畫類型：Refactor / Migration / Ecosystem  
> 狀態：`Discussing`  
> 擴充項目：無  
> 模板版本：v1.4  

---

## 1. 使用者原始需求與意圖 (User Intent)

在 YS-Codebase 核心骨架（無狀態超薄宿主、Core 微內核、Dev 開發工具箱、四段版本號、雙軌發布與 Zip 單檔分發體系）全面落成並完成安全加固後，正式啟動 **`agents-workflow`** 模組的全面遷移與架構升級主計畫。

### 核心目標與意圖
1. **標準微內核模組化落地**：
   - 將 `agents-workflow` 作為標準一等公民模組建立於 `source/agents-workflow/`。
   - 具備標準 `manifest.json`、宣告式 `contributes`（CLI 指令、語意 URI 協議、配置注入）。
2. **SOP 工作流資產與模板現代化重構**：
   - 遷移並升級 SOP 流程庫（`NewPlan`, `Continue`, `Discuss`, `Review`, `Pause`, `ContextInit`, `Idea`, `Research`, `DocumentationStandards` 等）。
   - 遷移並升級標準文檔模板庫（`P00` ~ `P07`, `FT_plan`, `umbrella_overview`, `R01` 等）。
3. **CLI 治理工具鏈與多 IDE 動態編譯注入**：
   - 實作 `agents-workflow` 核心 CLI 治理子指令（`verify`, `scan`, `docs`, `ext`, `archive` 等）。
   - 實作多 IDE 工作流動態生成編譯器（Google Antigravity、Claude Code、Cursor 等 IDE 之 `.agents/` 與規則檔案生成）。
4. **全生命週期 Hook 治理與自動化測試驗證**：
   - 對接微內核 Hook（`scripts/hook.core.py` 監聽安裝、升級與重載事件）。
   - 建立 100% 覆蓋的合約測試與自包含沙盒測試套件。

---

## 2. 核心方針與增量原則 (Incremental Strategy)

依開發者指示，本主計畫採**嚴格增量式 (Incremental) 推進**，避免跨度過大：
- **逐步引導**：由開發者按步驟逐步引導，每一小步聚焦於單一最小完整功能閉環。
- **穩紮穩打**：完成當前步驟的規格、實作與測試驗證後，再視需要規劃下一步。

---

## 3. 開放議題與第一步請示

- [ ] **第一步聚焦點確認**：請示我們第一步要先聚焦於哪一個最小核心（例如：先透過 `dev create agents-workflow` 建立最純淨的模組骨架與基礎 Manifest 宣告）？
