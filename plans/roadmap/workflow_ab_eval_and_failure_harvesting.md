# 技術路線圖：工作流單階段切片雙盲 A/B 評測與歷史錯題收割管線 (Roadmap)

> 主題：工作流單階段切片雙盲 A/B 評測與歷史錯題收割管線 (`workflow_ab_eval_and_failure_harvesting`)  
> 歸檔日期：2026-10-28  
> 狀態：Proposed  
> 目標範疇：`agents-workflow` (`agents_workflow/eval/`, `scripts/cli.py`, `assets/skills/skill-optimizer/`)、`dev` (`dev/testing/sandbox.py`)  
> 前置解鎖條件：完成 `session_audit_and_trace_telemetry`  
> 模型：Gemini 4 Argon (High)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- **工作流深水區微調難以單憑體感（Vibe Check）衡量 ROI**：當 `agents-workflow` 進入細部調優（例如微調某階段提示詞條款、調整 Subagent 委派門檻、增減檢核點）時，往往伴隨「邊界防禦力提升 vs. Token 消耗／耗時增加」的取捨，受 LLM 隨機性影響難以單憑單次日常體感客觀定奪。
- **全流程重跑成本過高且缺乏真實地雷題庫**：若每次測試 `P04` 或 `P07` 的單一條款都必須從 `P00` 一路跑完 `P07`，時間與 Token 成本過高；而人工憑空編造玩具題目（Toy Problems）既耗時又無法反映真實工程邊界。
- **考官討好偏見（Sycophancy）與宿主 System Prompt 污染**：若主 Agent 事先知曉哪一組是剛修改的新條款，極易產生盲目判贏偏見；同時宿主 IDE 自動注入根目錄 `AGENTS.md` 的機制會污染單純依賴目錄切換的沙盒實驗。

### 1.2 現況與影響範圍評估
- 既有 `skill-optimizer`（`references/ab-eval-guide.md`）已定義 Mode B 之 `trigger_evals.json`、`evals.json` 與 `benchmark.json` 概念，但尚無自動化雙盲沙盒初始化 CLI、單階段切片重播機制與歷史錯題收割工具。
- `plans/archived/` 中累積了大量真實發生過的 `revision_log.md` 與修復計畫，尚未轉化為結構化的地雷陣基準測試集（Baseline Suite）。

### 1.3 核心根因
1. 缺少支援「單階段切片重播（Single-Phase Replay）」與「Prompt 顯式規則路徑注入 + 雙盲隨機編號（`Candidate_Alpha` / `Candidate_Beta`）」的自動化評測 CLI。
2. 缺少將 `plans/archived/` 歷史 `revision_log.md` 及日常 `/session-audit` 抓出之瑕疵快速凍結為「地雷陣檢核點（Planted Landmines Rubric）」的題庫收割管線。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：新建獨立頂層模組 `module:agents-ab-test`** | 獨立建立第 6 個核心模組，自帶一套與 `skill-optimizer` 分離的 CLI 與 `/ab-test` Skills | 模組目錄看似獨立 | 與 `agents-workflow` 及 `skill-optimizer` 職責重疊，增加跨模組維護與安裝認知負擔 | ⭐️⭐️⭐️ |
| **方案 2：內聚整合至 `agents-workflow` 並升級 `skill-optimizer` 雙盲切片評測** | 於 `agents-workflow` 新增 `eval` / `harvest` CLI 引擎，結合 Prompt 顯式規則路徑隔離（規避宿主 System Prompt 污染）、雙盲代號映射與地雷陣 Checkpoints，並與 `skill-optimizer` Mode B 無縫合流 | 零額外頂層模組膨脹、工具鏈單一收口、100% 規避宿主根目錄 `AGENTS.md` 污染 | 需設計精簡的 `case_manifest.json` 與加密雙盲映射表 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（獨立頂層模組） | 方案 2（內聚整合至 `agents-workflow` + 顯式規則注入雙盲沙盒） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 中（沙盒根目錄 `AGENTS.md` 無法覆蓋宿主自動注入之 System Prompt） | 極高（透過單階段切片 + Prompt 顯式注入受測規範路徑，100% 物理隔離） |
| **後續維護難度 (Maintenance)** | 高（需額外維護第 6 個模組發布與版本同步） | 低（與 `PlanVerifier` 及 `skill-optimizer` 同源演進） |
| **可靠性 (Reliability)** | 中 | 高（硬指標由 Python 0 成本確定性統計，軟指標採 0/1 地雷捕捉 Checkpoints） |
| **落地難度 (Implementation)** | 中 | 低 |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 步驟 1：定義題庫 Schema (case_manifest.json) 與三大題庫來源
# - 來源一：挖掘 plans/archived/ 具代表性之 revision_log.md（儲存前置 P01~P03 快照 + Git Commit Hash / 符號切片 + 反轉地雷 Checkpoints）
# - 來源二：日常失敗順手收割（`python yscb.py agents-workflow eval harvest` 抓取修改前狀態與 Negative Trap / Checkpoint）
# - 來源三：Saboteur Subagent 逆向變異埋雷合成

# 步驟 2：實作雙盲沙盒初始化與硬指標統計 CLI
# - `python yscb.py agents-workflow eval init <case_id>`：建立 sandbox_alpha / sandbox_beta，隨機打亂 Control / Variant 映射並加密暫存
# - `python yscb.py agents-workflow eval score <run_id>`：由 Python 自動統計字元數（Token 通膨率）、執行耗時、PlanVerifier 首次通過率與沙盒測試通過率，結合雙盲考官之 Checkpoints 得分後解密生成對照表

# 步驟 3：升級 skill-optimizer 與評測工作流
# - 對接 `/session-audit` 之 [Harvest Candidate] 收割閉環與單階段切片雙盲派發
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 拒絕外部付費 API 多輪轟炸基建，以「單階段切片 + 0/1 硬性地雷捕捉 Checkpoints + Python 確定性硬指標」建立輕量高鑑別度量尺。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（題庫 Schema 與雙盲評測 CLI）**：於 `agents-workflow` 實作 `case_manifest.json` 解析、雙盲隨機映射沙盒與硬指標統計器。
2. **Stage 2（提煉首批 3~5 道黃金歷史錯題）**：自 `plans/archived/` 挑選具代表性的 `revision_log.md` 案例轉化為基準題庫。
3. **Stage 3（收割指令 `harvest` 與技能整合）**：實作 `eval harvest` 並更新 `skill-optimizer` 完成「觀測 $\rightarrow$ 收割 $\rightarrow$ 雙盲評測」飛輪。

