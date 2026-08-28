# 需求規格說明書 (Requirements Specification)

> 功能名稱：Core Contributes 系統檔案結構升級 (Core Contributes File Structure Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_01)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  


---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 目錄化 Contributes 標準結構 | 確立 `source/<module>/contributes/<target>.json` 為全生態系唯一官方標準貢獻檔案結構。模組向目標 `<target>` 貢獻之內容獨立儲存於專屬檔案中。 | P0 | [sub_01:P00:DR-03] |
| **FR-02** | Contributes 雙階聚合引擎重構 | 重構 `core.contributes.ContributesAggregator`：<br/>1. **階層 ① (模組貢獻)**：掃描已安裝模組之 `module://<donor>/contributes/<target>.json`，遞迴注入 `__provider__ = donor` 標記並拓撲合併。<br/>2. **階層 ② (專案特化注入與覆蓋)**：依然完整掃描專案 `config://<target>/config.project.json`（與 `config.local.json`）中之 `"contributes"` 物件，疊加於模組基礎貢獻之上，允許下游專案進行特化客製與優先覆蓋。<br/>3. **物化持久化**：聚合結果持久化物化寫入 `cache://<target>/contributes.merged.json`。 | P0 | [sub_01:P00:DR-03], [sub_01:P00:DR-05] |
| **FR-03** | 舊版相容代碼全面清算 (Breaking Clean) | 徹底移除 `ContributesAggregator` 內部對 `manifest.json` 下 `"contributes"` 欄位與根目錄 `contributes.<target>.json` 之解析邏輯，實現 100% 純淨單一路徑。 | P0 | [sub_01:P00:DR-03] |
| **FR-04** | 全模組 Manifest 瘦身與 Contributes 檔案遷移 | 將現有 4 大核心模組之貢獻宣告自 `manifest.json` 移出至 `contributes/<target>.json`：<br/>- `core`: `contributes/core.json`, `contributes/agents-workflow.json`<br/>- `dev`: `contributes/core.json`, `contributes/agents-workflow.json`<br/>- `knowledge-db`: `contributes/core.json`<br/>- `agents-workflow`: `contributes/core.json`, `contributes/agents-workflow.json`<br/>`manifest.json` 僅保留 `name`, `version`, `description`, `entry`, `dependencies`。 | P0 | [sub_01:P00:DR-03] |
| **FR-05** | 消費端 SDK 100% 統一收斂 | 全面重構消費端模組，廢除所有手寫檔案掃描，統一調用 `core.contributes.get(target, key=None)`：<br/>1. `core.providers.get_agents_cli_guild`: 改自 `contributes.get("core", "commands")` 讀取並以 `__provider__` 分組。<br/>2. `core.engine.act_get_installed_commands_summary`: 改自 `contributes.get("core", "commands")` 讀取。<br/>3. `knowledge_db.space.SpaceManager`: 廢除手寫遍歷，改自 `contributes.get("knowledge-db")` 讀取 `spaces` 與 `thesaurus`。<br/>4. `agents_workflow.compiler.ArtifactCompiler`: 廢除手寫遍歷，改自 `contributes.get("agents-workflow")` 讀取 `export`, `token`, `insert`, `release_target`。 | P0 | [sub_01:P00:DR-04] |
| **FR-06** | 拔除 `module.source://` 空間穿透反模式 | 徹底自 `agents_workflow/compiler.py` 與 `core/providers.py` 清理探知 `module.source://` 的歷史穿透代碼，恪守三層空間公理。 | P0 | [sub_01:P00:DR-04] |
| **FR-07** | 專案特化注入相容性 | 支援專案於 `config://<target>/config.project.json` 中宣告 `contributes.<target>` 自訂擴充（例如覆蓋特定指令說明、追加專案專屬 space 或替換 token insert 內容），專案特化宣告擁有最高優先權。 | P0 | [sub_01:P00:DR-05] |


---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Donor 模組無 `contributes/` 目錄或為空 | 引擎安全掠過，不拋出例外，維持該模組無貢獻之正常空字典狀態。 |
| **EC-02** | `contributes/<target>.json` 語法錯誤或檔案損毀 | 捕獲 `json.JSONDecodeError`，印出警告日誌並略過該損毀檔案，不阻斷其他模組正常聚合。 |
| **EC-03** | 查詢 SDK (`core.contributes.get`) 時快取未生成或損毀 | 觸發自動自愈（Auto-Healing）流程，即時呼叫 `ContributesAggregator().scan_and_inject()` 重新生成快取並回傳正確資料。 |
| **EC-04** | Target 模組尚未安裝或不存在於 `module://` | 引擎安全接收並於快取中保留該 target 之物化資料，待 target 模組安裝或載入時立即可被 SDK 查詢。 |
| **EC-05** | 重複 List 項目合併與唯一性 | `_deep_merge` 對於 List 結構執行基於內容的去重追加，避免同一個宣告重複堆疊。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部相依 (Zero Dependency) | 100% 使用 Python 3 原生標準庫（`os`, `json`, `shutil`），禁止引入任何第三方套件。 |
| **NFR-02** | Manifest 瘦身成效 | 全庫 `manifest.json` 行數大幅減少（`agents-workflow/manifest.json` 由 554 行縮減至 < 20 行，降幅 >95%）。 |
| **NFR-03** | 效能與快取命中 | 快取命中時 `core.contributes.get()` 讀取耗時 < 2ms；全模組聚合掃描耗時 < 15ms。 |
| **NFR-04** | 回歸測試品質閘門 | 全庫 4 大模組所有單元測試與全系統沙盒回歸 100% Passed（維持既有 163+ 測試案例全數通過）。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` Dogfooding Axiom (三層空間公理)**：
  運行期代碼與測試沙盒一律依賴 `module://`，所有依賴在測試前置階段由 `dev build` 自動物化至沙盒，模組內部嚴格禁止回頭探測 `source/`。
- **`[!IMPORTANT]` 徹底純淨重構 (Breaking Migration)**：
  本次不保留舊版向下相容，所有模組之 source 源碼必須在 Phase 5 同步建立 `contributes/<target>.json`，並自 `manifest.json` 移除 `"contributes"`。
- **`[!CAUTION]` 專案組態覆蓋優先權**：
  專案級組態 `config://<target>/config.project.json` 中宣告的 `contributes` 擁有最高優先權，需在模組層級合併後疊加覆蓋。
