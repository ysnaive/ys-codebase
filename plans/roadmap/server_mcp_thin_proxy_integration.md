# 技術路線圖：Server MCP 輕量轉發層與單例背景守護進程整合架構 (Roadmap)

> 主題：Server MCP 輕量轉發層與單例背景守護進程整合架構 (`server_mcp_thin_proxy_integration`)  
> 歸檔日期：2026-10-27  
> 狀態：Proposed  
> 目標範疇：`server`、`knowledge-db`、`agents-workflow`  
> 前置解鎖條件：確認目標宿主 IDE 環境需透過標準 MCP (`stdio`) 協議接入 YSCB 工具鏈時啟動  
> 模型：Unknown  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- **多視窗 MCP `stdio` 子進程模型易引爆記憶體（OOM）**：標準 MCP 客戶端（如 Claude Desktop、Cursor 等）預設以 `stdio` 子進程方式為每個開啟的 IDE 視窗或對話實例獨立拉起一個 MCP Server。若直接在 MCP `stdio` 進程內載入 `knowledge-db` 的本地 Embedding 模型與大型 AST 索引，多開視窗時將導致記憶體倍數暴增並失去常駐熱快取優勢。
- **細粒度 CLI 1:1 映射為 MCP Tools 會導致工具定義膨脹（Tool Bloat）**：若將 YSCB 所有模組數十個子指令全部註冊為獨立 MCP Tool，每次對話都會消耗數千個系統提示詞 Tokens，並降低 LLM 選取工具的準確率。

### 1.2 現況與影響範圍評估
- 目前 `server` 模組已具備完善的單例背景守護進程（`ServerMaster` + `WarmWorker` + `.cache/server/daemon.lock` + HTTP Loopback IPC），但尚未提供對接標準 MCP `stdio` 客戶端的輕量轉發入口。

### 1.3 核心根因
1. MCP 標準預設假設工具服務為無狀態或單實例 `stdio` 進程，與本地重型語義檢索引擎（需單例共享記憶體快取）存在架構衝突。
2. 缺乏針對 MCP 協議的 Meta-Tools 聚合門面與輸出 Payload 預算截斷守門。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：Monolithic `stdio` MCP Server** | 在每個 MCP `stdio` 進程內直接 import 並初始化 `knowledge-db` 與各模組 | 實作最簡單 | 多視窗下重複載入向量模型導致 RAM 暴表，且無法與 CLI 共享熱快取 | ⭐️ |
| **方案 2：MCP Thin Proxy + 單例 Daemon IPC 轉發** | `yscb.py server mcp-stdio` 僅作為 <15MB 的極薄 JSON-RPC 轉發器（Thin Proxy），透過本地 Loopback IPC 轉發給單例 `ServerMaster`/`WarmWorker`，並僅暴露 5~6 個聚合型 Meta-Tools | 多開視窗零額外模型記憶體開銷、共享毫秒級熱索引、嚴格控制 Tool Schema 與輸出 Token 預算 | 需實作 `stdio` JSON-RPC 與現有 Daemon HTTP `/api/exec` 之橋接與錯誤轉譯 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（Monolithic `stdio`） | 方案 2（MCP Thin Proxy + 單例 Daemon） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 低（違反記憶體防護邊界） | 高（現有 `ServerMaster` 已具備單例鎖與 `/api/exec` 路由） |
| **後續維護難度 (Maintenance)** | 高（兩套獨立執行路徑） | 低（底層 100% 復用既有 `WarmWorker` 分派管線） |
| **可靠性 (Reliability)** | 低（易 OOM 與檔案鎖衝突） | 極高（單一寫入與快取來源） |
| **落地難度 (Implementation)** | 低 | 中 |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 步驟 1：實作 Thin Proxy 轉發器 (`server/mcp_proxy.py`)
# 接收 IDE 的 stdio JSON-RPC 請求，透過 `.cache/server/daemon.json` 轉發至單例 ServerMaster

# 步驟 2：定義 5~6 個高內聚 Meta-Tools（禁止 1:1 細粒度暴露）
# 例如：yscb_code_intelligence (search/callers/callees/impact)、yscb_workflow_manager (status/verify/todo)、yscb_module_dev (check/test)

# 步驟 3：強制語義 URI 入參與 Payload Budgeting（單次調用輸出硬上限 4,000 tokens，超限自動降級為大綱 + 分頁指引）
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 作為 `Proposed` 技術儲備，確保未來擴充 MCP 時嚴守「Thin Proxy + 單例 Daemon + Meta-Tools + Payload Budgeting」四大架構不變量。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（Thin Proxy 與 JSON-RPC 橋接）**：於 `server` 模組實作零外部依賴的 MCP `stdio` Thin Proxy，對接單例 Daemon。
2. **Stage 2（Meta-Tools 契約與輸出節流閘門）**：封裝核心 Meta-Tools 並實作 4,000 tokens 輸出截斷與降級提示。
3. **Stage 3（跨平台與多視窗壓力測試）**：驗證多並發 `stdio` 代理連接同一 Daemon 時的記憶體穩定度與連線復原能力。

