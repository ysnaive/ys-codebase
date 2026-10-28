---
name: session-audit
description: 執行當前或近期開發對話之隱形摩擦軌跡提取、決策瑕疵解剖與四象限根因診斷報告生成。僅於顯式輸入 /session-audit 或明確指示自檢分析對話摩擦與返工原因時觸發。
---

# Session 隱形摩擦與決策瑕疵自檢工作流 (Session Audit)

本技能定位為「事後法醫解剖（Post-Mortem Autopsy）」，結合 `session-trace` 三級軌跡提取引擎與四象限根因分類樹，揭露開發過程中因 AI 自我修復而被掩蓋的走彎路、重複試錯與提示詞誤導。

```markdown
/SessionAudit 四步執行檢核表：
- [ ] 步驟 1：嚴守唯讀隔離，調用 `session-trace` 提取會話基礎統計、五大硬性摩擦訊號與思考鏈切片
- [ ] 步驟 2：檢視提取結果（若處於 Tier 3 則執行強制回合逆向審訊自白）
- [ ] 步驟 3：對每項摩擦訊號執行 A/B/C/D 四象限根因歸類與修補對策推導
- [ ] 步驟 4：輸出結構化自檢診斷卡（含會話基礎常數與 Token 統計）並立即 End Turn
```

---

## 1. 核心鐵律：絕對唯讀安全隔離與零臆測鐵證紀律 (Read-Only & Evidence-Only Discipline)

1. **禁止修改業務與規格資產**：執行 `/session-audit` 期間，**嚴禁修改任何專案原始碼、設定檔或既有的 `P00`~`P07` / `fast_track_plan.md` / `revision_log.md` 計畫文檔**。
2. **無鐵證不歸因，嚴禁推估語句 (`Zero-Speculation Autopsy`)**：
   - 分析報告**絕對禁止出現「推測、可能、大概、也許、估計是因為...」等模糊臆測字眼**。
   - 每一條摩擦歸因與修補對策，必須 100% 綁定明確的 `Step #`、`<thinking>` 原文切片、工具調用參數或錯誤輸出（`session-trace` 已自動聯集 `transcript_full.jsonl` 補齊截斷行）；若日誌確實未記載某決策動機，強制標註 `[日誌未載，不予臆測]`。
3. **允許產出範圍**：預設僅於對話視窗輸出結構化診斷報告；唯有開發者明確要求落檔時，方允許寫入獨立診斷檔 `__${workflow.plans://}__/<active_plan>/session_audit.md`。

---

## 2. 執行步驟

### 步驟 1：調用 `session-trace` 提取摩擦鐵證
- 若欲先檢視本工作區有哪些歷史對話紀錄可分析，可執行 `--list`（加 `--all` 可顯示跨專案與 Subagent 對話）：
  ```bash
  python __${yscb.host://yscb.py}__ agents-workflow session-trace --list [--all]
  ```
- 若當前宿主環境上下文已宣告本輪對話之 Transcript 路徑（如 Antigravity 之 `transcript.jsonl`），優先帶入 `--transcript` 以 100% 鎖定主視窗：
  ```bash
  python __${yscb.host://yscb.py}__ agents-workflow session-trace [--transcript <path>] [--plan <plan_dir>] --json
  ```
- 若回報多份工作區候選 `.jsonl`（`transcript_candidates`）或多活躍計畫提示，依提示補入 `--transcript` 或 `--plan` 重新提取。

### 步驟 2：核對五大硬性摩擦訊號
依據 `session-trace` 輸出（或 Tier 3 逆向審訊表），逐一盤點：
1. **`MULTI_EDIT_CHURN`（同檔多次修改震盪）**：同一檔案跨步驟重複修改 $\ge 2$ 次。
2. **`TOOL_MISS_AND_RETRY`（工具報錯與檢索空轉）**：CLI 非零退出碼、參數猜錯重試或連續 `knowledge-db search` $\ge 3$ 次。
3. **`SILENT_BACKPATCH`（未申報之跨階段暗中回補）**：後期階段回頭修改前期 `P01`~`P03` 規格卻未登記於 `changelog.md`（已合規登記之 `VALIDATED_BACKPROP` 不列為違規）。
4. **`GATE_BOUNCE`（驗證關卡退件）**：遭 `plan verify`、`dev check`、`dev test` 或 `contributes check` 攔截退回。
5. **`CONTEXT_WASTE`（無效上下文載入）**：同檔案區段重複讀取 $\ge 2$ 次，或未先執行 `knowledge-db search` 即連續原生翻讀 $\ge 4$ 個源碼檔。

### 步驟 3：A/B/C/D 四象限根因分類樹
針對每項摩擦訊號，對照事發當下之 `<thinking>` 摘要與已載入規範，嚴格歸入四象限之一：
- **Type A（提示詞／SOP 歧義或遺漏）**：已載入之 `SKILL.md`、模板或規範條文含糊矛盾。**行動**：指出具體檔案與段落標題，給出文字修改建議（可轉交 [`/skill-optimizer`](`__#{module://agents-workflow/assets/skills/skill-optimizer/SKILL.md}__`) 或 Revision 修訂）。
- **Type B（ACI 工具介面或檢索斷層）**：CLI `--help`、報錯提示不明確或索引涵蓋不足導致盲猜。**行動**：指出應強化之模組 CLI 提示或檢索空間。
- **Type C（任務本質的不可知探索）**：外部環境或底層邊界需實測方能確認。**行動**：標記為「健康試錯（Healthy Exploration）」，評估是否沉澱至 `__${workflow.docs://}__`。
- **Type D（模型注意力滑脫／規則未遵循）**：規範已明文記載但執行時遺漏。**行動**：評估是否將文字規則升級為 `verifier.py` / `checker.py` 靜態硬性攔截。

`__@{SESSION_AUDIT_STANDARDS}__`

### 步驟 4：輸出結構化自檢診斷卡（強制 End Turn）

```markdown
### 🔬 /SessionAudit 隱形摩擦與決策自檢報告
- **觀測層級與標的**：`[Tier 1+2 | Tier 2 | Tier 3]` / 計畫：`[plan_name 或 None]` / Telemetry：`[N]` 筆
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

- **切勿在自檢過程中順手改動源碼或計畫檔**：發現問題時僅允許在報告中提出具體 Diff 建議或詢問開發者是否透過 [`/todo`](`__#{module://agents-workflow/assets/skills/todo/SKILL.md}__`) 登記。
- **切勿將合規回寫誤判為暗中偷改**：若 `session-trace` 標記為 `VALIDATED_BACKPROP`，代表已在 `changelog.md` 或 `revision_log.md` 留有正式修訂紀錄，屬正常工程回寫。

