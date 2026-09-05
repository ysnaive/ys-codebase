# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_04_test_suite_aggregation_and_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「插入子計畫: test case 聚合與純化，合併邏輯相似之測試，移除過時測試，移除性質重複測試」
- **核心目標**：
  1. **測試套件聚合 (Test Suite Aggregation)**：整併零散與碎片化測試小檔（目前共計 20 個測試檔），依職責領域（語意解析、索引與檢索、調用圖譜與拓撲、掃描與打包、系統與 CLI）整併為高凝聚的測試套件。
  2. **消除過時與重複案例 (Prune Obsolete & Redundant Tests)**：清理經歷 Tree-sitter AST、FastEmbed 向量與 NetworkX 圖譜重構後殘留的過時正則測試、同質邊界測試與重複 Mock 案例，精煉測試代碼。
  3. **根除 Unknown 狀態 (100% Passed Classification)**：全面遵循 Dev 測試框架 3-State 分類規範，補齊所有測試案例之 `self.mark_passed()`，徹底消除目前 115 個 `Unknown` 假未驗回報，達成 100% Passed。
  4. **實施 4-Tier 需求分流 (Tiered Execution Optimization)**：
     - `@require(Requirement.LOGIC)`：純記憶體單元邏輯，預設日常跑測（快測目標 $< 2.5\text{s}$）。
     - `@require(Requirement.WORKFLOW)`：實體磁碟 I/O、ProcessPoolExecutor 多進程打包、大型 Gzip 快取等重度整合流程。
     - `@require(Requirement.PERF)`：效能基準與記憶體壓力測試。
  5. **0 邏輯遺失保證**：測試案例純化整併後，既有業務邏輯與邊界防禦之斷言覆蓋率保持 100%，無任何防禦空洞。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動 `engine.py` 核心流水線重構（保留至 sub_05 處理）。
  - 不修改業務邏輯之 Public API 契約與核心算法（僅專注於 `tests/` 測試套件之結構與品質重構）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 測試套件整併架構與拓撲**：
  - 圖譜與消歧：整併 `test_call_graph.py` 與 `test_networkx_graph.py` ➔ 統一為 `test_graph.py`。
  - 解析器家族：整併 `test_parsers.py`、`test_spice_parser.py`、`test_web_parsers.py` ➔ 統一為 `test_parsers.py`。
  - 檢索與聚合：整併 `test_retrieval.py` 與 `test_search_aggregation.py` ➔ 統一為 `test_retrieval.py`。
  - 增量與熱修復：整併 `test_incremental_hot_reload.py` 與 `test_jit_hot_healing.py` ➔ 統一為 `test_hot_reload.py`。
  - 選擇器與結構：保留 `test_selector.py` 與 `test_schema.py`。
  - 混合檢索：保留 `test_hybrid.py`。
  - 系統層：保留 `test_cli.py`、`test_engine.py`、`test_bundler.py`、`test_scanner.py`、`test_space.py`。
- **[P00:DR-02] 100% 補齊 `self.mark_passed()` 紀律**：每個測試方法成功執行完畢時，強制調用 `self.mark_passed()`，全面根除 115 個 Unknown 狀態。
- **[P00:DR-03] 4-Tier 分流標註標準**：
  - 耗時較長之真實多進程與實體檔案打包測試標註為 `@require(Requirement.WORKFLOW)`。
  - 效能基準測試標註為 `@require(Requirement.PERF)`。
  - 預設跑測（`python yscb.py dev test knowledge-db --quiet`）僅執行 `LOGIC`，達成極速日常回饋。
- **[P00:DR-04] 過時測試淘汰原則**：
  - 淘汰針對舊正則狀態機或已刪除同義詞庫之遺留測試。
  - 消除跨測試檔案之同質 mock 實體重複。

---

## 3. 開放議題與確認紀錄

- [x] **子計畫插入位置**：確認作為 `sub_04`，原流水線重構延後為 `sub_05`。
- [x] **目標通過率與狀態**：追求快測全數 Passed 且 Unknown: 0。
- [x] **分流模式**：採用 Full Track 標準開發推進。
