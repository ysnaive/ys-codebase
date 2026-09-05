# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：進入 sub 05（主計畫分類下之最終子計畫：流水線解耦與生態系驗收）。拆解 1,800 行 Monolithic `engine.py` 為 Pipeline 架構；核驗對外 CLI 契約；全套件純化測試 100% 回歸；完成 Dogfooding 閉環與發布。
- **核心目標**：
  1. **Monolithic `engine.py` 職責拆解與流水線化**：將當前 1,765 行龐大 God Object 中近 700 行之終端 Markdown 格式化器（`format_callers_output`、`format_callees_output`、`format_impact_output`、`format_search_output` 與預算計算）解耦至專屬模組；將索引建置與增量熱補丁流程流水線化。
  2. **維持門面契約零破壞 (Zero-Breaking Facade API)**：`KnowledgeEngine` 頂層 Facade 類別所有既有 Public 方法（`search`、`act_callers`、`act_callees`、`act_impact`、`status`、`scan`、`bundle`、`clean` 等）保持 100% 簽名相容，內部無縫委派。
  3. **生態系 CLI 契約實機檢驗**：實機驗證 `python yscb.py knowledge-db search/callers/callees/impact/status` 之 `--json` 與純文字輸出結構完整性。
  4. **全套件測試 100% 綠燈守門**：純化後之 12 大測試套件（121 個測試案例）全部 100% 通過，0 Failed、0 Unknown。
  5. **Dogfooding 閉環與知識庫登記**：完成本地 `@build` 物化驗收，登記設計決策筆記（`DN-12`），同步文檔與總結里程碑 5。
  6. **檢索輸出 8,000 字元上限與全域重複資訊極致剔除**：CLI 輸出預算嚴格限制為 8,000 字元；實作通用切片純化與去重機制 (`UniversalRedundancyFilter`)，徹底剔除任何與已呈現元資料重複之資訊（包含但不限於：Docstring 註解重疊、Markdown Header 重疊、檔案標頭授權樣板、連續空行等），最大幅度釋放空間以承載高價值可執行邏輯代碼，達成極致資訊密度。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁改動任何外部 CLI 指令名稱或對外契約（維持向下相容）。
  - 嚴禁在未獲授權時執行 `dev bump` 或 `dev release`（嚴格維持日常開發軌道 A `@build`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 格式化器解耦至 `formatter.py`**：將 `engine.py` 中佔據 700+ 行的 CLI/Markdown 呈現層代碼完整收斂至 `formatter.py`，定義 `ResultFormatter` 處理動態預算、Markdown 鏈接與 JSON 序列化封裝，`KnowledgeEngine` 內部委派調用。
- **[P00:DR-02] 索引建置與熱修復解耦至 `pipeline.py`**：將多空間倒排索引與向量索引之建置 (`build_unified_index`)、增量熱補丁嗅探 (`_hot_patch_unified_index`) 及快取序列化流水線化，抽離至專屬 `IndexingPipeline`。
- **[P00:DR-03] `KnowledgeEngine` 維持輕量協調中樞 (Thin Orchestrator)**：`KnowledgeEngine` 保留為高內聚門面，負責各子系統組裝、參數透傳與上下文注入，行數目標降至 $\le 450$ 行。
- **[P00:DR-04] 雙軌開發守門與 Dogfooding 閉環**：依據 `yscb-module-dev` 規範，實作完成並跑通沙盒測試後，以 `python yscb.py install knowledge-db@build --force` 進行本地物化驗收，並以實體指令檢驗真實代碼庫檢索。
- **[P00:DR-05] 全域重複資訊剔除 (Universal Redundancy Purge) 與 8,000 字元極致資訊密度最大化**：將 `AUTO_BUDGET_CHARS` 下修至 8,000（衰減閾值調整為 3,500 / 6,000 / 7,000）；於 `formatter.py` 實作多層次通用純化機制，自動比對並剔除任何與已呈現元資料（名稱、簽名、摘要、標題、授權樣板等）高度重疊或重複之內文，消除冗餘佔位，確保 8,000 字元內的每一字元皆為最高資訊密度之真實邏輯代碼。

---

## 3. 開放議題與確認紀錄

- [x] 是否影響現有 121 個單元測試？（已評估：所有測試皆調用 `KnowledgeEngine` 公開方法，保持 Facade 契約一致即可達成零回歸）。
- [x] 是否需要改動 CLI 門面 `scripts/cli.py`？（已評估：無須改動，CLI 僅依賴 `KnowledgeEngine` 公開方法）。
