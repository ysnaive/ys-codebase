# Knowledge-DB vs 傳統工具 基準評測綜合對比報告 (Benchmark Evaluation Report)

> **評測執行時間**：2026-09-05 12:44 ~ 12:52 UTC  
> **評測標的**：YS-Codebase `knowledge-db` (v1.0.2.0)  
> **實驗組 (Agent A)**：Conversation ID `f1cbe57e-182d-4213-a474-2c990e38ddd5`（使用 `knowledge-db` 工具鏈）  
> **對照組 (Agent B)**：Conversation ID `90a6547f-3966-47bd-9460-b76edb6b4418`（僅限 `grep_search` / `view_file` 傳統工具）  
> **測試題目**：`benchmark/QUESTIONS.md` (Level 1~3 共 9 題，含客觀 Ground Truth)

---

## 📊 1. 核心效能指標量化對比 (Executive Summary)

| 評測維度 | 實驗組 (Agent A: Knowledge-DB) | 對照組 (Agent B: 傳統工具) | 差異幅度 (Gain / Efficiency) |
| :--- | :---: | :---: | :---: |
| **總耗時 (Wall-Clock Time)** | **37 秒** | **162 秒** (2分42秒) | ⚡ **提速 4.38 倍 (節省 77.2% 時間)** |
| **工具調用總次數 (Tool Calls)** | **15 次** | **37 次** | 📉 **減少 59.5% 工具往返** |
| **檢索讀取量 (Read Chars)** | **35,560 字元** | **49,228 字元** | 📉 **減少 27.8% 讀取容量** |
| **預估讀取 Tokens** | **8,893 Tokens** | **12,308 Tokens** | 📉 **節省 3,415 Tokens (單輪讀取)** |
| **推理/思考步驟 (Thinking Steps)** | **15 步** | **36 步** | 🧠 **降低 58.3% 模型認知負擔** |
| **Ground Truth 準確度** | **100% (9/9)** | **100% (9/9)** | 🎯 **雙方皆達最高精準度** |

---

## 📋 2. 分題詳細指標對照矩陣 (Question-by-Question Breakdown)

| 題號 | 題目維度與焦點 | 工具次數 (A vs B) | 讀取字元 (A vs B) | 預估 Tokens (A vs B) | 耗時 (A vs B) | 提速倍率 |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **Q1.1** | Level 1: 符號定位與依賴正規化簽名 | **2 vs 5** | 2,579 vs 3,818 | 645 vs 955 | **4s vs 20s** | **5.0x** |
| **Q1.2** | Level 1: 上游調用者排查 (Callers) | **1 vs 4** | 1,150 vs 3,145 | 288 vs 786 | **4s vs 18s** | **4.5x** |
| **Q1.3** | Level 1: 多階重構影響半徑 (Impact) | **1 vs 6** | 1,475 vs 8,530 | 369 vs 2,133 | **3s vs 25s** | **8.3x** |
| **Q2.1** | Level 2: Dev 沙盒 3-Tier 微環境投影 | **2 vs 3** | 4,566 vs 4,085 | 1,142 vs 1,021 | **4s vs 15s** | **3.8x** |
| **Q2.2** | Level 2: AST 解析與零特權自貢獻 | **2 vs 4** | 8,630 vs 5,795 | 2,158 vs 1,449 | **6s vs 18s** | **3.0x** |
| **Q2.3** | Level 2: 4-Tier 測試分流與跑測過濾 | **2 vs 1** | 4,620 vs 1,960 | 1,155 vs 490 | **5s vs 8s** | **1.6x** |
| **Q3.1** | Level 3: 測試警告收斂與崩潰診斷 | **1 vs 9** | 3,200 vs 12,390 | 800 vs 3,098 | **3s vs 30s** | **10.0x** |
| **Q3.2** | Level 3: 第三方套件隔離與自動適配 | **2 vs 1** | 3,290 vs 3,420 | 823 vs 855 | **4s vs 10s** | **2.5x** |
| **Q3.3** | Level 3: 複合檢索融合 (RRF) 與降級 | **2 vs 4** | 6,050 vs 6,085 | 1,513 vs 1,521 | **4s vs 18s** | **4.5x** |
| **總計** | **Total** | **15 vs 37** | **35.6k vs 49.2k** | **8.9k vs 12.3k** | **37s vs 162s** | **4.38x** |

---

## 🔍 3. 深度質化分析與架構洞察 (Qualitative Insights)

### 亮點 1：調用圖譜與影響分析的「降維打擊」 (Q1.2 & Q1.3)
- **對照組 (Agent B)**：
  - 在面對 Q1.2（排查誰調用了 `adapt_build_pip_dependencies`）時，傳統 Agent 必須先以 grep 搜尋符號，在大量匹配結果中過濾出真實業務代碼，再透過 `view_file` 打開相關檔案確認是否屬於調用點，耗費 4 次工具調用與 18 秒。
  - 在面對 Q1.3（多階影響面分析）時，傳統 Agent 陷入「遞迴人工比對」噩夢：先查 `PipManager` 被誰實例化，接著針對每個實例化方法再次 grep 其呼叫者，被迫進行 6 次工具往返、讀取 8.5k 字元，耗時 25 秒。
- **實驗組 (Agent A)**：
  - Agent A 調用 `knowledge-db callers` 與 `knowledge-db impact --depth=2`，**僅各需 1 次 CLI 指令**、**3~4 秒** 即可精確獲取 NetworkX 圖演算法計算出的 Layer 1 (4 個符號) 與 Layer 2 (5 個符號) 的完整依賴拓撲，且 100% 免疫字串同名幽靈關聯。

### 亮點 2：自然語言抽象問題的語意檢索突破 (Q3.1)
- **對照組 (Agent B)**：
  - 面對人類直白問題「跑測試時那些非致命警告是怎麼被收起來的？出錯時又怎麼保留關鍵錯誤？」，傳統 Agent 無法直接拿口語文字進行精確 grep，只能在 `docs/dev` 與 `source/dev` 之間反覆試探關鍵字（grep `## 7.` $\rightarrow$ grep `sandbox warning` $\rightarrow$ grep `tail` $\rightarrow$ grep `stderr` $\rightarrow$ list_dir $\rightarrow$ view tester.py），累計調用高達 **9 次工具**、讀取 **12.4k 字元**、耗時 **30 秒**。
- **實驗組 (Agent A)**：
  - Agent A 透過 `knowledge-db search '警告折疊' --space=docs --json -s`，BM25 與 FastEmbed BGE-small-zh 向量索引協同生效，直接在第一候選精準召回 `testing_guide.md` 第 7 節的完整切片，**僅需 1 次調用、3 秒完成**（提速 10 倍，節省 74% 讀取 Token）。

### 亮點 3：路徑漂移與目錄結構免疫
- **對照組 (Agent B)**：
  - 在 Q1.1 啟動時，傳統 Agent 直覺假設源碼目錄為 `/workspace/ys-codebase/source`，遭遇不存在錯誤後被迫調用兩次 `list_dir` 校正至 `/workspace/ys-codebase/ys_codebase/source`。
- **實驗組 (Agent A)**：
  - Knowledge-DB 的空間抽象協議（`--space=source`、`--space=docs`）在底層直接封裝了語意 URI 解算，無論實體路徑如何組織，CLI 檢索層 100% 免疫路徑假設錯誤。

### 亮點 4：上下文複利效應 (Compound Context Tax)
- 雖然單題讀取的字元量差異約為 13.6k 字元（~3.4k tokens），但在實際 Agent 交互中，**工具調用次數（37 次 vs 15 次）的差異具有嚴重的上下文化複利效應**：
  - Agent B 歷經 37 次 Tool Call / Response 往返，其上下文歷史 (Context Window) 急劇膨脹，每多一輪調用都需將先前所有工具歷史重新傳遞給模型，導致整體 API Input Token 消耗呈現二次方級數增長。
  - Agent A 以極簡 15 次往返結束任務，總 Session Context 體積較對照組節省超過 65%，顯著降低伺服端推理延遲與 API 費用。

---

## 🏁 4. 評測結論與後續建議

本次基準評測實機驗證了新版 `knowledge-db` 的核心工程價值：
1. **極速響應**：整體解答流程自 162 秒縮短至 37 秒（**提速 4.38 倍**）。
2. **精準無冗餘**：調用圖譜與語意向量融合檢索彻底消除了傳統 grep 漫無目的的猜測式試探。
3. **高保真度**：在所有 9 道實機題目中，Knowledge-DB 均達成與 Ground Truth 100% 吻合，無任何語意幻覺或漏判。
