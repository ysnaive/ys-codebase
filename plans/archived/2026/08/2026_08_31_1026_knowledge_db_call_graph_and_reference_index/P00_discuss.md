# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_call_graph_and_reference_index  
> 建立日期：2026-08-31  
> 所屬主計畫：無 (獨立主計畫)  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：由技術路線圖 `plans/roadmap/knowledge_db_call_graph_and_reference_index.md` 轉化正式立項，為 `knowledge-db` 模組建構跨檔案符號調用圖譜 (Call Graph) 與引用依賴拓撲索引 (Reference Index)，並提供上游調用者、下游被調用者與重構影響面分析能力。
- **核心目標**：
  1. **補足拓撲感知斷層**：消除目前 `knowledge-db` 僅支援符號定義 (Definitions/Docstrings) 倒排索引的限制，提供「誰調用了我 (Callers)」、「我調用了誰 (Callees)」與「重構影響半徑 (Blast Radius Impact)」的拓撲查詢能力。
  2. **純 Python 原生零外部依賴 (Zero Dependency)**：基於 Python 原生 `ast` 走訪器與多語言狀態機提取調用點，完全不依賴外部肥大 LSP 或二進位背景服務，確保 100% 沙盒相容與極速解析。
  3. **四階消歧鏈接演算法 (4-Tier Disambiguation Cascade)**：
     - **Tier 1 (Self/Scope)**：檔內/類別內自省 (`self.xxx`、同檔內函式)
     - **Tier 2 (Import Alias)**：檔頭顯式 Import 映射表 (`from a.b import C`)
     - **Tier 3 (Same-Space)**：同語意空間符號優先匹配
     - **Tier 4 (Context Scoring)**：全庫倒排索引上下文打分匹配
  4. **整數池化雙向圖索引 (`CallGraphIndex`)**：透過整數 ID 映射池化 (Integer Pool) 與雙向稀疏鄰接表，控制全專案 5000+ 調用邊在 Gzip 二進位快取下體積 $< 150\text{ KB}$，載入時間 $< 5\text{ ms}$。
  5. **CLI 與 Agent 人體工學體驗**：擴充 `callers`、`callees`、`impact` CLI 子命令，全數輸出符合 RFC 8089 之 `[rel_path:Lline](file:///abs_path#Lline)` 可點擊直達 Markdown 連結。
- **邊界排除 (Explicitly Excluded)**：
  - 本階段排除執行期動態 Type Monkey-Patching 或複雜 Reflection 動態推斷。
  - 本階段不引入外部肥大 LSP Daemon（如 Node.js / pyright-langserver）。
  - 對於無法靜態確定的動態字串調用（如 `getattr(obj, var)`），標記為動態未鏈接邊，不造成解析中斷或崩潰。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 方案選型：雙層複合式靜態 AST 符號調用拓撲**
  - **決策**：捨棄外部 LSP (方案 1，依賴重且沙盒通訊不佳) 與純文字 Token 近似圖 (方案 2，精度低且雜訊多)，採用方案 3「原生 Python AST + Import 作用域棧 + 跨空間四階消歧鏈接」。
  - **理由**：兼顧 100% Python 標準庫純淨度、隔離沙盒相容性、90%~95% 靜態精度與極小快取體積。
- **[P00:DR-02] 資料結構：`SymbolCallSite` 與 `CallGraphIndex` 雙向索引**
  - **決策**：在 `schema.py` 擴充不可變 `SymbolCallSite` 記錄調用點位置與上下文前綴；在 `CallGraphIndex` 採用 `forward_graph` (caller $\rightarrow$ callees) 與 `reverse_graph` (callee $\rightarrow$ callers) 雙向鄰接表，並整合至 `unified.index.bin.gz` 持久化快取。
- **[P00:DR-03] 分流等級確立：Level 1 (Full Track)**
  - **決策**：本功能涉及 `knowledge-db` 核心架構擴充、Schema 變更、AST 解析器升級、新增拓撲鏈接器、新 CLI 指令及完整單元與回歸測試，全案依 Level 1 Full Track (Phase 0~7) 嚴格執行。

---

## 3. 開放議題與確認紀錄

- [x] 是否已繼承並清理 Roadmap 檔案？（已完成清查與移除 `knowledge_db_call_graph_and_reference_index.md` 與 `knowledge_db_performance_and_memory_optimization.md`）
- [x] 分流等級是否已確認？（Confirmed: Level 1 Full Track）
- [ ] Phase 01 規格轉譯待推進 (FR/EC/NFR)。
