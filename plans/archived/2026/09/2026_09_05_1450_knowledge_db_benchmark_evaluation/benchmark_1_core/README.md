# Knowledge-DB 基準評測套件 (Knowledge-DB Benchmark Suite)

本目錄包含針對 YS-Codebase 新版 `knowledge-db`（v1.0.2.0，整合 Universal AST、FastEmbed BGE-small-zh 向量索引、NetworkX 調用圖譜與 SymbolSelector）的客觀效能與精準度評測環境。

---

## 📁 目錄結構

```text
benchmark/
├── README.md                  # 本指引文件 (評測架構、指標與操作流程)
├── QUESTIONS.md               # 評測題目集 (Level 1~3 共 9 題，含標準 Ground Truth 與計量規範)
├── PROMPT_KNOWLEDGE_DB.md     # 實驗組 (Agent A) 提示詞：啟用 knowledge-db 專用工具鏈
├── PROMPT_TRADITIONAL.md      # 對照組 (Agent B) 提示詞：嚴格僅限傳統工具 (grep / view_file)
├── results_knowledge_db.md    # [待生成] 實驗組執行結果與指標統計
└── results_traditional.md     # [待生成] 對照組執行結果與指標統計
```

---

## 🎯 評測設計維度 (Question Hierarchy)

題目依據真實開發場景難度與語意抽象層次分為三個 Level，各包含 3 道關鍵題目（詳見 [`QUESTIONS.md`](./QUESTIONS.md)）：

1. **Level 1：帶有明確符號需求之問題 (Explicit Symbol Queries)**
   - **Q1.1**：符號精確定位、型態簽名與規格正規化邏輯 (`PipManager.parse_pip_dependencies`)
   - **Q1.2**：調用圖譜上游調用者排查 (`adapt_build_pip_dependencies` 的 callers)
   - **Q1.3**：多階重構影響半徑評估 (類別 `PipManager` 深度=2 的拓撲擴散分析)
2. **Level 2：帶有大致關鍵模組訊息之問題 (Module Context Queries)**
   - **Q2.1**：Dev 沙盒微環境零拷貝投影與 3-Tier 降級兜底機制 (`SandboxProvisioner._project_venv`)
   - **Q2.2**：Knowledge-DB 通用 AST 解析與零特權自貢獻架構 (`TreeSitterDriver` 與 `contributes/knowledge-db.json`)
   - **Q2.3**：Dev 測試套件 4-Tier 需求分流與跑測過濾機制 (`Requirement` 列舉與 `--workflow`/`--all-types`)
3. **Level 3：直白敘述式問題 (Natural Language Queries)**
   - **Q3.1**：跑測試時非致命警告收集折疊與崩潰 tail 20 行錯誤保留機制
   - **Q3.2**：第三方套件隔離微環境與沙盒自動安裝適配機制
   - **Q3.3**：知識庫 BM25 與向量特徵複合融合 (RRF) 與離線剛性降級機制

---

## 📊 核心觀測與評量指標 (Metrics)

本評測聚焦於大語言模型在工程實務中**「檢索效率」**與**「Token 經濟效益」**的對比：

| 指標名稱 | 說明 | 單位 / 計量方式 |
| :--- | :--- | :--- |
| **讀取與檢索 Token (Read/Search Tokens)** | 檢索結果、代碼切片或全檔讀取所消耗的內容容量 | 字元數 $\div 4$ 或 Transcript Token 統計 |
| **工具呼叫次數 (Tool Calls)** | 定位並解答該題所需呼叫的外部工具總次數 | 次數 (Calls) |
| **思考步驟數 (Thinking Steps)** | 模型推論、組織策略與綜合判斷的推理步驟數 | 步驟數 (Steps) |
| **執行耗時 (Wall-Clock Time)** | 該題從發起檢索到產出解答所消耗的實際時間 | 秒 (Seconds) |
| **解答準確度與完整率 (Accuracy)** | 比對 [`QUESTIONS.md`](./QUESTIONS.md) 之 Ground Truth 評分 | 0% ~ 100% |

---

## 🚀 評測執行流程 (Step-by-Step Guide)

### 步驟 1：開立實驗組 Agent A (Knowledge-DB 啟用)
1. 在 IDE 中開啟一個全新的獨立 Agent 對話 Session。
2. 複製 [`benchmark/PROMPT_KNOWLEDGE_DB.md`](./PROMPT_KNOWLEDGE_DB.md) 內容發送給 Agent A。
3. 等待 Agent A 自主調用 `knowledge-db` 完成 Q1.1 至 Q3.3，並自動寫入 `benchmark/results_knowledge_db.md`。

### 步驟 2：開立對照組 Agent B (傳統工具組)
1. 在 IDE 中開啟另一個全新的獨立 Agent 對話 Session。
2. 複製 [`benchmark/PROMPT_TRADITIONAL.md`](./PROMPT_TRADITIONAL.md) 內容發送給 Agent B。
3. 等待 Agent B 僅使用 `grep_search`、`view_file` 等傳統工具完成 Q1.1 至 Q3.3，並自動寫入 `benchmark/results_traditional.md`。

### 步驟 3：返回本 Session 進行雙軌歷史對比評估
1. 兩個 Agent 皆完成後，回到當前此對話 Session。
2. 輸入指令，例如：  
   `評測已完成，請調閱歷史紀錄進行評估分析。Agent A Session: <ID-A>, Agent B Session: <ID-B>`  
   *(亦可直接通知完成，本 Session 會自動從 IDE transcript 紀錄中調閱最近的 2 個 Session)*。
3. 本 Session 將深度解析雙方的 `transcript.jsonl` 與結果檔，產出包含**雷達圖/量化對比表、Token 節省率分析、耗時比對、檢索路徑深度與錯誤幻覺分析**的完整綜合評估報告。
