# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge_db_parser_and_search_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_1049_knowledge_db_algorithm_optimization  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P02/P03 中皆有完整型態定義、函式簽名與循序資料流承接。
- [x] **邊界防護**：EC-01（候選池集中單檔案）、EC-02（`--ftype` 容錯）、EC-03（C++ 30行超限截斷）皆有具體防禦邏輯。
- [x] **依賴純淨**：NFR-01 ~ NFR-03 確保 100% Python 標準庫、向後相容與 5ms 內聚合高效能。
- [x] **測試前置定稿**：P06_test_plan.md 測試案例 FT-01 ~ FT-08 與 RT-01 全數定稿為 `Confirmed`。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2** | `docs/knowledge-db/user_guide.md` | Modify | 補充 `--ftype` 來源過濾用法說明與樹狀 ASCII 聚合輸出展示範例。 |
| **維度 4** | `docs/knowledge-db/architecture.md` | Modify | 補充 Top-N 動態聚合回填管線演算法、Max + α·ΣRest 積分合併模型與 C++ 多行簽名狀態機說明。 |
| **維度 5** | `docs/knowledge-db/api_reference.md` | Modify | 更新 `UnifiedSymbol` (end_line)、`AggregatedFileResult`、`QueryFilter.ftypes` API 簽名規格。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：當使用者查詢詞在多個超大檔案中分別命中數十個方法時，Top-N 回填是否會引發大量重複掃描導致效能驟降？**  
> 💡 **防護解法**：  
> 回填管線採用**單趟游標推進 (Single-Pass Cursor Scan)**。維護 `file_results: Dict[str, AggregatedFileResult]` 與 `unique_files: Set[str]`。每次從排序後的 Postings 池中依序推進指針，遇重複檔案直接在 $O(1)$ 時間內累加分數並將 Item 插入已排序子陣列（維持最大長度 3），遇新檔案則記錄。當 `len(unique_files) == limit` 或指針抵達池尾時立即終止，整體時間複雜度嚴格控制在 $O(K \log 3)$（其中 $K$ 為掃描之候選命中數，通常 $\le 100$），耗時 $< 1\text{ms}$。

> ❓ **尖銳問題 2：C++ 原始碼中若存在語法錯誤或巨集（例如 `UFUNCTION(...) void Foo(\n...\n)`），多行簽名狀態機是否會失控跨越多個函式？**  
> 💡 **防護解法**：  
> 狀態機設置**三重熔斷守門**：  
> 1. `MAX_SIGNATURE_LINES = 30`：累積超過 30 行未閉合自動強制放棄並清空暫存。  
> 2. 遇到關鍵界定詞（如下一個 `namespace`、`class`、`struct` 宣告行）時強制中斷當前累積。  
> 3. 任何未閉合狀態均安全降級，不拋出任何未捕獲例外，確保單一檔案的局部異常不污染全專案索引。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：**模型層擴充** (`knowledge_db/schema.py`)  
  - `UnifiedSymbol` 新增 `end_line: int = 0`，相容 `to_dict` / `from_dict`。  
  - 新增 `AggregatedItem` 與 `AggregatedFileResult` 資料模型。  
- [ ] **TASK-02**：**解析器 Item 化與深度強化** (`knowledge_db/parsers/`)  
  - `python_parser.py`：AST 遍歷將 Function / Method 提取為獨立 `UnifiedSymbol`，附帶 `end_lineno`。  
  - `cpp_parser.py`：實作多行簽名累積狀態機、Namespace 作用域堆疊、Class 作用域識別。  
  - `csharp_parser.py`：完善 Namespace 堆疊與 Method/Property `end_line` 標記。  
  - `markdown_parser.py`：完善標題、表格、段落精確 `end_line` 計算。  
- [ ] **TASK-03**：**檢索引擎與動態聚合管線** (`knowledge_db/retrieval.py`)  
  - `QueryFilter` 支援 `ftypes: Optional[List[str]]`。  
  - `BM25Engine` 實作副檔名過濾、`search_aggregated` 回填管線與 Max + 0.2·ΣRest 積分合併。  
- [ ] **TASK-04**：**核心引擎與 CLI 樹狀輸出** (`knowledge_db/engine.py` & `scripts/cli.py`)  
  - `KnowledgeDBEngine.search` 對接 `ftypes` 與延遲切片提取。  
  - `scripts/cli.py` 實作 `--ftype` 解析與 Default/Detail/Snippet/JSON 四大樹狀輸出排版。  
- [ ] **TASK-05**：**單元與整合測試編寫** (`tests/`)  
  - 實作 `test_parsers_deep.py` 與 `test_search_aggregation.py`。  
- [ ] **TASK-06**：**Dogfooding 標準閉環與全量回歸**  
  - 執行 Stage 1~4 Dogfooding 流水線，確保 `run_regression.py` 100% Passed。  

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立單趟游標推進演算法（Single-Pass Cursor Scan），保障極致檢索效能。
- **[P04:DR-02]** C++ 狀態機具備三重防禦熔斷機制，保障極限邊界健壯性。
- **[P04:DR-03]** P06 測試計畫（FT-01 ~ FT-08, RT-01）全數定稿，進入 Phase 5 編碼實作。

