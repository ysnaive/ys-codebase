# 技術路線圖：工作流宣告式階段拓撲引擎與可插拔領域擴充架構 (Roadmap)

> 主題：工作流宣告式階段拓撲引擎與可插拔領域擴充架構 (`declarative_track_schema_and_domain_packs`)  
> 歸檔日期：2026-10-28  
> 狀態：Proposed  
> 目標範疇：`agents-workflow` (`agents_workflow/plans/{status.py,verifier.py,scanner.py}`, `contributes/_format.json`)  
> 前置解鎖條件：完成 `workflow_ab_eval_and_failure_harvesting`（具備量化回歸測試基準）  
> 模型：Gemini 4 Argon (High)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- **階段拓撲與檢核邏輯存在硬編碼條件分支**：目前 `agents-workflow` 的 `status.py` 與 `verifier.py` 雖支援 6 大計畫模式（`full`, `fast`, `umbrella`, `revision`, `research`, `roadmap`），但其階段轉換順序、檔名匹配規則與檢核條件主要以 Python 條件分支寫死在引擎內部。
- **跨領域擴充缺乏宣告式 `contributes` 接口**：當未來面對非純軟開發場景（如系統企劃與數值設計 `design`、遊戲引擎資產管線 `unity`、機構與電子工程 `cad` / `spice`）時，外部模組無法透過 `contributes/agents-workflow.json` 宣告自訂的階段有向無環圖（Phase DAG）、專屬模板與領域驗收鉤子（Gate Validators）。

### 1.2 現況與影響範圍評估
- `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py`（約 600 行）與 `verifier.py`（約 1,480 行）承載了固定階段識別邏輯。
- `ys_codebase/source/agents-workflow/contributes/_format.json` 目前僅開放 `export`、`token`、`insert`、`release_target` 四類擴充點，尚無 `track` 或 `gate_validator` 宣告契約。

### 1.3 核心根因
1. 缺少將「計畫分支（Plan Track）」抽象為包含 `phase_id`、`filename`、`template_uri`、`context_whitelist`、`required_sections` 與 `gate_validators` 之表驅動 `TrackSpec` 模型。
2. 缺少階段感知的「按需提示詞路由（Phase-Scoped Routing）」與跨領域子計畫混合編排（Cross-Track Umbrella）支援。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：物理拆包為 `agents-workflow`（空引擎）+ `agents-workflow-code`（規則包）** | 將現行軟體開發 `P00`~`P07` 模板與規則強制剝離為獨立的第 6 個模組 | 形式上完全分離 | 造成嚴重的雙模組同步打包、測試與版本耦合摩擦（Split-Brain Friction），違背日常高頻迭代效率 | ⭐️⭐️ |
| **方案 2：內部表驅動 `TrackSpec` 解耦 + 開放 `contributes` 領域擴充（預設 `code` 內建不拆包）** | 將 `status.py` 與 `verifier.py` 重構為讀取宣告式 `TrackSpec` 註冊表，將現有軟體開發模式作為內建預設 Track，同時透過 `contributes/_format.json` 開放外部領域模組註冊新 Track 與驗證鉤子 | 100% 具備跨領域可插拔擴充能力、日常核心開發 0 拆包摩擦、開箱體驗零退化 | 需重構 `status.py` 與 `verifier.py` 內部狀態轉移表並通過 A/B 回歸測試 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（物理拆出 `agents-workflow-code`） | 方案 2（內部表驅動 `TrackSpec` + 開放 `contributes` 擴充） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 中 | 高（100% 相容現有模組拓撲與 CLI 介面） |
| **後續維護難度 (Maintenance)** | 高（每次改模板需跨兩模組 `@build` 與發布） | 極低（單一模組閉環維護，外部領域按需外掛） |
| **可靠性 (Reliability)** | 中（跨模組版號錯配風險） | 極高（內建預設 Track 零外部相依） |
| **落地難度 (Implementation)** | 高 | 中 |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 步驟 1：定義宣告式 TrackSpec Schema 並擴充 contributes/_format.json
# 支援欄位：track_id, phases (phase_id, filename, template_uri, context_whitelist, required_sections), gate_validators

# 步驟 2：重構 PlanStatusResolver (status.py) 與 PlanVerifier (verifier.py) 為表驅動引擎
# - 將現行 6 大模式轉化為內建標準 TrackSpec 定義表
# - 拆分為「通用結構檢核層（Core Verifier）」與「可插拔領域驗證鉤子（Contributed Gate Validators）」
# - 於 `plan status --resume` 動態輸出當前 Track 與階段專屬之 [Active Phase Directive] 按需載入指引（平時 0 Token 佔用）

# 步驟 3：升級 Umbrella 支援跨領域子計畫混合編排 (Cross-Track Umbrella)
# - 允許同一母計畫下之 sub_XX 分別採用不同領域 Track，並執行量化 A/B 題庫驗證解耦前後行為 100% 零退化
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 遵循「內部表驅動先行、外部領域包按真實下游需求孵化」原則，先完成核心狀態機的表驅動純化與擴充點開放，避免在無實際非軟專案時過早建立空殼領域包。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（`TrackSpec` 表驅動狀態機與驗證器重構）**：重構 `status.py` 與 `verifier.py` 改由宣告式結構驅動，並於 `contributes/_format.json` 開放 `track` 與 `gate_validator` 註冊。
2. **Stage 2（階段感知路由與 Cross-Track Umbrella）**：實作按需階段提示詞路由與 `Umbrella` 跨 Track 子計畫狀態聚合，執行 A/B 基準回歸驗證零退化。
3. **Stage 3（首個非 Coding 領域擴充包實戰孵化）**：待實際下游非純軟場景（如 `design`、`unity` 或 `cad`）立項時，以標準外部插件形式掛載專屬 Track 與 `knowledge-db` 領域解析器。

