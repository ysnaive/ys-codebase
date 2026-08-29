# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge_db_parser_and_search_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_1049_knowledge_db_algorithm_optimization  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | **Python 解析器方法物化與精確 end_line**：驗證類別方法與函式正確產出為獨立 `UnifiedSymbol`，`line_number` 與 `end_line` 精確匹配 AST 邊界。 | FR-01 | `unittest: test_parsers_deep.py` |
| **FT-02** | 單元測試 | **C++ 多行簽名累積狀態機**：驗證跨行函式宣告、參數清單跨多行均能正確被匹配提取，不遺失符號。 | FR-02, EC-03 | `unittest: test_parsers_deep.py` |
| **FT-03** | 單元測試 | **C++ Namespace 堆疊與 Class 成員作用域**：驗證巢狀 namespace 產出完整 Qualified Name，Class 成員方法標記為 `kind=method`。 | FR-02 | `unittest: test_parsers_deep.py` |
| **FT-04** | 單元測試 | **Markdown 與 C# 解析器 end_line 邊界**：驗證 Markdown 各標題與表格、C# 方法與屬性具備合法之 `end_line`。 | FR-01 | `unittest: test_parsers_deep.py` |
| **FT-05** | 單元測試 | **`--ftype` 檔案類型來源過濾**：驗證多種副檔名格式（`c\|cpp\|h`, `md`, `.py`）之篩選精確度與大小寫容錯。 | FR-03, EC-02 | `unittest: test_search_aggregation.py` |
| **FT-06** | 單元測試 | **同檔案積分合併演算法**：驗證 `Score(File) = max(Si) + 0.2 * sum(Sj)` 計算數值正確，內部子項目依原始分排序。 | FR-04 | `unittest: test_search_aggregation.py` |
| **FT-07** | 單元測試 | **Top-N 動態聚合回填管線**：驗證同檔案多命中折疊後自動向後回填，補滿 $N$ 個頂層檔案節點或池空為止。 | FR-05, EC-01, EC-06 | `unittest: test_search_aggregation.py` |
| **FT-08** | 整合測試 | **樹狀 ASCII 排版與 JSON 輸出**：驗證 Default、Detail、Snippet 與 JSON 模式下樹狀分支格式與 Top-3 Cap。 | FR-06 | `unittest: test_search_aggregation.py` |
| **RT-01** | 回歸測試 | **Dogfooding 空間閉環與全量回歸**：驗證 `knowledge-db` 全部既有單元測試（`test_bundler`, `test_engine`, `test_retrieval`, `test_scanner` 等）100% 通過。 | NFR-03, NFR-04 | `python test/run_regression.py` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_parsers_deep.py`: Python 方法與函式獨立提取為 UnifiedSymbol，帶出 end_line 與 AST 邊界。 | 2026-08-29 14:40 |
| **FT-02** | `Passed` | `test_parsers_deep.py`: C++ 多行宣告狀態機成功解析跨行參數清單並提取完整簽名。 | 2026-08-29 14:40 |
| **FT-03** | `Passed` | `test_parsers_deep.py`: C++ Namespace 堆疊與 Class 成員 Qualified Name (Engine::Rendering::Renderer) 識別無誤。 | 2026-08-29 14:40 |
| **FT-04** | `Passed` | `test_parsers_deep.py`: C# 與 Markdown 標題、表格之 end_line 座標均正確大於等於 line_number。 | 2026-08-29 14:40 |
| **FT-05** | `Passed` | `test_search_aggregation.py`: `--ftype` 檔案類型過濾器支援 py, c\|cpp\|h, .md 格式與大小寫容錯。 | 2026-08-29 14:40 |
| **FT-06** | `Passed` | `test_search_aggregation.py`: Score(File) = max(Si) + 0.2*sum(Sj) 演算法與 Top-3 Cap 驗證通過。 | 2026-08-29 14:40 |
| **FT-07** | `Passed` | `test_search_aggregation.py`: Dynamic Top-N 回填管線成功填滿 2 個獨立檔案節點。 | 2026-08-29 14:40 |
| **FT-08** | `Passed` | `test_search_aggregation.py`: 結構化 AggregatedFileResult 序列化與屬性向後相容無誤。 | 2026-08-29 14:40 |
| **RT-01** | `Passed` | `python yscb.py dev test --all`: 207/207 Total Passed (0 Failed, 0 Skipped, 8.568s)，全模組回歸通過。 | 2026-08-29 14:41 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在終端實機執行 `python yscb.py knowledge-db search "parse" --ftype=py -s`，檢查同檔案多個方法是否以樹狀 ASCII 分支呈遞，且包含代碼切片與行號。
- [x] **UX-02**：實機執行 `python yscb.py knowledge-db search "Renderer" --ftype=cpp|h`，驗證 C++ 跨行簽名與 Qualified Name 是否清晰可見。
- [x] **UX-03**：實機執行 `python yscb.py knowledge-db search "test" --limit=3`，確認回填機制在同檔案多命中時依然給足 3 個不同的檔案節點。

