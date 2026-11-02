---
name: session-audit
description: 提取對話之隱形摩擦軌跡 (session-trace)，執行決策瑕疵解剖與四象限根因診斷。僅於顯式輸入 /session-audit 時觸發，嚴禁主動觸發。
---

# Session 隱形摩擦與決策瑕疵自檢工作流 (Session Audit)

本技能定位為「事後法醫解剖（Post-Mortem Autopsy）」，結合 `session-trace` 三級軌跡提取引擎、[`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`) 盲眼子代理認知隔離機制與四象限根因分類樹，揭露開發過程中因 AI 自我修復而被掩蓋的走彎路、重複試錯與提示詞誤導，並切斷當事主代理的自我辯護與敘事合理化偏誤。

```markdown
/session-audit 四步執行檢核表：
- [ ] 步驟 1：嚴守唯讀隔離，主代理調用 `session-trace` 提取會話基礎統計、五大硬性摩擦訊號與思考鏈切片
- [ ] 步驟 2：依 `BlindSubagentStandards.md` 執行認知隔離分流（有摩擦/錯誤訊號時強制派發盲眼 Subagent 核對五大訊號；0 摩擦且 0 錯誤或 Tier 3/無子代理環境按規分流）
- [ ] 步驟 3：對每項摩擦訊號執行 A/B/C/D 四象限冷眼根因歸類與修補對策推導（嚴防將 Type D 規則滑脫合理化為 Type C 探索）
- [ ] 步驟 4：由主代理彙整輸出結構化自檢診斷卡（含會話基礎常數、審計執行主體與 Token 統計）並立即 End Turn
```

---

## 1. 核心鐵律：絕對唯讀安全隔離、盲眼認知隔離與零臆測鐵證紀律

1. **禁止修改業務與規格資產**：執行 `/session-audit` 期間，主代理與盲眼 Subagent **嚴禁修改任何專案原始碼、設定檔或既有的 `P00`~`P07` / `fast_track_plan.md` / `revision_log.md` 計畫文檔**。
2. **無鐵證不歸因，嚴禁推估語句 (`Zero-Speculation Autopsy`)**：
   - 分析報告**絕對禁止出現「推測、可能、大概、也許、估計是因為...」等模糊臆測字眼**。
   - 每一條摩擦歸因與修補對策，必須 100% 綁定明確的 `Step #`、`<thinking>` 原文切片、工具調用參數或錯誤輸出（`session-trace` 已自動聯集 `transcript_full.jsonl` 補齊截斷行）；若日誌確實未記載某決策動機，強制標註 `[日誌未載，不予臆測]`。
3. **盲眼認知隔離與防自我辯護鐵律 (`Blind Autopsy & Anti-Rationalization`)**：
   - 當事主代理因持有完整對話歷史脈絡，極易因「敘事慣性（Narrative Inertia）」與「確認偏誤（Confirmation Bias）」將明明已記載於 `AGENTS.md` 或 `SKILL.md` 的 **`Type D（模型注意力滑脫／規則未遵循）`** 防衛性合理化為 **`Type C（任務本質的不可知探索）`**。
   - 因此，凡 `session-trace` 檢出**任一硬性摩擦訊號 (`len(friction_signals) > 0`) 或錯誤步數 (`error_steps > 0`)** 且處於 `Tier 1+2` / `Tier 2` 時，主代理**強制讀取 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`) 並委派唯讀盲眼 Subagent（原型 ② 基準對齊冷眼靜態審查）**執行步驟 2 與步驟 3 之四象限根因解剖。
4. **允許產出範圍**：預設僅於對話視窗輸出結構化診斷報告；唯有開發者明確要求落檔時，方允許寫入獨立診斷檔 `__${workflow.plans://}__/<active_plan>/session_audit.md`。

---

## 2. 執行步驟

### 步驟 1：調用 `session-trace` 提取摩擦鐵證
- 若欲先檢視本工作區有哪些歷史對話紀錄可分析，可執行 `--list`（加 `--all` 可顯示跨專案與 Subagent 對話）：
  ```bash
  python __${yscb.host://yscb.py}__ agents-workflow session-trace --list [--all]
  ```
- 若當前宿主環境上下文已宣告本輪對話之 Transcript 路徑（如 Antigravity 之 `transcript.jsonl`），優先帶入 `--transcript` 以 100% 鎖定主視窗：
  ```bash
  python __${yscb.host://yscb.py}__ agents-workflow session-trace [--transcript <path>] [--plan <plan_dir>]
  ```
- 若回報多份工作區候選 `.jsonl`（`transcript_candidates`）或多活躍計畫提示，依提示補入 `--transcript` 或 `--plan` 重新提取。
- **三級觀測降級說明**：`Tier 1+2` 代表同時具備宿主 `.jsonl` 對話軌跡與 CLI 遙測日誌；`Tier 2` 代表僅具備 CLI 遙測日誌；`Tier 3` 代表兩者皆不可用時，降級由主代理依對話上下文進行結構化逆向自白。

### 步驟 2：盲眼子代理派發分流與五大硬性摩擦訊號核對

1. **三軌審計執行主體分流 (`Audit Executor Triage`)**：
   - **軌道 A — 零摩擦快速放行（`0 Friction & 0 Error Fast-Pass`）**：若 `session-trace` 提取結果確認 **`friction_signals` 為空 (`0` 項) 且 `error_steps == 0`**，免派發 Subagent（節約冷啟動 Token），直接由主代理彙整 `session_stats` 進入步驟 4 輸出零摩擦報告（審計主體標註 `Main Agent (0-Friction Fast-Pass)`）。
   - **軌道 B — 盲眼子代理冷眼解剖（`Blind Subagent Autopsy`，預設強制軌道）**：當 `len(friction_signals) > 0` 或 `error_steps > 0`（且非 `Tier 3`）時，主代理**必須先讀取 [`BlindSubagentStandards.md`](`__#{module://agents-workflow/assets/standards/BlindSubagentStandards.md}__`)**，套用其 `§5.2 主代理 -> 盲眼 Subagent 專用派發訊息模板`（**原型 ②：基準對齊冷眼靜態審查**，`Mode I` 回傳 150~400 Tokens 濃縮結論）派發唯讀 Subagent：
     - **去錨定傳址 (`Pointer-Only`)**：僅向盲眼 Subagent 傳遞步驟 1 執行之 `session-trace` 精確命令（或已提取之結構化訊號座標）、本技能 `session-audit/SKILL.md` 路徑，以及事發步驟涉及之 `AGENTS.md` / 相關 `SKILL.md` 規範路徑。**嚴禁在派發 Prompt 中夾帶主代理的主觀辯解、心路歷程說明或預先歸類傾向！**
     - **反合理化審計基準注入**：要求盲眼 Subagent 逐一核對事發 `Step #` 前後之 `<thinking>` 切片與當時已生效之規範條文；**凡規範或 CLI `-h` 已明文記載卻未遵循、漏讀或盲猜參數者，一律剛性歸為 `Type D`（或 `Type A/B`），嚴禁放水歸入 `Type C`！**
   - **軌道 C — 無子代理環境或 `Tier 3` 降級（`Inline Fallback`）**：若當前宿主環境不支援 Subagent 工具或處於 `Tier 3` 無外部日誌模式，依 `BlindSubagentStandards.md §1` 自動降級由主代理 Inline 執行，並於報告頂部顯式標註 `Main Agent [Inline Fallback]`。

2. **核對五大硬性摩擦訊號**：
   依據 `session-trace` 輸出（或 Tier 3 逆向審訊表），逐一盤點：
   - **`MULTI_EDIT_CHURN`（同檔多次修改震盪）**：同一檔案跨步驟重複修改 $\ge 2$ 次。
   - **`TOOL_MISS_AND_RETRY`（工具報錯與檢索空轉）**：CLI 非零退出碼、參數猜錯重試或連續 `knowledge-db search` $\ge 3$ 次。
   - **`SILENT_BACKPATCH`（未申報之跨階段暗中回補）**：後期階段回頭修改前期 `P01`~`P03` 規格卻未登記於 `changelog.md`（已合規登記之 `VALIDATED_BACKPROP` 不列為違規）。
   - **`GATE_BOUNCE`（驗證關卡退件）**：遭 `plan verify`、`dev check`、`dev test` 或 `contributes check` 攔截退回。
   - **`CONTEXT_WASTE`（無效上下文載入）**：同檔案區段重複讀取 $\ge 2$ 次，或未先執行 `knowledge-db search` 即連續原生翻讀 $\ge 4$ 個源碼檔。

### 步驟 3：A/B/C/D 四象限根因分類樹
針對每項摩擦訊號，對照事發當下之 `<thinking>` 摘要與已載入規範，嚴格歸入四象限之一：
- **Type A（提示詞／SOP 歧義或遺漏）**：已載入之 `SKILL.md`、模板或規範條文含糊矛盾。**行動**：指出具體檔案與段落標題，給出文字修改建議（可轉交 [`/skill-optimizer`](`__#{module://agents-workflow/assets/skills/skill-optimizer/SKILL.md}__`) 或 Revision 修訂）。
- **Type B（ACI 工具介面或檢索斷層）**：CLI `--help`、報錯提示不明確或索引涵蓋不足導致盲猜。**行動**：指出應強化之模組 CLI 提示或檢索空間。
- **Type C（任務本質的不可知探索）**：外部環境或底層邊界需實測方能確認（且規範未預先載明）。**行動**：標記為「健康試錯（Healthy Exploration）」，評估是否沉澱至 `__${workflow.docs://}__`。
- **Type D（模型注意力滑脫／規則未遵循）**：規範已明文記載但執行時遺漏或僥倖跳過。**行動**：評估是否將文字規則升級為 `verifier.py` / `checker.py` 靜態硬性攔截。

`__@{SESSION_AUDIT_STANDARDS}__`

### 步驟 4：輸出結構化自檢診斷卡（強制 End Turn）

```markdown
### 🔬 /session-audit 隱形摩擦與決策自檢報告
- **觀測層級與審計主體**：`[Tier 1+2 | Tier 2 | Tier 3]` / 審計主體：`[Blind Subagent (原型 ②) | Main Agent (0-Friction Fast-Pass) | Main Agent [Inline Fallback]]` / 計畫：`[plan_name 或 None]` / Telemetry：`[N]` 筆
- **會話基礎統計 (Session Metrics)**：
  - **耗時與回合**：歷時 `[session_duration_human]` / 總步數 `[total_steps]`（使用者 `[user_turns]` 回合、模型 `[model_turns]` 回合、思考鏈 `[thinking_steps]` 步、截斷 `[truncated_steps]` 步、錯誤 `[error_steps]` 步）
  - **Token 消耗統計**：完整計算 `~[estimated_full_tokens]` Tokens / 精簡 `~[estimated_compact_tokens]` Tokens（使用者輸入 `[user_input]`、模型回覆 `[model_output]`、思考鏈 `[thinking]`、工具參數 `[tool_call_args]`、工具輸出 `[tool_outputs]`；日誌體積 `[transcript_compact_kb]` KB / Full `[transcript_full_kb]` KB）*(若具原生 API Usage 則併列 `reported_api_usage`)*
  - **Token 效益與浪費分析 (Token ROI & Waste Breakdown)**：有效生產 `~[effective_tokens]` Tokens (`[efficiency_pct]%`) / 無效浪費 `~[wasted_tokens]` Tokens (`[waste_pct]%`：重複讀檔 `[duplicate_reads]`、失敗與退件步驟 `[failed_tool_steps]`、返工覆寫 `[edit_churn_rework]`、未檢索盲讀 `[unindexed_blind_reads]`)
  - **高耗能工具與指令排行 (Top Token Consumers)**：
    - **工具耗能佔比 Top 3 (`by_tool`)**：列出前三大消耗 Token 之工具、總 Token（佔比 `%`）與單次平均 Token
    - **單步重度操作 Top 3 (`heavy_steps`)**：列出 `Step #`、工具與目標檔/指令、單步消耗 Token
    - **高耗能 CLI 指令 Top 3 (`heavy_cli_commands`)**：列出消耗大量輸出 Token 之具體 CLI 命令字串與 `Step #`，診斷是否因漏加 `-q`/`-s` 或全量傾倒所致
  - **工具與檔案操作**：工具調用 `[total_tool_calls]` 次（前三大工具分佈：`[tool_distribution]`）/ 讀檔 `[total_read_ops]` 次（涵蓋 `[unique_files_read]` 個不重複檔案）/ 改檔 `[total_edit_ops]` 次（涵蓋 `[unique_files_edited]` 個不重複檔案）/ 子代理派發 `[subagent_calls]` 次
  - **CLI 遙測統計**：總呼叫 `[cli_total_calls]` 次 / 失敗 `[cli_failed_calls]` 次 / 總耗時 `[cli_total_duration_ms]` ms（平均 `[cli_avg_duration_ms]` ms）/ 派發模式分佈 `[cli_by_mode]` / 模組分佈 `[cli_by_module]`
- **摩擦訊號總覽**：共捕捉 `[M]` 項訊號（`MULTI_EDIT_CHURN: x`, `TOOL_MISS_AND_RETRY: y`, `SILENT_BACKPATCH: z`, `GATE_BOUNCE: w`, `CONTEXT_WASTE: k`）
- **四象限根因診斷**：
  1. **[Type A/B/C/D] 訊號類別 @ 標的**：[根因剖析與具體修補建議（精確至檔案與段落）]
- **後續收斂建議**：`[維持現狀 | 建議執行 /skill-optimizer 優化技能 | 建議透過 /todo 登載待辦 | 建議開啟修訂計畫]`
```

---

## 常見踩坑指南 (Gotchas)

- **切勿在派發盲眼審計 Subagent 時夾帶主視窗的「事後辯解」**：主代理傳遞給盲眼 Subagent 的 Prompt 必須維持 100% 中立（僅傳遞 `session-trace` 客觀數據與規範路徑），嚴禁暗示「因為某原因所以當時沒辦法遵守規則」，否則將破壞盲眼隔離效果。
- **切勿在自檢過程中順手改動源碼或計畫檔**：發現問題時僅允許在報告中提出具體 Diff 建議或詢問開發者是否透過 [`/todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`) 登記。
- **切勿將合規回寫誤判為暗中偷改**：若 `session-trace` 標記為 `VALIDATED_BACKPROP`，代表已在 `changelog.md` 或 `revision_log.md` 留有正式修訂紀錄，屬正常工程回寫。

