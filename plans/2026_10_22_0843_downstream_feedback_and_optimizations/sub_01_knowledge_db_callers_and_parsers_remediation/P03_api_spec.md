# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_knowledge_db_callers_and_parsers_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `KnowledgeEngine.act_callers` | `knowledge_db/engine.py` | Public | 查詢目標符號之上游調用者清單，支援 `space`、`snippet` 與新增之 `ftypes` 過濾 |
| `KnowledgeEngine.act_callees` | `knowledge_db/engine.py` | Public | 查詢目標符號之下游被調用者清單，支援 `space`、`snippet` 與新增之 `ftypes` 過濾 |
| `KnowledgeEngine.act_impact` | `knowledge_db/engine.py` | Public | 分析目標符號之多階重構影響面，支援 `depth`、`space` 與新增之 `ftypes` 過濾 |
| `IndexingPipeline.act_callers` | `knowledge_db/pipeline.py` | Public | 執行上游調用者檢索、介面/實作契約聚合、文檔預設排除與 `ftypes` 過濾 |
| `IndexingPipeline.act_callees` | `knowledge_db/pipeline.py` | Public | 執行下游被調用者檢索、文檔預設排除與 `ftypes` 過濾 |
| `IndexingPipeline.act_impact` | `knowledge_db/pipeline.py` | Public | 執行多階重構影響面 BFS 走訪、介面/實作契約聚合、文檔預設排除與 `ftypes` 過濾 |
| `TopologyLinker.resolve_call_site` | `knowledge_db/linker.py` | Public | 四階消歧演算法（含無前綴隱含 `this` 類別/基類查找與完整命名空間限定前綴匹配） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class IndexingPipeline:
    def find_target_symbol(
        self,
        query: str,
        space: Optional[str] = None,
        allow_docs: bool = False,
    ) -> Optional[UnifiedSymbol]:
        """
        精準定位目標 UnifiedSymbol。
        - Pre-conditions: query 為非空字串。
        - Post-conditions: 當 allow_docs=False 時，優先在非 markdown/doc_* 程式碼符號池中定位；
          若無匹配且 allow_docs=True 則回退包含文檔符號。
        """

    def act_callers(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        查詢指定符號之上游調用者清單 (Who calls me?)。
        - Pre-conditions: target_query 為目標符號選擇器或名稱。
        - Post-conditions:
          1. 自動聚合契約鏈（介面/實作類別）上對應同名方法之上游調用者。
          2. 預設排除 language == "markdown" 或 doc_* 節點，除非 ftypes 顯式包含 "md"/"markdown"。
          3. 回傳 callers 清單每項皆同時包含 "symbol" 與 "caller_symbol" 鍵以確保 CLI/SDK 100% 相容。
        """

    def act_callees(
        self,
        target_query: str,
        space: Optional[str] = None,
        snippet: bool = True,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        查詢指定符號內部調用之下游被調用者清單 (Whom do I call?)。
        - Post-conditions: 預設排除文檔符號，並依 ftypes 過濾結果。
        """

    def act_impact(
        self,
        target_query: str,
        depth: int = 2,
        space: Optional[str] = None,
        ftypes: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        分析目標符號之重構影響面擴散拓撲 (Blast Radius Analysis)。
        - Post-conditions:
          1. 支援從目標符號及其介面/實作對應方法共同作為 BFS 起點向上走訪。
          2. 預設排除文檔符號，並依 ftypes 過濾各層受影響符號與統計數。
        """
```

### 階段決策記錄
- **[P03:DR-01] `ftypes` 參數選填與預設值向後相容**：`act_callers`、`act_callees`、`act_impact` 新增之 `ftypes` 參數均設為 `Optional[Union[str, List[str]]] = None` 選填預設值，確保既有 SDK 呼叫端 0 修改無縫相容。
- **[P03:DR-02] `callers` 字典雙鍵相容契約**：`act_callers` 回傳之 `callers_detail` 元素同時提供 `"symbol": caller_sym` 與 `"caller_symbol": caller_sym`，使 `formatter.py`（讀 `"symbol"`）與 `scripts/cli.py --json`（讀 `"caller_symbol"` / `"symbol"`）雙向永不觸發 `KeyError`。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: assets/queries/{c_sharp,cpp,c,typescript,javascript,python}.scm (底層語法查詢擴充)
  │
  ▼
Step 2: knowledge_db/parsers/treesitter.py (base_types 提取、C++ 類別外方法作用域、鏈式/泛型/條件存取 prefix 提取)
  │
  ▼
Step 3: knowledge_db/linker.py (多段式名稱雙段索引、Tier 1 隱含 this 與基類查找、完整命名空間前綴消歧、遞迴自呼叫保留)
  │
  ▼
Step 4: knowledge_db/pipeline.py & knowledge_db/engine.py (介面/實作契約展開、預設排除文檔、ftypes 過濾、雙鍵相容)
  │
  ▼
Step 5: contributes/core.json & scripts/cli.py (CLI --ftype 契約宣告與 callers --json 修復)
  │
  ▼
Step 6: tests/{test_graph.py,test_cli.py} & docs/knowledge-db/ (單元測試與三層文檔同步)
```

