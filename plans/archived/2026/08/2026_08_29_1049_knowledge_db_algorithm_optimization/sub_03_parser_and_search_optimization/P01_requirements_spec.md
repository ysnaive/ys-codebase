# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge_db_parser_and_search_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_1049_knowledge_db_algorithm_optimization  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **解析器原子 Item 化與精確座標 (Type 1)** | 1. 重構 `PythonParser`、`MarkdownParser`、`CppParser`、`CSharpParser`，使產出之符號皆為具備獨立物理行號區間 `(start_line, end_line)` 的原子 Item。<br>2. Python 解析器將類別方法 (`Method`) 與頂層函式 (`Function`) 提取為獨立 `UnifiedSymbol`，精確帶出 AST `end_lineno`。<br>3. Markdown 解析器為標題、表格、段落精確計算 `end_line`。<br>4. C#/C++ 解析器完善方法/屬性/函式之 `end_line` 邊界標記。 | P0 | [P00:DR-02]<br>[P00:DR-06] |
| **FR-02** | **C++ 解析器深度精準度強化 (Type 2)** | 1. **多行簽名累積狀態機 (Multi-line Accumulator)**：支援跨行參數清單匹配，解決跨行宣告被忽略問題。<br>2. **Namespace 堆疊追蹤 (Namespace Stack)**：追蹤 `{` / `}` 深度，產出完整 `Namespace::Class` Qualified Name。<br>3. **Class 作用域追蹤 (Class Scope Stack)**：識別類別內部方法，以 `kind=METHOD` 產出並記錄所屬類別關聯。 | P1 | [P00:DR-06] |
| **FR-03** | **`--ftype` 檔案類型來源過濾** | 1. `QueryFilter` 新增 `ftypes: Optional[List[str]]` 支援。<br>2. CLI `knowledge-db search` 新增 `--ftype` 參數，支援單一或多副檔名（如 `--ftype=c\|cpp\|h\|hpp`、`--ftype=md`、`--ftype=py`）。<br>3. 檢索引擎在計分過濾階段執行副檔名匹配，與解析器私有 token 徹底解耦。 | P0 | [P00:DR-03] |
| **FR-04** | **同檔案動態聚合與積分合併 (Score Aggregation)** | 1. 搜尋結果依檔案路徑 (`file_path`) 進行動態匯聚為 `AggregatedFileResult`。<br>2. 積分合併公式嚴格採行 **Max + α·ΣRest (方案 B)**：<br>&nbsp;&nbsp;&nbsp;&nbsp;$\text{Score}(\text{File}) = \max(S_i) + \alpha \cdot \sum_{j \neq i} S_j$，預設 $\alpha = 0.2$。<br>3. 聚合節點內部子項目依原始 BM25 分數降序排列，保留內部 Top-3 關鍵 Items。 | P0 | [P00:DR-02]<br>[P00:DR-05] |
| **FR-05** | **Top-N 動態聚合回填管線 (Dynamic Refill Pipeline)** | 1. 搜尋候選池依 BM25 分數降序排列。<br>2. 動態推進游標：若當前 Item 命中已存在的檔案節點，合併至該節點並更新檔案總分；若為新檔案且目前頂層結果數 $< N$，則開立新檔案節點。<br>3. 持續掃描直到頂層聚合檔案節點數達到 $N$ 筆（或候選池耗盡），徹底消除同檔案多項目造成的 Top-N 截斷名額浪費。 | P0 | [P00:DR-02] |
| **FR-06** | **樹狀階層與 ASCII 聚合渲染 (Tree Output)** | 1. **預設 / Detail 模式**：獨立單 Item 檔案維持簡潔行；聚合檔案節點以 ASCII 樹狀分支渲染：<br>&nbsp;&nbsp;&nbsp;&nbsp;`file_path (Score: XX.XX, N items):`<br>&nbsp;&nbsp;&nbsp;&nbsp;`├── #01 [XX.XX] METHOD: methodName (lines L1-L2)`<br>&nbsp;&nbsp;&nbsp;&nbsp;`└── #02 [XX.XX] FUNCTION: funcName (lines L3-L4)`<br>2. **Top-3 上限**：聚合內部最多展示 Top 3 Items。<br>3. **`--snippet` 模式**：依序展示聚合節點內 Top-3 Items 之程式碼切片與行號指標。<br>4. **`--json` 模式**：輸出結構化 `aggregated_results`，完全相容結構化資料消費。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **候選池極度集中於單一檔案**<br>搜尋關鍵詞所有命中皆來自同一個大檔案（例如某個龐大模組），聚合後僅能產出 1 個檔案節點。 | 游標掃描完整個候選池後安全終止，輸出該 1 筆聚合節點（內含 Top-3 Items），不引發死循環或越界錯誤。 |
| **EC-02** | **`--ftype` 輸入格式容錯**<br>使用者輸入帶前綴點（`--ftype=.cpp`）、逗號分隔（`--ftype=cpp,h`）或管道分隔（`--ftype=c\|cpp\|h`）。 | 參數解析層進行正規化清洗：去除前置 `.`、支援 `\|` 與 `,` 分割、不分大小寫比對，確保過濾行為一致。 |
| **EC-03** | **C++ 跨行簽名異常中斷 (未閉合或超長)**<br>遇到語法不完整、巨集包裝、或缺少閉合括號 `)` 的 C++ 代碼。 | 狀態機設置**最大累積行數限制**（Max 30 行），超過上限自動放棄當前跨行累積並重置狀態，防止跨越多個函式產生毒性錯誤。 |
| **EC-04** | **AST 解析異常或動態語法錯誤**<br>遇到無效 Python 語法或不相容之 AST 結構。 | 捕獲 `SyntaxError` 與 `ValueError`，優雅降級為空符號或檔案級別基底符號，不中斷整體索引建立流程。 |
| **EC-05** | **跨 Space 相同檔案路徑聚合**<br>相同實體檔案被掛載於多個空間標籤（如 `project` 與 `local`）。 | 聚合時以正規化 `file_path` 作為唯一識別鍵，合併其 `spaces` 標籤聯集，維持單一檔案節點輸出。 |
| **EC-06** | **Top-N 回填動態重排穩定性**<br>在回填過程中，舊檔案節點因後續 Item 合併累加分數，可能導致檔案總分超過較早建立的檔案節點。 | 動態維護聚合字典，並在回填結束後對頂層 $N$ 個檔案節點按最終聚合總分進行二次排序，確保輸出順序嚴格符合總分降序。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **檢索延遲** | Top-N 動態聚合與回填管線在 10,000+ 篇符號倒排池中，額外計算耗時 $\le 5\text{ms}$，整體檢索時間維持在 $< 50\text{ms}$。 |
| **NFR-02** | **零外部依賴** | 核心演算法、狀態機與樹狀渲染 100% 採用純 Python 原生標準庫（Zero External Dependency）。 |
| **NFR-03** | **向後相容性** | 1. `UnifiedSymbol` 的 `to_dict()` / `from_dict()` 需向下相容舊版快取資料。<br>2. 現有 `SearchResult` 與 CLI 基本參數（`--space`, `--kind`, `--lang`, `--snippet`, `--json`）維持行為一致。 |
| **NFR-04** | **Dogfooding 閉環測試** | 必須通過 `python test/run_regression.py`（23/23 + E2E 100% Passed），並以本專案與下游專案之 C++/Python 程式碼實機驗證。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Dogfooding 三層空間隔離鐵律**：
  所有代碼修改必須 100% 於空間 ① `ys_codebase/source/knowledge-db/` 中進行，嚴禁直接修改空間 ③ 根目錄之 `modules/`。完成後需執行 4 步閉環流水線進行 Build ➔ Test ➔ Install ➔ Agents-Workflow 部署。
- **`[!IMPORTANT]` InvertedIndex 快照與 Gzip 二進位相容**：
  若 `UnifiedSymbol` 或 `SearchResult` 資料結構有擴充欄位，需確保 `from_dict` 具備預設值容錯，避免舊快取讀取時報 `KeyError`。
- **`[!NOTE]` Alpha 衰減係數標定**：
  `Score(File) = max(S_i) + α * sum(S_j)` 中 $\alpha = 0.2$ 為預設值，保證主命中佔據主導權重（$\ge 80\%$），其餘輔助命中提供合理加成，避免單純項目數量暴力洗榜。

