# 技術路線圖：knowledge-db 跨檔案符號調用圖譜與引用依賴拓撲索引 (Roadmap)

> 主題：knowledge_db_call_graph_and_reference_index  
> 歸檔日期：2026-08-30  
> 狀態：Proposed  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- 目前 `knowledge-db` 僅支援符號定義層級 (Definitions & Docstrings) 的倒排索引檢索。
- 當 Agent 進行跨檔案重構、影響面分析 (Blast Radius Analysis) 或執行鏈除錯時，無法精準得知某個函式/方法「被誰調用 (Callers)」或「內部調用了誰 (Callees)」。
- Agent 只能退化使用 `grep_search` 進行模糊文字搜尋，面對常見方法名（如 `.parse()`, `resolve()`, `get_storage_root()`）或短名導入 (`from x import y`) 時會產生大量雜訊或漏搜，造成「Grep ➔ ViewFile」鏈式翻讀與 Token 浪費。

### 1.2 全庫歷史物件量化分析
- 本專案四大模組累積 230+ 單元測試與 40+ 核心原始碼檔案，包含 Python、C/C++、C# 與 SPICE 多語言體系。
- 多型方法（如各解析器的 `parse()`）與實例變數調用（`self._get_storage_root()`）佔全庫調用點約 60% 以上，文字搜尋在這些情境下難以單次確定指向。

### 1.3 核心根因
1. 缺少 AST 調用點萃取器 (CallSite Visitor) 與作用域分析 (Scope Stack)。
2. `UnifiedSymbol` Schema 未定義 `calls`、`callers` 與 `dependencies` 邊緣關聯結構。
3. 缺少跨檔案拓撲鏈接器 (TopologyLinker) 與雙向圖索引 (CallGraphIndex)。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：外部 LSP 協議橋接 (Pyright / clangd)** | 依賴 Node.js / C++ 背景 Daemon 通訊獲取精確型別與參考清單 | 99% 精確型別推斷 | 外部依賴重、記憶體開銷大、沙盒環境不易運行、多語言維護成本高 | ⭐️⭐️ |
| **方案 2：純文字 Token 近似圖** | 掃描識別碼相鄰矩陣建立圖結構 | 實作簡單、零依賴 | 嚴重受字串、註解與同名局部變數干擾，精度低 | ⭐️⭐️⭐️ |
| **方案 3：雙層複合式靜態 AST 符號調用拓撲 (推薦)** | 原生 Python AST + 各語系狀態機萃取 CallSites，結合 Import 表與倒排索引進行跨空間消歧鏈接 | 零外部依賴、純 Python 秒級解析、快取體積極小 (<300KB)、原生支援 YSCB 語意空間 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1 (LSP) | 方案 2 (Token-Level) | 方案 3 (AST Topology - 推薦) |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 🟡 中 (跨平台相容性挑戰) | 🟢 高 | 🟢 高 (現有 BaseParser 擴充) |
| **後續維護難度 (Maintenance)** | 🔴 高 (多語言 Daemon 配置) | 🟢 低 | 🟢 低 (模組自包含) |
| **可靠性 (Reliability)** | 🟢 高 | 🔴 低 | 🟢 高 (90%~95% 靜態解析精度) |
| **落地難度 (Implementation)** | 🔴 高 | 🟢 低 | 🟡 中 (需實作 CallSiteVisitor 與 Linker) |

---

## 4. 標準作業流程與 CLI 介面 (Standard Operating Procedure)

```bash
# 1. 查詢誰調用了某符號 (Upstream Callers)
python yscb.py knowledge-db callers "build_index" -s

# 2. 查詢某函式/方法內部調用了哪些符號 (Downstream Callees)
python yscb.py knowledge-db callees "AtomicEngine.act_register" -s

# 3. 重構前影響面分析 (Blast Radius Impact)
python yscb.py knowledge-db impact "SpaceManager._get_storage_root"
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 保持 `knowledge-db` 現有倒排索引與 RFC 8089 連結穩定性。
- 將本主題納入 Roadmap 策略資產，待需要大規模重構或跨模組深層除錯時一鍵立項開發。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (Schema & Intra-File AST Parsing)**：
   - 於 `schema.py` 新增 `SymbolCallSite` 模型，擴充 `UnifiedSymbol.calls` 與 `UnifiedSymbol.dependencies`。
   - 於 `PythonParser` 實作 `CallVisitor` 與 `ImportVisitor`，支援函式調用點與模組引入別名萃取。
2. **Stage 2 (Cross-File Topology Linking & Disambiguation)**：
   - 實作 `TopologyLinker`，結合 Import 映射表、類別階層與全域倒排索引進行跨空間符號消歧與雙向圖綁定。
3. **Stage 3 (CallGraphIndex & Fast Binary Cache)**：
   - 實作 `CallGraphIndex` 雙向圖結構（`forward_graph` / `reverse_graph`），整合至 `unified.index.bin.gz` Gzip 二進位快取。
4. **Stage 4 (CLI & Agent Ergonomics)**：
   - 於 `knowledge_db/cli.py` 實作 `callers`、`callees`、`impact` 指令，輸出 RFC 8089 可點擊 Markdown 連結。
   - 於 `contributes/agents-workflow.json` 更新 Agent 檢索指引。
