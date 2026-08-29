# 實作任務清單 (Task Breakdown)

> 功能名稱：knowledge_db_parser_and_search_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_1049_knowledge_db_algorithm_optimization  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：**模型層擴充** (`knowledge_db/schema.py`)  
  - `UnifiedSymbol` 擴充 `end_line: int = 0`，向後相容序列化與反序列化。  
  - 新增 `AggregatedItem` 與 `AggregatedFileResult` 資料模型。  
- [x] **TASK-02**：**解析器 Item 化與深度強化** (`knowledge_db/parsers/`)  
  - `python_parser.py`：AST 遍歷將 Function / Method 提取為獨立 `UnifiedSymbol`，帶出 `end_lineno`。  
  - `cpp_parser.py`：實作多行簽名累積狀態機、Namespace 作用域堆疊、Class 作用域識別。  
  - `csharp_parser.py`：完善 Namespace 堆疊與 Method/Property `end_line` 標記。  
  - `markdown_parser.py`：完善標題、表格、段落精確 `end_line` 計算。  
- [x] **TASK-03**：**檢索引擎與動態聚合管線** (`knowledge_db/retrieval.py`)  
  - `QueryFilter` 支援 `ftypes: Optional[List[str]]`。  
  - `BM25Engine` 實作副檔名過濾、`search_aggregated` 回填管線與 Max + 0.2·ΣRest 積分合併。  
- [x] **TASK-04**：**核心引擎與 CLI 樹狀輸出** (`knowledge_db/engine.py` & `scripts/cli.py`)  
  - `KnowledgeDBEngine.search` 對接 `ftypes` 與延遲切片提取。  
  - `scripts/cli.py` 實作 `--ftype` 解析與 Default/Detail/Snippet/JSON 四大樹狀輸出排版。  
- [x] **TASK-05**：**單元與整合測試編寫** (`tests/`)  
  - 實作 `test_parsers_deep.py` 與 `test_search_aggregation.py`。  
- [x] **TASK-06**：**Dogfooding 標準閉環與全量回歸**  
  - 執行 Stage 1~4 Dogfooding 流水線，確保 `run_regression.py` 100% Passed。  

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 嚴格依 Phase 3/4 規格實作 |

