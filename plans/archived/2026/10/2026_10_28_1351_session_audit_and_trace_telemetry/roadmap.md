# 技術路線圖：Session 隱形摩擦自檢技能與三級軌跡提取機制 (Roadmap)

> 主題：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 歸檔日期：2026-10-28  
> 狀態：Ready  
> 目標範疇：`core` (`core/commands/dispatcher.py`)、`server` (`server/worker.py`)、`agents-workflow` (`scripts/cli.py`, `assets/skills/session-audit/`)  
> 前置解鎖條件：無  
> 模型：Gemini 4 Argon (High)  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
- **自我修復掩蓋上游提示詞缺陷（Self-Healing Masks Upstream Defects）**：在嚴密的 `P00`~`P07` 與檢核機制下，若 AI 在 `P02` 或 `P04` 被模稜兩可的 `SKILL.md` 條文誤導，往往會在 `P05` 實作撞牆或 `P06` 測試失敗時自行發現並默默修好。最終產出物看似完美，但中間浪費了大量無效 Tool Calls 與 Tokens，且導致誤導的規範缺陷未被顯性揭露。
- **單純依賴 AI 事後回憶檢討存在三大盲區**：
  1. **事後合理化（Hindsight Bias）**：長對話結束時早期 `<thinking>` 權重淡化，易將曲折試錯美化為合理探索。
  2. **越權修改風險（Over-correction Hazard）**：若無唯讀安全隔離，自檢時可能擅自動用編輯工具塗改已通過測試之代碼或正式文檔。
  3. **歸因模糊（Attribution Confusion）**：缺乏結構化分類時，易籠統歸咎於「自己疏忽」，無法精準定位規範檔案與段落。

### 1.2 現況與影響範圍評估
- 目前 `core` 與 `server` 執行 CLI 派發時，尚未將單次 Session 內的命令調用軌跡（指令、參數、耗時、Exit Code、報錯摘要）寫入輕量飛行紀錄器。
- `agents-workflow` 尚無針對「同檔多次修改震盪（Multi-Edit Churn）」、「工具呼叫報錯與空轉（Tool Call Misses & Retries）」、「未申報之跨階段暗中回補（Silent Back-patching）」、「驗證關卡退件（Gate Bounces）」與「無效上下文載入（Context Waste）」五大硬性摩擦訊號的自動提取 CLI 與唯讀診斷 Skill。

### 1.3 核心根因
1. 缺乏跨平台、不依賴外部 IDE 私有格式的 YSCB 原生輕量 CLI Telemetry 與結合 `changelog.md` 變更紀錄的 `P0X` 時間戳逆序審計機制。
2. 缺乏具備「絕對唯讀隔離」與「A/B/C/D 四象限根因分類樹」的事後法醫解剖技能（`/session-audit`）。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：純靠各 IDE 本地 `.jsonl` 對話紀錄解析** | 直接讀取 `~/.claude`、`~/.codex` 或 Antigravity 本地 `.jsonl` 提取 Tool Calls 與 `<thinking>` | 可取得完整原始思考鏈 | 各宿主路徑與 Schema 差異大，且受沙盒 `$HOME` 讀取權限限制易失效 | ⭐️⭐️⭐️ |
| **方案 2：YSCB 原生 Telemetry + `mtime` 底座 + 本地 `.jsonl` 三級漸進提取** | 以 `cache://agents-workflow/session_telemetry.jsonl` 與 `plans/<active>/` 結合 `changelog.md` 之 `mtime`/`git diff` 為 100% 跨平台底座，並支援本地 `.jsonl` 增強與 In-Context 逆向審訊保底 | 100% 跨平台可用、零沙盒阻斷風險、可精確區分「合法規格回寫」與「暗中偷改」 | 需於 `dispatcher.py` 與 `server` 埋入極簡無阻塞日誌追加 | ⭐️⭐️⭐️⭐️⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 方案 1（純外部 `.jsonl` 解析） | 方案 2（三級漸進式軌跡提取 + 四象限歸因） |
| :--- | :--- | :--- |
| **可行性 (Feasibility)** | 中（受限於宿主沙盒邊界與私有格式變動） | 極高（核心底座 100% 掌控於 YSCB 空間內） |
| **後續維護難度 (Maintenance)** | 高（需持續追趕多家 IDE 日誌格式） | 低（原生 Telemetry 格式固定，外部 `.jsonl` 按需適配） |
| **可靠性 (Reliability)** | 中 | 極高（三級 Fallback 保證任何環境皆有鐵證可查） |
| **落地難度 (Implementation)** | 中 | 低 |

---

## 4. 核心機制與落地步驟 (Implementation Mechanism & Steps)

```bash
# 步驟 1：於 core/commands/dispatcher.py 與 server 熱派發處寫入輕量 Telemetry
# 記錄 {timestamp, cmd, exit_code, duration_ms, error_head} 至 cache://agents-workflow/session_telemetry.jsonl

# 步驟 2：實作 `python yscb.py agents-workflow session-trace [--plan <dir>] [--json]`
# - Tier 1：若環境支援讀取當前 Session 之 transcript.jsonl / IDE jsonl，提取失敗/重試 Tool Calls、同檔多次 Edit 與事發前後 <thinking>
# - Tier 2：讀取 session_telemetry.jsonl 抓出非 0 Exit Code 與重複檢索，並比對 P00~P07 mtime（扣除 changelog.md 合法 REVISION/DECISION 回寫紀錄）與 git diff
# - Tier 3：若無外部與 CLI 紀錄，輸出 [Fallback: In-Context Mode] 觸發強制回合逆向審訊表

# 步驟 3：建立唯讀技能 `/session-audit` (assets/skills/session-audit/SKILL.md)
# - 嚴守絕對唯讀安全隔離（僅輸出終端報告或獨立寫入 plans/<active>/session_audit.md，嚴禁修改源碼或 P00~P07）
# - 強制對五大摩擦訊號執行四象限歸因：
#   * Type A：提示詞／SOP 歧義或遺漏（給出檔案、段落與建議 Diff）
#   * Type B：ACI 工具介面或檢索斷層（給出 CLI --help 或索引強化建議）
#   * Type C：任務本質的不可知探索（標記為健康試錯，建議是否沉澱至 docs/）
#   * Type D：模型注意力滑脫／規則未遵循（評估升級為 checker.py / verifier.py 硬性攔截）
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
- 在不變動現有 SOP 流程的前提下，優先建立零副作用的觀測顯微鏡，讓日常開發中的隱形彎路顯性化，並作為後續量化 A/B 評測的真實錯題探測器。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1（原生 Telemetry 與 `session-trace` CLI）**：於 `core` / `server` 埋入極簡 Telemetry 紀錄，並於 `agents-workflow` 實作 `session-trace` 三級提取引擎（含合法規格回寫識別）。
2. **Stage 2（`/session-audit` 唯讀診斷技能）**：建立 `assets/skills/session-audit/SKILL.md`，固化五大硬性摩擦訊號檢核、四象限分類樹與收割建議卡（`[Harvest Candidate]`）。
3. **Stage 3（沙盒測試與編譯發布）**：補齊單元測試，執行 `dev check`、`dev test` 與 `@build` 物化同步。

