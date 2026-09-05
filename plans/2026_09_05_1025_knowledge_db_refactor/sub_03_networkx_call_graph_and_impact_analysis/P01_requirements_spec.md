# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_03_networkx_call_graph_and_impact_analysis  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | NetworkX DiGraph 圖拓撲儲存與雙向索引 | 替換手刻整數池與雙向 set 字典，以 `networkx.DiGraph` 作為核心拓撲資料結構；節點保存 `symbol_id` 與 Universal AST 元數據（FQN, kind, file_path, space），有向邊保存調用點資訊 (`SymbolCallSite`)。 | P0 | [P00:DR-01] |
| **FR-02** | 多語言調用拓撲協議 (Topology Protocol) | 定義 `LanguageTopologyProtocol` 抽象介面，支援宣告式與外掛擴充各語言之調用點與檔頭匯入提取；使 Python、JS/TS、C/C++、C# 等語言皆能透過統一協議外掛物化。 | P0 | [P00:DR-06] |
| **FR-03** | 基於 FQN 與 Import 作用域消歧鏈接 | 重構 `TopologyLinker` 四階消歧階層，依據 Universal AST 的階層 FQN、父子節點作用域與檔頭 Import 映射精確消歧；收緊 Tier 4 全域候選匹配門檻，無法確信歸屬者標記為未鏈接，徹底消除跨檔案幽靈關聯。 | P0 | [P00:DR-03] |
| **FR-04** | 全方位 AST 符號結構化選擇器 (Comprehensive Selector) | 實作完備的 `SymbolSelector` 語法解析器，支援類型前綴（`class`, `struct`, `interface`, `enum`, `fn`/`func`/`def`, `type`, `const`, `var`, `macro`）、階層範疇（`foo.a`、`pkg.foo.a`）與可調用標記（`()`）之任意正交組合（如 `class Foo.bar()`, `struct Point.x`）；CLI 指令（`callers`, `callees`, `impact`, `search`）全面支援該選擇器進行目標符號消歧與高維度定位。 | P0 | [P00:DR-07] |
| **FR-05** | 高精度多階影響面分析與調用鏈追溯 | `query_impact` 改由 NetworkX 有向圖的前驅走訪與路徑演算法實作，精準計算多階影響層級（Layer 1..N）並還原調用鏈路（Call Chains），天然免疫遞迴循環調用。 | P0 | [P00:DR-05] |
| **FR-06** | 對外 API 門面與 CLI 契約向後相容 | 嚴格維持 `CallGraphIndex` 與 `TopologyLinker` 現有 Public API 門面方法簽名與資料格式，維持 CLI 輸出人體工學（`--json`, `-s`），確保現有測試與上游調用端零破壞相容。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 圖中存在循環調用 (A ➔ B ➔ A) | 走訪演算法維護 visited 集合，走訪檢測到重複節點時自動剪枝，杜絕無限循環與重複計算。 |
| **EC-02** | 符號選擇器語法格式無效或未命中任何符號 | 解析器提供寬容容錯，語法解析異常時回退為純文字精確比對；未命中時回傳清晰錯誤提示或空清單，不造成崩潰。 |
| **EC-03** | 動態語言裸調用無法確定唯一被調用者 | 嚴格標記為未鏈接邊，不強行鏈接至全域無關同名函式，杜絕幽靈關聯。 |
| **EC-04** | 孤立節點（無調用者或無被調用者）查詢 | 查詢 `get_callers` 或 `get_callees` 回傳空列表，`query_impact` 回傳總影響符號數為 0，結構化格式維持完整。 |
| **EC-05** | 二進位快取損毀或缺少 NetworkX 依賴 | 提供載入例外防禦，快取反序列化失敗時記錄警告並退回自 AST 即時重建；依賴缺失時拋出引導安裝之友善提示。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 查詢效能 | 萬級符號規模圖譜下，`callers` 與 `callees` 單步查詢耗時 $\le 1\text{ms}$，2 階 `query_impact` 走訪分析耗時 $\le 15\text{ms}$。 |
| **NFR-02** | 純 Python 輕量穩定 | `networkx` 依賴為純 Python 實現，零二進位 C 擴展，相容 Windows、Linux 與 macOS，冷啟動開銷 sub-5ms。 |
| **NFR-03** | 既有測試相容性 | 既有單元測試（包含 `test_call_graph.py` 與 CLI 回歸測試）100% 通過，API 契約完全零破壞。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `DN-07` 與 `DN-10`：調用邊使用 NetworkX 有向圖時，節點使用字串 ID，邊屬性儲存 `call_sites`；在缺少型別標註的動態調用中，嚴禁將無 import 的裸調用盲連至全域符號，杜絕幽靈關聯。

---

## 5. 關鍵決策紀錄 (Key Decisions)

- **[P01:DR-01] 全方位符號選擇器 EBNF 與正規化映射規範**：
  - **EBNF 語法規則**：
    $$\texttt{Selector} \Coloneqq [\texttt{KindPrefix}\;\textvisiblespace]\;[\texttt{Scope}\;\texttt{"."}]\,\texttt{Identifier}\;[\texttt{"()"\,]}$$
  - **KindPrefix 映射表**：
    - `class` ➔ `SymbolKind.CLASS`
    - `struct` ➔ `SymbolKind.STRUCT`
    - `interface` ➔ `SymbolKind.INTERFACE`
    - `enum` ➔ `SymbolKind.ENUM`
    - `fn` / `func` / `def` / `function` / `method` ➔ `{SymbolKind.FUNCTION, SymbolKind.METHOD}`
    - `type` / `typedef` ➔ `SymbolKind.TYPE_ALIAS`
    - `const` ➔ `SymbolKind.CONSTANT`
    - `var` / `let` ➔ `SymbolKind.VARIABLE`
    - `macro` ➔ `SymbolKind.MACRO`
  - **Callable 約束 (`()`)**：尾端帶 `()` 時強制約束為可調用節點（`FUNCTION` 或 `METHOD`）。
  - **Scope 階層解析**：點分隔前綴對應符號之 `parent_id`、所屬類別名稱或 FQN 前置路徑。
- **[P01:DR-02] 語言拓撲協議生命週期整合**：
  - `LanguageTopologyProtocol` 伴隨 AST 解析管線運行，利用 Tree-sitter S-Expression 或專屬語法走訪器，輸出標準化之 `List[SymbolCallSite]` 與 `Dict[str, str]` 匯入映射表。
- **[P01:DR-03] NetworkX 圖持久化策略**：
  - 採用 Gzip 壓縮的 Pickle Protocol 5 序列化，圖中節點與邊屬性保持精簡輕量，確保磁碟佔用與載入時間維持在毫秒級。
