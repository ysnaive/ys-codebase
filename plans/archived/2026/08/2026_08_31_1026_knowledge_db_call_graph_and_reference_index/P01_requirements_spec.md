# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge_db_call_graph_and_reference_index  
> 建立日期：2026-08-31  
> 所屬主計畫：無 (獨立主計畫)  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 依據 R01：[R01_knowledge_db_architecture_and_tokenizer.md](./R01_knowledge_db_architecture_and_tokenizer.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **符號調用點模型與抽象介面** | 於 `schema.py` 新增不可變 Value Object `SymbolCallSite`（記錄 `callee_name`, `line_number`, `caller_member_name`, `context_prefix` 等）；於 `BaseParser` 擴充通用抽象介面 `extract_call_sites(file_path, content, space)`。 | P0 | [P00:DR-02] |
| **FR-02** | **Python AST 調用點與作用域萃取器** | 於 `PythonParser` 實作 `CallSiteVisitor`，走訪 `ast.Call`、`ast.Attribute`、`ast.Import` 與 `ast.ImportFrom`；維護 `ScopeStack` 精準提取呼叫點所屬類別/函式作用域，並產出檔頭 `imports` 映射表與 `List[SymbolCallSite]`。 | P0 | [P00:DR-01] |
| **FR-03** | **四階跨空間拓撲消歧鏈接器 (TopologyLinker)** | 實作 `TopologyLinker`，聚合全域符號池與調用點，執行四階消歧鏈接演算法：<br/>• **Tier 1 (Self/Scope)**：檔內/類別內自省 (`self.xxx`)<br/>• **Tier 2 (Import Alias)**：檔頭顯式 Import 映射表 (`from a.b import C`)<br/>• **Tier 3 (Same-Space)**：同語意空間優先匹配 (`project://` vs `yscb://`)<br/>• **Tier 4 (Context Scoring)**：全庫倒排上下文打分匹配。 | P0 | [P00:DR-01] |
| **FR-04** | **雙向圖譜索引結構 (CallGraphIndex)** | 實作 `CallGraphIndex`，支援 `forward_graph` (caller $\rightarrow$ callees) 與 `reverse_graph` (callee $\rightarrow$ callers) 雙向稀疏鄰接表，使用整數 ID 池化 (Integer String Pool) 最小化記憶體佔用與序列化開銷。 | P0 | [P00:DR-02] |
| **FR-05** | **Gzip 二進位快取持久化與 JIT 增量修補** | 將 `CallGraphIndex` 整合進 `unified.index.bin.gz` (Protocol 5 + compresslevel=1)；在 `patch_incremental()` 中支援 dirty 檔案調用邊的差量拔除與重構，保證熱自愈延遲 $< 50\text{ ms}$。 | P0 | [P00:DR-02] |
| **FR-06** | **統一門面 SDK 與 CLI 人體工學指令** | 於 `KnowledgeEngine` 與 `cli.py` 新增子命令：<br/>• `callers <symbol>`：查詢上游調用者<br/>• `callees <symbol>`：查詢下游被調用者<br/>• `impact <symbol> [--depth=N]`：分析重構影響面擴散拓撲<br/>全數輸出符合 RFC 8089 之 `[rel_path:Lline](file:///abs_path#Lline)` 可點擊 Markdown 連結。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **動態多型與無法靜態消歧調用** | 遭遇動態字串調用（如 `getattr(obj, name)`）或無 import 的同名多型方法時，標記為動態未鏈接邊或依上下文打分排序，系統永不中斷或崩潰。 |
| **EC-02** | **循環調用與遞迴依賴圖 (Recursive Cycles)** | 函式 A 調用 B 且 B 調用 A 時，`impact` 多階搜尋走訪演算法強制綁定 `visited_set`，杜絕無窮遞迴與死循環。 |
| **EC-03** | **檔案刪除與符號孤立殘留 (Ghost Edges)** | 當檔案被刪除或重構時，JIT 熱重載 `patch_incremental` 100% 同步清理 `CallGraphIndex` 中舊檔案作為 Caller 與 Callee 的雙向鄰接邊，杜絕幽靈邊殘留。 |
| **EC-04** | **深層屬性鏈與複雜表達式 (Chained Calls)** | 遭遇 `a.b.c.method()` 或鏈式調用 `foo().bar().baz()` 時，安全防禦提取最末端屬性名與前綴字串，若 `ast.unparse` 失敗安全回退為空前綴。 |
| **EC-05** | **跨語意空間同名符號隔離** | 當 `project://` 與 `yscb://` 存在同名符號時，依據呼叫源檔案所屬空間執行 Tier 3 空間隔離優先綁定，防止跨專案邊界污染。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **純淨度 / 依賴** | 100% 採用純 Python 標準庫（`ast`, `gzip`, `pickle`, `hashlib`），嚴禁依賴外部肥大 LSP 或 Node.js 二進位背景進程，保證沙盒環境 100% 原生安全相容。 |
| **NFR-02** | **快取體積與載入延遲** | 全專案 5,000+ 調用邊在 Gzip 二進位快取下檔案體積 $< 150\text{ KB}$，反序列化載入耗時 $< 10\text{ ms}$。 |
| **NFR-03** | **查詢與影響面分析延遲** | 單次 `callers` / `callees` 查詢延遲 $< 5\text{ ms}$；`impact --depth=3` 深度影響面分析遍歷延遲 $< 20\text{ ms}$。 |
| **NFR-04** | **跨平台路徑規範** | 所有路徑強制正規化為 forward slashes (`/`)，輸出連結 100% 符合 RFC 8089 `file:///` 協議與 IDE 點擊規範。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!CAUTION]
  > **符號池解耦防呆 (DN-01)**：`CallGraphIndex` 鄰接表內部嚴禁直接持有 `UnifiedSymbol` 或 `SymbolCallSite` 完整物件副本，必須強制透過 `Integer String Pool` 或 `symbol_id` 引用，避免 Protocol 5 二進位快取序列化體積爆炸。
- > [!WARNING]
  > **空間隔離防呆 (DN-02)**：所有圖譜快取產物必須嚴格留存於 `cache://knowledge-db/`，嚴禁污染宿主專案工作目錄。
- > [!NOTE]
  > **增量熱自愈一致性**：`CallGraphIndex.patch_incremental` 必須與 `InvertedIndex.patch_incremental` 保持嚴格一致的生命週期同步，確保單檔變更時調用圖譜與倒排索引同步刷新。
