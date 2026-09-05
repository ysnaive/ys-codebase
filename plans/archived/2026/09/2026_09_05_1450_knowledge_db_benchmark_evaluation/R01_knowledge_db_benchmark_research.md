# 技術調研報告：Knowledge-DB 雙基準測試綜合評估與審計報告

> 功能名稱：knowledge_db_benchmark_evaluation  
> 調研主題：Knowledge-DB 雙基準測試綜合評估與審計報告  
> 建立日期：2026-09-05  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 背景動機與調研範疇 (Background & Scope)

### 1.1 調研背景
在 AI Agent 輔助軟體開發過程中，代碼庫探索與語意理解通常依賴傳統工具（如 `grep_search`、`view_file`、`list_dir`）。然而，面對大型或多模組代碼庫時，傳統工具常遭遇以下瓶頸：
1. **上下文視窗膨脹**：全檔檢視或寬泛 grep 傳回大量非關鍵代碼，迅速耗盡上下文視窗。
2. **多輪往返延遲**：缺乏語意空間抽象與結構化調用圖譜，Agent 需多次嘗試猜測目錄結構與遞迴排查調用點。
3. **語意鴻溝**：開發者提出抽象或業務語意問題時，純詞法搜尋（Regex/Literal）難以精準命中。

為解決上述痛點，專案引入了 `knowledge-db` 模組，提供基於 AST 切片、語意向量檢索與調用拓撲分析能力。為了科學量化其工程效益，專案先後實施了兩輪基準測試（Benchmark 1: Core 基礎架構；Benchmark 2: 生態系實戰與疑難排查）。本調研報告旨在對兩份 Benchmark 進行獨立審計與客觀評估，提煉結構性優勢，修正數據偏差，並納入專案歷史資產封存。

### 1.2 調研納入資產清單
本計畫已將兩次基準測試的完整測試套裝、提示詞、答題記錄與評估報告納入計畫資產：
- **Benchmark 1 (Core 基礎架構評測)**：位於 `benchmark_1_core/`，包含 9 道題（符號定位、模組架構、語意理解）。
- **Benchmark 2 (生態系進階評測)**：位於 `benchmark_2_ecosystem/`，包含 9 道題（生命週期、跨模組排查、深層調用）。
- **受測 Agent 實例**：4 位獨立 Session Agent（A1: f1cbe57e, B1: 90a6547f, A2: cc7c1fb5, B2: 11c70f4b）與評估 Agent（7b3a9095）。

---

## 2. 實驗設計與控制變量審計 (Experimental Methodology Critique)

### 2.1 變量控制機制
兩次測試均採用嚴格的對照實驗設計：
- **實驗組 (Agent A)**：強制引導優先使用 `python yscb.py knowledge-db` 系列工具（`search`、`callers`、`callees`、`impact`、`status`）。
- **對照組 (Agent B)**：嚴格禁用 `knowledge-db`，僅允許使用環境原生工具（`grep_search`、`view_file`、`run_command`、`list_dir`）。
- **共同邊界**：兩組 Agent 接獲完全相同的 `QUESTIONS.md` 題目與客觀 Ground Truth。

### 2.2 空間抽象與先驗知識公正性分析
在審計過程中，針對 System Prompt 進行了嚴格核驗：
- 兩組 System Prompt **均未提供任何源碼實體目錄路徑**（兩組皆處於零路徑先驗狀態）。
- Agent A 所使用的 `--space=source` 是 `knowledge-db` 模組內建的語意空間抽象能力，而非 Prompt 額外洩漏之先驗知識。
- Agent B 在探索過程中因未知代碼結構而走訪無效路徑（例如誤判目錄層級），其產生的額外工具調用與時間消耗，正是**傳統工具缺乏空間抽象與索引的真實工程成本**，此項對比完全客觀公平。

### 2.3 指標偏差與限制校驗
審計發現以下需客觀看待之限制：
1. **Agent 自報偏差**：原始報告之 Tool Calls、字元讀取量與耗時均為 Agent 於結算時自填。經比對 Transcript 發現，報告數值精準反映了「解答問題的核心工具調用」，過濾了讀取 QUESTIONS 與寫入 results 的固定消耗。兩組篩選標準一致，相對比較維持有效。
2. **Wall-Clock Time 噪聲**：兩組 Agent 在不同時段與 Session 執行，總耗時（如 BM1 的 37s vs 162s）受到雲端 LLM 推理隊列負載、思考時間（Thinking Steps）與網路波動影響，4.38× 提速數據中含有模型推理噪聲。

---

## 3. 雙基準測試數據審計矩陣 (Audit & Metric Matrix)

### 3.1 原始數據 vs 審計校準數據對比

| 評測維度 | BM1 報告數值 | BM2 報告數值 | 審計判定 | 客觀校準估計區間 | 實質驅動因素 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **端到端提速** | 4.38× (37s vs 162s) | 1.88× (50s vs 94s) | ⚠️ BM1 偏樂觀<br/>✅ BM2 較穩健 | **2.0× ~ 3.0×** | 工具往返減少 + 思考鏈長度縮短 |
| **工具調用縮減** | 59.5% (15 vs 37) | 45.2% (23 vs 42) | ✅ 趨勢真實可信 | **40% ~ 50%** | 一步命中符號 vs 多輪 grep/目錄走訪 |
| **Token / 讀取量節省** | 27.8% (23.4k vs 32.4k) | 38.5% (20.5k vs 33.3k) | ✅ 結構性硬優勢 | **25% ~ 38%** | AST 精準切片 vs 800 行切片全檔翻讀 |
| **解答準確度** | 100% vs 100% | 100% vs 100% | ⚠️ 題目無分化度 | **0% 顯著差異** | 題目皆具單一明確正解，Agent 均具推導能力 |

---

## 4. 關鍵實證案例剖析 (Empirical Case Studies)

### 4.1 案例一：AST 語意切片 vs 全檔分段走訪 (BM2 - Q3.1)
- **場景**：排查 `knowledge-db daemon` 背景進程的生命週期與崩潰恢復邏輯。
- **傳統組 (Agent B)**：面對超過 900 行的 `daemon.py`，受限於單次工具讀取 800 行上限，被迫使用 5 次 `view_file` 切片分段閱讀代碼，消耗大量 Token 並造成多次上下文堆疊。
- **Knowledge-DB 組 (Agent A)**：透過 `knowledge-db search "daemon lifecycle" --space=source --snippet`，利用 AST 節點精準定位 `DaemonManager` 關鍵函式，僅調用 2 次工具即完整解答。
- **結論**：這是 AST 索引帶來的**結構性代價差異**，程式碼檔案越長、結構越複雜，效益越顯著。

### 4.2 案例二：語意融合檢索 vs 詞法 grep (BM1 - Q3.1)
- **場景**：回答自然語言技術問題「系統如何處理模組間的貢獻點 (contributes) 聚合？」。
- **傳統組 (Agent B)**：嘗試使用多組正則表達式進行跨檔案 grep，產生大量無效候選行，調用工具 9 次、耗時 30 秒。
- **Knowledge-DB 組 (Agent A)**：調用 `knowledge-db search "contributes aggregation"`，語意索引直接傳回 `ContributesRegistry` 核心類別與方法摘要，1 次命中、3 秒解答。
- **結論**：對於「業務概念已知但符號命名未知」的探索場景，語意檢索具備不可替代的工程價值。

### 4.3 案例三：邊界極限——純文字定位場景 (BM1 - Q2.3)
- **場景**：排查特定字串常數與組態檔案。
- **實測數據**：傳統組僅使用 1 次 `grep_search`、耗時 8 秒即精準命中。
- **結論**：在目標符號明確、字串具備唯一性的純詞法定位場景下，傳統 `grep` 與 `knowledge-db` 表現相當，`knowledge-db` 的邊際收益收斂。

---

## 5. Ground Truth 偏差校驗與記錄 (Ground Truth Correction)

在審計過程中，比對源碼與 [benchmark_1_core/QUESTIONS.md](file:///workspace/ys-codebase/plans/2026_09_05_1450_knowledge_db_benchmark_evaluation/benchmark_1_core/QUESTIONS.md) 時發現一處客觀 Ground Truth 定義偏差：

```diff
- 原 QUESTIONS.md (Q1.1) 宣稱: def parse_pip_dependencies(deps: Any) -> Dict[str, str]
+ 實際源碼簽名 (Core):         def parse_pip_dependencies(pip_deps: Any) -> List[str]
```

- **影響評估**：兩組受測 Agent（Agent A 與 Agent B）均如實從代碼中讀取並報告了正確的 `List[str]` 與 `pip_deps`。兩組答案皆正確，對比結論不受影響；但此處記錄作為 Ground Truth 修正依據。

---

## 6. 調研總結與流轉出口 (Concluded Recommendations)

### 6.1 調研結論
1. **真實核心價值**：`knowledge-db` 的核心價值不在於宣傳性的高倍率 Wall-Clock 提速（受模型推理延遲影響），而在於 **Token 消耗顯著降低 (25%~38%)** 與 **工具往返次數減少 (~45%)**。在多輪長上下文對話中，此效益因 Context 複利效應將大幅降低 API 調用成本並減少 Context Window 污染。
2. **適用邊界明晰**：
   - **極高價值**：大型檔案 AST 切片、調用拓撲追蹤（callers/callees/impact）、口語化語意概念探索。
   - **一般價值**：已知檔名之特定字串直接定位（與 grep 相當）。

### 6.2 流轉出口裁定
- **出口選擇**：**出口 ③ 存檔留痕 (Archive & Finalize)**
- **處置說明**：本調研之評估目標已全數達成，兩份基準測試原始資產已完整納入計畫目錄 `benchmark_1_core/` 與 `benchmark_2_ecosystem/`，調研結論正式固化，本計畫可逕行封存至 `plans/archived/2026/09/`。
