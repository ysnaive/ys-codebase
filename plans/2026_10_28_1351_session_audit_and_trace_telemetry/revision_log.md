# 修訂紀錄書 (Revision Log)

> 功能名稱：Session 隱形摩擦自檢技能 (`/session-audit`) 與三級軌跡提取引擎 (`session-trace`)  
> 建立日期：2026-10-28  
> 所屬主計畫：2026_10_28_1351_session_audit_and_trace_telemetry  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] 移除 `/session-audit` 未來視題庫收割敘述並擴充 `session-trace` 全維度會話基礎常數與 Token 統計
- **修訂類別**：DX / Docs
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/assets/skills/session-audit/SKILL.md`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py`
  - `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`
  - `docs/agents-workflow/user_guide.md`
- **修訂摘要**：
  - 移除 `session-audit/SKILL.md` 中尚未落地之未來視「題庫收割評估 (`[Harvest Candidate]`)」欄位，收斂為現有體系已具備之「後續收斂建議」（對接 `/skill-optimizer`、`/todo` 與修訂計畫），並於步驟 4 診斷卡新增「會話基礎統計 (Session Metrics)」呈現區塊。
  - 於 `session_trace.py` (`SessionTraceReport.session_stats`) 實作三大維度基礎常數與 Token 統計回報：
    1. `tokens`：`estimated_full_tokens`（自動補償同目錄 `transcript_full.jsonl` 截斷差額）、`estimated_compact_tokens`、`by_category`（`user_input`、`model_output`、`thinking`、`tool_call_args`、`tool_outputs`）、`reported_api_usage`（原生 `usage` 欄位）與日誌體積 KB。
    2. `steps_and_tools`：`total_steps`、`user_turns`、`model_turns`、`thinking_steps`、`truncated_steps`、`error_steps`、`total_tool_calls`、`tool_distribution`、`subagent_calls`、讀改檔次數與不重複檔案數（並剝除路徑多餘外層引號）。
    3. `time_and_cli`：`session_duration_sec` / `session_duration_human`、`cli_total_calls`、`cli_failed_calls`、`cli_total_duration_ms`、`cli_avg_duration_ms`、`cli_by_mode`（`hot`/`local`）與 `cli_by_module`。
- **驗證結果**：
  - `python yscb.py dev check agents-workflow`：`PASSED`。
  - `python yscb.py dev test agents-workflow -q`：`Pass: 134(100.0%), Fail: 0, Skip: 0`（含 `test_ft_15` 對 `session_stats` 全欄位之正負向斷言）。
  - 實機運行 `python yscb.py agents-workflow session-trace` 成功輸出 `Session Baseline Metrics` 與 `--json` 統計結構。

---

### [REV-02] 實戰盲審回饋收斂：新增 `--list` 歷史對話清單、頭中尾工作區主導探測與 Subagent 過濾、Telemetry 時間窗上界鎖定及模板路徑標示強化
- **修訂類別**：UI/UX/DX / Docs
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py`
  - `ys_codebase/source/agents-workflow/scripts/cli.py`
  - `ys_codebase/source/agents-workflow/contributes/core.json`
  - `ys_codebase/source/agents-workflow/assets/skills/session-audit/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/pause/SKILL.md`
  - `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`
  - `docs/agents-workflow/user_guide.md`
- **修訂摘要**：
  - **新增 `session-trace --list [--all]` 歷史清單**：支援列出本工作區可抓取之歷史主對話（顯示 Session ID、UTC 時間、步數與使用者回合數、完整 Token 估算、摩擦訊號數與首發需求主題），預設自動排除無 `USER_INPUT` 之 Subagent 與其他工作區對話；搭配 `--all` 可檢視全機紀錄。
  - **頭中尾三段切片與主導工作區指紋判定**：`_inspect_candidate_beacon` 擴充讀取頭/中/尾各 64KB，並統計 `/workspace/<proj>` 出現頻次判定主導工作區（`detected_workspace`），徹底解決長對話頭尾漏判與跨專案文字提及誤綁定；同時自動識別首筆 `<SYSTEM_MESSAGE>` 且 0 `USER_INPUT` 之 Subagent。
  - **歷史與跨專案時間窗上界保護 (`until_iso`)**：`_analyze_telemetry()` 新增 `until_iso` 上界過濾（`last_ts + 60s`），分析歷史或外部工作區 Transcript 時嚴格隔離非該時間窗/非本工作區之 Telemetry 與活躍計畫。
  - **摩擦訊號去噪與語言擴充**：同一步驟 (`step_no`) 對同檔案的多區塊編輯合併計為單次修改；檔案被編輯後重置該檔 `read_counts`（避免改後重讀確認被誤判為 `CONTEXT_WASTE`），排除圖片/媒體檔重複讀取，並擴充 `.cs`, `.java`, `.kt`, `.tsx` 等源碼副檔名監測。
  - **消除模板相對路徑拼接歧義**：於 `development-sop/SKILL.md` §6 與 `pause/SKILL.md` 明確標註工作區根目錄視角路徑 `.agents/.yscb/templates/<檔名>`。
- **驗證結果**：
  - `python yscb.py contributes check`：`15/15 valid`。
  - `python yscb.py dev check agents-workflow`：`PASSED`。
  - `python yscb.py dev test agents-workflow -q`：`134/134 (100.0%)`。
  - 實機執行 `python yscb.py agents-workflow session-trace --list` 精準列出本倉歷史主對話並排除跨專案與 Subagent 雜訊。

---

### [REV-03] 歷史 Session `84facb53` 盲審回饋收斂與 Claude Code / OpenAI Codex 異質 `.jsonl` 完整相容
- **修訂類別**：UI/UX/DX / Docs
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py`
  - `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md`
  - `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`
- **修訂摘要**：
  - **舊版 `view_file` 參數 `AbsolutePath` 相容與 `changelog.md` 豁免**：於 `_parse_transcript_file` 補齊 `t_args.get("AbsolutePath")`、`StartLineNumber`/`EndLineNumber` 映射（修復舊版對話 `total_read_ops: 0` 盲區），並於 `MULTI_EDIT_CHURN` 豁免合規逐階段追加之 `changelog.md`。
  - **`AgentsStandards.md` 語意路徑佔位符化**：將第 2 節底部硬編碼 `config/agents-workflow/contribute.json` 改為 `` `__${config://agents-workflow}__/contribute.json` ``（於母倉自動展開為 `ys_codebase/config/agents-workflow/contribute.json`）。
  - **Claude Code 與 OpenAI Codex 異質 `.jsonl` 全欄位動態相容**：
    1. **Claude Code (`~/.claude/projects/**/*.jsonl`)**：完整支援 `message.content[]` 之 `thinking`、`tool_use` (`input`)、`tool_result` (`is_error: true` 錯誤提取與輸出 Token 估算) 及 `message.usage` (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`)。
    2. **OpenAI Codex (`~/.codex/sessions/**/*.jsonl`)**：完整支援頂層與 `payload` 封裝層之 `function_call` / `custom_tool_call`（自動 `json.loads` 字串型 `arguments`）、`reasoning` (`summary[].text`)、`input_text`/`output_text` 與 `usage`。
- **驗證結果**：
  - `python yscb.py dev check agents-workflow`：`PASSED`。
  - `python yscb.py dev test agents-workflow -q`：`134/134 (100.0%)`（新增 Claude Code / Codex 格式與 `AbsolutePath` / `changelog.md` 豁免斷言）。

---

### [REV-04] 跨 8 份歷史對話盲審實證收斂：`session-trace` 5 項精準度修正與核心 Skill 通用型防呆微調
- **修訂類別**：UI/UX/DX / Docs
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py`
  - `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`
  - `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md`
  - `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/testing-sop/references/test_suite_audit_and_purification.md`
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md`
- **修訂摘要**：
  - **`session-trace` 5 項精準度修正 (`session_trace.py`)**：
    1. **`GENERIC` 工具回傳步驟與 `PLANNER_RESPONSE` 分流及頂層 Token 相容**：修正 Antigravity `source == "MODEL"` 且 `type == "GENERIC"` 之工具回傳步驟被計入 `model_turns`/`tok_model` 的偏差，將其歸入 `tok_tool_out`；並支援頂層 `input_tokens`/`output_tokens`/`cache_read_tokens` 欄位。
    2. **`read_key` 納入 `ByteOffset` 分段位移**：大檔分段讀取（>46KB 帶 `ByteOffset`）不再被誤判為 `CONTEXT_WASTE` 同區段重複讀取。
    3. **失敗讀檔排除於 `read_counts` 之外**：當讀檔工具返回 `ERROR`（如檔案不存在）時，自動回滾該步驟之 `read_key` 計數，避免單純路徑盲猜失敗被雙重誤判為 `CONTEXT_WASTE` 重複讀取。
    4. **合規多階段生命週期文件之 `MULTI_EDIT_CHURN` 豁免**：將 `revision_log.md` 與 `umbrella_overview.md` 納入豁免清單；並將 `P00_discuss.md`、`P06_test_plan.md`、`fast_track_plan.md` 之震盪閾值放寬為非連續回合 $\ge 4$ 次或總修改 $\ge 5$ 次，消除合規階段流轉之假陽性。
    5. **無 Telemetry 歷史/外部對話之 Transcript CLI 與 `GATE_BOUNCE` 自動回填**：當 `telem_count == 0` 時，自動從 Transcript 內含 `yscb.py` 之終端指令提取 CLI 呼叫次數、模組分佈與關卡退件 (`GATE_BOUNCE`) 訊號。
  - **核心 Skill 通用型防呆微調 (`[Type A]`)**：
    1. [`auto/SKILL.md`](../../ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md)：增補「同對話跨子計畫模板免重讀豁免 (`Same-Session Template Cache Reuse`)」，同一 Session 連續推進 Umbrella 多個 `sub_XX` 子計畫且未發生 Context Compaction 時免重複重讀模板。
    2. [`knowledge-db-search/SKILL.md`](../../ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md)：以跨語言通用型敘述增補「嚴禁憑模組／命名空間（Namespace / Package）階層或命名慣例盲猜實體路徑直接讀檔」及「非索引資源檔（Non-Code/MD Assets）定位防呆（先查引用符號或單次目錄列舉，嚴禁讀檔盲猜窮舉）」。
    3. [`how-to-config-yscb/SKILL.md`](../../ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md)：明確標註首次配置前 `contribute.json` 與 `snippets/` 屬選配項（先檢查是否存在，勿盲目 `read_file` 報錯），且三步驗證 `[PASS]` 後免重讀物化產物全文。
    4. [`test_suite_audit_and_purification.md`](../../ys_codebase/source/agents-workflow/assets/skills/testing-sop/references/test_suite_audit_and_purification.md)、[`development-sop/SKILL.md`](../../ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md)、[`yscb-cli-guide/SKILL.md`](../../ys_codebase/source/agents-workflow/assets/skills/yscb-cli-guide/SKILL.md)：明定 `T-02` 須同步執行「檔案級 1:1 歸戶」與「方法級內聚整併」；標註 `plan verify --phase <P0X>` 僅限 Full Track 單階段檢核；標註 `server` 子命令為 `start / stop / status / reload`（無 `restart`）。
- **驗證結果**：
  - `python yscb.py dev check knowledge-db` & `dev test knowledge-db -q`：`PASSED` (100%)。
  - `python yscb.py dev check agents-workflow` & `dev test agents-workflow -q`：`PASSED` (`134/134`, 100%)。

---

### [REV-05] 實作無推估鐵證聯集解析、有效 vs. 無效 Token 效益分析 (`token_efficiency`) 與三維高耗能排行 (`top_consumers`)
- **修訂類別**：UI/UX/DX / Docs
- **涉及檔案**：
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py`
  - `ys_codebase/source/agents-workflow/assets/skills/session-audit/SKILL.md`
  - `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`
- **修訂摘要**：
  1. **`transcript_full.jsonl` 截斷行定點聯集與零臆測鐵律 (`Zero-Speculation Autopsy`)**：
     - `_parse_transcript_file` 偵測到 `truncated_fields` 時，自動從同目錄 `transcript_full.jsonl` 同步讀取完整 JSON 對象取代截斷行，直接計算 100% 真实未截斷之參數、輸出與思考鏈 Token（`exact_full_parsed: true`）。
     - 於 `session-audit/SKILL.md` §1 新增「無鐵證不歸因，嚴禁推估語句」紅線，禁止報告出現「推測、可能、大概、估計」等模糊詞彙，強制綁定 `Step #` 與具體日誌證據。
  2. **有效 Token vs. 無效（摩擦浪費）Token 確定性拆解 (`token_efficiency`)**：
     - 量化計算 `effective_tokens` (`efficiency_pct%`) 與 `wasted_tokens` (`waste_pct%`)，並拆解四大浪費來源 (`wasted_breakdown`)：
       - `duplicate_reads`：同一檔案區段未修改下第 $2 \dots K$ 次重複讀取之參數與輸出 Token。
       - `failed_tool_steps`：返回 `ERROR` / `is_error=True` 或關卡退件 (`GATE_BOUNCE`) 步驟所消耗之思考鏈、工具參數與錯誤輸出 Token。
       - `edit_churn_rework`：觸發 `MULTI_EDIT_CHURN` 檔案扣除首尾定稿後，中間返工覆寫步驟消耗之參數 Token。
       - `unindexed_blind_reads`：未呼叫 `knowledge-db` 連續盲讀 $\ge 4$ 個源碼檔時，超額盲讀步驟之參數與輸出 Token。
  3. **三維高耗能操作與 CLI 指令排行榜 (`top_consumers`)**：
     - `by_tool`：各工具累計消耗之 `args_tokens`、`output_tokens`、`total_tokens`、單次平均 `avg_tokens` 與佔總量百分比 `share_pct`。
     - `heavy_steps`：單步吞吐量最高之前 5 大步驟（含 `Step #`、工具名稱、目標檔案/指令、消耗 Token 與截斷標記）。
     - `heavy_cli_commands`：消耗最多 Token 之前 5 大具體終端 CLI 指令字串（含 `Step #`、`command`、`tokens`、`output_tokens`、`is_error`）。
- **驗證結果**：
  - `python yscb.py dev check agents-workflow` & `dev test agents-workflow -q`：`PASSED` (`134/134`, 100%)。
  - `python yscb.py agents-workflow plan verify`：`PASSED`。

---

### [REV-06] 上下游雙向實證合併收斂：`knowledge-db` 二階段漏斗與 40 行切片截斷保護、`handoff.md` 上下文交接壓縮區塊、以及跨宿主通用敘述與 `session-trace` 精準讀檔豁免
- **修訂類別**：UI/UX/DX / Docs
- **涉及檔案**：
  - `ys_codebase/source/knowledge-db/scripts/cli.py`
  - `ys_codebase/source/knowledge-db/contributes/core.json`
  - `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/templates/handoff.md`
  - `ys_codebase/source/agents-workflow/assets/skills/pause/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/references/phase_02_architecture.md`
  - `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py`
  - `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py`
- **修訂摘要**：
  1. **`knowledge-db` 切片溢位截斷保護 (`--max-snippet-lines=40`) 與二階段漏斗模型 (`Two-Stage Funnel Retrieval`)**：
     - 於 `knowledge-db/scripts/cli.py` 及 `contributes/core.json` 新增 `--max-snippet-lines`（預設 `40` 行），當 `search --json -s` 命中大型類別時自動截斷並輸出跨宿主通用提示 `use native file reader with line range to view`；同時將 `search --json -s` 之 `auto` 預設筆數上限收斂為 Top `10`，徹底消滅單步 50~90KB JSON 切片溢位。
     - 重構 [`knowledge-db-search/SKILL.md`](../../ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md)：廢除「探索一律帶 `--json -s`」，改為 **Stage 1（無 `-s` 輕量大綱定位：`search --limit=10 --json`）$\rightarrow$ Stage 2（以各環境之原生檔案讀取工具指定起訖行號定點精讀）**；並明定單次命令列最多串接 2~3 個無 `-s` 查詢，且**嚴禁調用原生檔案讀取工具讀取宿主環境之超長輸出截斷暫存檔**。
  2. **`handoff.md` 新增 `## 4. 上下文交接 (Compressed Task Context)` 區塊**：
     - 於 [`handoff.md`](../../ys_codebase/source/agents-workflow/assets/templates/handoff.md) 模板與 [`pause/SKILL.md`](../../ys_codebase/source/agents-workflow/assets/skills/pause/SKILL.md) 正式增設「上下文交接」區塊，要求將當前對話中已定案之具體拆解清單、子系統歸戶映射表、關鍵決策與檔案行號座標進行**高密度資訊壓縮**後寫入，杜絕接手或 Compaction 後翻讀會話歷史日誌檔考古（單次可省逾 4.5 萬 Tokens）。
  3. **全面對齊跨宿主通用性敘述 (`Host-Agnostic Phrasing`) 與 `callers` 強制守門**：
     - 將各 Skill 與 CLI 提示中之 `read_file`/`view_file`/`write_file` 統一替換為「各環境之原生檔案讀取／覆寫工具（指定起訖行號區段）」。
     - 於 [`phase_02_architecture.md`](../../ys_codebase/source/agents-workflow/assets/skills/development-sop/references/phase_02_architecture.md) 與 [`auto/SKILL.md`](../../ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md) 增設「破壞性公開 API 簽名變更強制執行 `knowledge-db callers` 守門」與「批次 A 讀模板後嚴禁穿插源碼讀取以防 Compaction 洗記憶」。
  4. **`session-trace` 啟發式判準升級 (`session_trace.py`)**：
     - **豁免二階段漏斗之定點行號讀取**：執行 `knowledge-db` 定位後，對跨度 $\le 160$ 行區段之原生檔案讀取不計入 `unindexed_blind_reads`。
     - **新增 `JSON_SNIPPET_OVERFLOW` 子類偵測**：自動捕捉讀取宿主截斷暫存檔（如 `steps/*/output.txt`、`tool-results`）或會話歷史日誌檔（`transcript_full.jsonl`）之高耗能行為並計入 `wasted_tokens`。
- **驗證結果**：
  - `python yscb.py contributes check`：`15/15 valid`。
  - `python yscb.py dev check knowledge-db` & `dev test knowledge-db -q`：`PASSED` (`150/150`, 100%)。
  - `python yscb.py dev check agents-workflow` & `dev test agents-workflow -q`：`PASSED` (`134/134`, 100%)。
  - `python yscb.py agents-workflow plan verify`：`PASSED`。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 docs/ 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 CHANGELOG.md。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
