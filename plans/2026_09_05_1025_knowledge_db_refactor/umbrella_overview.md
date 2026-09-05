# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：knowledge_db_refactor  
> 建立日期：2026-09-05  
> 狀態：In Progress  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：針對 `knowledge-db` 模組展開架構級重寫，將 AST 打造為未來 Agent 程式碼搜尋與架構理解的唯一核心基石。透過 YSCB 微環境引入成熟 Pip 相依性（Tree-sitter、FastEmbed、NetworkX），徹底捨棄手刻正則解析、手刻同義詞庫與手刻資料結構，打造支援通用語意、可擴充註冊、跨語言向量複合檢索與工業級圖譜拓撲的新一代代碼智慧中樞。
- **架構邊界**：
  - **通用與可擴充**：以 Tree-sitter S-Expression Query 為宣告式基礎，結合 YSCB `contributes.knowledge_db` 協議，讓新程式語言、自研 DSL 與自訂符號類型可外掛註冊。
  - **複合式檢索 (Hybrid Search)**：多語言 Tokenizer + 輕量 ONNX 多語言向量 + RRF 融合排序，打破中英跨語言檢索壁壘，並內建「未就緒 100% 降級為純 BM25」安全守門。
  - **對外契約相容**：維持既有 CLI 門面契約（`search`、`callers`、`callees`、`impact`、`status`、`clean`）與輸出格式（`--json` / `-s`），現有 Agent 技能零感升級。
  - **品質守門**：以現有 130 個單元測試用例為黃金驗收網 (Golden Test Suite)，重構後必須 100% 通過。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_universal_ast_and_contributed_tree_sitter` | Full Track | `Completed` | **Universal AST 與可擴充解析引擎**：定義遞迴階層符號模型 (FQN/結構化簽名)；制定 `contributes` 擴充協議；引入 `tree-sitter` 宣告式 S-Expression 解析器；徹底汰換 `parsers/` 手刻正則。 |
| **sub_02** | `sub_02_multilingual_tokenizer_and_hybrid_search` | Full Track | `Completed` | **多語言分詞與 BM25+向量複合檢索**：實作中英混雜分詞器；引入輕量 ONNX 多語言 Embedding (`fastembed`)；實作 RRF 融合演算法與平滑降級；徹底移除手刻同義詞庫 (`thesaurus.py`)。 |
| **sub_03** | `sub_03_networkx_call_graph_and_impact_analysis` | Full Track | `Pending` | **基於 NetworkX 的符號拓撲分析**：引入 `networkx`；利用 FQN 與 Import 作用域重構 `linker.py`（消除幽靈關聯）；重構 `graph.py` 提升 callers/callees 與多階 impact分析精度。 |
| **sub_04** | `sub_04_pipeline_engine_refactor_and_dogfooding` | Full Track | `Pending` | **流水線解耦與生態系驗收**：拆解 1,800 行 Monolithic `engine.py` 為 Pipeline 架構；核驗對外 CLI 契約；130+ 單元測試 100% 回歸；完成 Dogfooding 閉環與發布。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (AST 革命)**：完成 Universal AST Schema、Tree-sitter 引擎與 Contributes 語言外掛機制 (sub_01)
- [x] **里程碑 2 (檢索躍升)**：完成多語言 Tokenizer 與 BM25 + 向量 RRF 複合式檢索，打破跨語言檢索壁壘 (sub_02)
- [ ] **里程碑 3 (圖譜強化)**：完成基於 NetworkX 與 FQN 的精確調用拓撲與影響面分析 (sub_03)
- [ ] **里程碑 4 (架構收斂)**：完成 Pipeline 引擎解耦、全系統單元測試回歸、Dogfooding 驗證與正式打包發布 (sub_04)
