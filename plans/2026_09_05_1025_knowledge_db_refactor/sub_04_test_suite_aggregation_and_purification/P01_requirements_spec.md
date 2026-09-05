# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_04_test_suite_aggregation_and_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 測試套件架構整併與同質小檔聚合 | 將現有 20 個分散之測試檔整併為 10~12 個高內聚測試套件：整併圖譜家族 (`test_call_graph.py` + `test_networkx_graph.py` ➔ `test_graph.py`)、解析器家族 (`test_parsers.py` + `test_spice_parser.py` + `test_web_parsers.py` ➔ `test_parsers.py`)、檢索家族 (`test_retrieval.py` + `test_search_aggregation.py` ➔ `test_retrieval.py`)、熱重載家族 (`test_incremental_hot_reload.py` + `test_jit_hot_healing.py` ➔ `test_hot_reload.py`)。 | P0 | [P00:DR-01] |
| **FR-02** | 全面補齊 `self.mark_passed()` 根除 Unknown | 依據 Dev 測試框架 3-State 分類規範，全面盤點並為全套件測試案例方法補齊 `self.mark_passed()`，徹底根絕目前 115+ 個 `Unknown` 假未驗狀態，達成 100% Passed。 | P0 | [P00:DR-02] |
| **FR-03** | 4-Tier 需求層級分流標註 | 依執行耗時與相依性實施分流標註：純記憶體邏輯標註 `@require(Requirement.LOGIC)`；多進程實體打包、大型 Gzip 快取與重度磁碟 I/O 標註 `@require(Requirement.WORKFLOW)`；壓力與效能量測標註 `@require(Requirement.PERF)`。日常預設快測僅跑 LOGIC。 | P0 | [P00:DR-03] |
| **FR-04** | 淘汰過時正則與重複同質案例 | 清理早期手刻正則解析狀態機之遺留案例、已刪除同義詞庫之測試、重複的 Mock 夾具與同質重複的邊界斷言，精簡代碼體積。 | P0 | [P00:DR-04] |
| **FR-05** | 0 邏輯遺失與覆蓋率守門 | 整併純化過程嚴格維持所有功能需求 (FT) 與邊界情況 (ET) 的有效斷言，全生態系單元測試 100% 通過，0 業務邏輯防禦遺漏。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 測試案例漏加 `self.mark_passed()` | 透過靜態檢查與測試執行 Diagnostic Summary 確認 `Unknown: 0`，漏加者立即補正。 |
| **EC-02** | 測試檔案整併後 Fixture 命名或暫存目錄衝突 | 測試類別內部嚴格使用 `tempfile.TemporaryDirectory()` 上下文管理器或獨立前綴方法，杜絕測試間跨案例污染。 |
| **EC-03** | 舊測試檔刪除後殘留 `__pycache__` 導致模組探索異常 | 執行測試重構後，主動清理對應舊檔之 `.pyc` 快取，確認測試探索清冊純淨。 |
| **EC-04** | 多進程打包測試在並行執行時產生鎖競爭 | 重度多進程測試明確標註為 `WORKFLOW`，日常快測隔離不執行，僅在全量回歸時調用。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 測試檔案精簡度 | `source/knowledge-db/tests/` 測試檔數量由 20 個精簡至 $\le 12$ 個，消除碎片化小檔。 |
| **NFR-02** | 狀態回報純淨度 | 執行 `python yscb.py dev test knowledge-db --quiet`，狀態回報中 `Unknown: 0` 且 `Fail: 0`。 |
| **NFR-03** | 日常快測耗時 | 預設模式（`LOGIC`）日常跑測回饋時間穩定在 $\le 3.5\text{s}$ 內。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `DN-DEV-08`：`YSCBTestCase` 覆寫 `_callTestMethod` 於 `tearDown` 執行三態分類，未顯式標註 `self.mark_passed()` 且未拋出異常之測試案例將被自動歸類為 `UNKNOWN`，造成測試報告統計污染。
- **`[!IMPORTANT]`** 4-Tier 分流標註標準：重度實體沙盒或真實多進程打包案例必須標註 `@require(Requirement.WORKFLOW)`，避免日常快測耗時過長。

---

## 5. 關鍵決策紀錄 (Key Decisions)

- **[P01:DR-01] 測試套件整併四大拓撲**：
  1. `test_graph.py`：整併 `test_call_graph.py` + `test_networkx_graph.py`。
  2. `test_parsers.py`：整併 `test_parsers.py` + `test_spice_parser.py` + `test_web_parsers.py`。
  3. `test_retrieval.py`：整併 `test_retrieval.py` + `test_search_aggregation.py`。
  4. `test_hot_reload.py`：整併 `test_incremental_hot_reload.py` + `test_jit_hot_healing.py`。
- **[P01:DR-02] 4-Tier 需求標註映射標準**：
  - 預設模式執行 `LOGIC + ENV`。
  - `WORKFLOW` 與 `PERF` 僅在顯式參數或全量發布守門時執行。
