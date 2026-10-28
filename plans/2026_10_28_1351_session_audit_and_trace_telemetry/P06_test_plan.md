# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 建立日期：2026-10-28  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core/telemetry.py` 寫入與讀取 `cache://core/telemetry.jsonl`（含 `ts`, `module`, `cmd`, `args`, `exit_code`, `duration_ms`, `mode`, `error_hint`），且 `dispatcher.dispatch` 正常與失敗路由均正確落盤。 | FR-01, NFR-01 | `python yscb.py dev test core -k test_ft_11_telemetry_flight_recorder_and_sandbox_isolation` |
| **FT-02** | 單元測試 | 驗證 `SessionTraceEngine.locate_transcript` 多宿主三層信標定錨：支援顯式 `--transcript`，並以「工作區路徑指紋 + 尾行 `session-trace` 信標」精準鎖定主視窗、排除唯讀 Reviewer Subagent。 | FR-02 | `python yscb.py dev test agents-workflow -k test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` |
| **FT-03** | 單元測試 | 驗證 `SessionTraceEngine.audit_plan_mtimes` 跨階段 `mtime` 逆序消歧：未在 `changelog.md` 申報之逆序修改標記為 `SILENT_BACKPATCH`，有 `REVISION`/`DECISION` 紀錄則轉為 `VALIDATED_BACKPROP`。 | FR-03 | `python yscb.py dev test agents-workflow -k test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` |
| **FT-04** | 單元測試 | 驗證 `SessionTraceEngine.analyze` 自動偵測並聚合五大硬性摩擦訊號（`MULTI_EDIT_CHURN`, `TOOL_MISS_AND_RETRY`, `SILENT_BACKPATCH`, `GATE_BOUNCE`, `CONTEXT_WASTE`）及 `<thinking>` 截斷摘要。 | FR-04, NFR-02 | `python yscb.py dev test agents-workflow -k test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` |
| **FT-05** | 單元與整合測試 | 驗證 `agents-workflow session-trace` CLI 契約、`/session-audit` 技能導出、23 個 Stage 1 Token 錨點地圖與 `ArtifactCompiler` Stage 1/2 編譯零警告。 | FR-05, NFR-02 | `python yscb.py dev test agents-workflow -q` |
| **ET-01** | 邊界測試 | 驗證當移除尾行自指信標且存在多份匹配工作區之 `.jsonl` 時，拒絕盲猜並回傳 `transcript_candidates` 候選清單，同時自動降級輸出 Tier 2 結果。 | EC-01 | `python yscb.py dev test agents-workflow -k test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` |
| **ET-02** | 邊界測試 | 驗證 0 活躍計畫時自動探測 `workflow.archived://` 下最近 30 分鐘內剛歸檔之計畫，且傳入不存在之 `--plan` 時返回非 0 錯誤碼 (`exit_code == 1`)。 | EC-02 | `python yscb.py dev test agents-workflow -k test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` |
| **ET-03** | 邊界測試 | 驗證 `should_record_telemetry` 在沙盒測試 (`YSCB_TEST_SANDBOX == "1"`)、`-h`/`--help` 查詢與 `session-trace` 自身呼叫時自動旁路略過，不污染宿主快取。 | EC-03 | `python yscb.py dev test core -k test_ft_11_telemetry_flight_recorder_and_sandbox_isolation` |
| **ET-04** | 邊界測試 | 驗證 `telemetry.jsonl` 超過 `max_bytes` 時自動滾動截斷保留最新 `keep_lines` 筆紀錄，且寫入目標為無效目錄時靜默吞除 I/O 異常不中斷 CLI。 | EC-04 | `python yscb.py dev test core -k test_ft_11_telemetry_flight_recorder_and_sandbox_isolation` |
| **ET-05** | 邊界測試 | 驗證 `.jsonl` 含損毀 JSON 行時自動容錯跳過不崩潰，以及 `AtomicEngine._atomic_swap_dir` 自動清掃殘留 `.old_*` 與 `.staging_*` 目錄。 | EC-05 | `python yscb.py dev test core -k test_atomic_swap_dir_cleans_stale_old_and_staging_remnants` |
| **RT-01** | 全量回歸測試 | 執行 `core`、`dev` 與 `agents-workflow` 三大受影響模組全量沙盒測試與 `contributes check` 靜態契約檢查。 | 全域回歸 | `python yscb.py dev test core -q` / `dev test dev -q` / `dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCLIRouter.test_ft_11_telemetry_flight_recorder_and_sandbox_isolation` 通過，驗證正常與失敗派發紀錄落盤與欄位完整性。 | 2026-10-28 15:12 |
| **FT-02** | `Passed` | `TestPlansModelRecord.test_ft_15_session_trace_beacon_anchoring_and_five_friction_signals` 通過，精準鎖定主視窗 `transcript.jsonl` 並排除 Subagent。 | 2026-10-28 15:18 |
| **FT-03** | `Passed` | 同上測試通過，驗證 `SILENT_BACKPATCH` 與補登 `REVISION` 後轉為 `VALIDATED_BACKPROP` 之消歧邏輯。 | 2026-10-28 15:18 |
| **FT-04** | `Passed` | 同上測試通過，五大摩擦訊號全數命中且 `<thinking>` 摘要正確擷取截斷。 | 2026-10-28 15:18 |
| **FT-05** | `Passed` | `TestWorkflowAssetsCompliance` 通過，18 個內建純 Skill 與 23 個 Stage 1 Token 錨點編譯 0 warning / 0 error。 | 2026-10-28 15:18 |
| **ET-01** | `Passed` | 多份無尾行信標之 `.jsonl` 測試返回 `locked_none is None` 且 `len(cands) == 2`。 | 2026-10-28 15:18 |
| **ET-02** | `Passed` | 剛歸檔計畫自動探測命中 `[Auto-Resolved Recently Archived Plan]`；無效 `--plan` 返回 `rc == 1`。 | 2026-10-28 15:18 |
| **ET-03** | `Passed` | 沙盒預設旁路、`-h` 與 `session-trace` 自身呼叫均回傳 `False`。 | 2026-10-28 15:12 |
| **ET-04** | `Passed` | 滾動截斷精準保留最新 N 筆紀錄，無效路徑寫入回傳 `False` 且不拋出例外。 | 2026-10-28 15:12 |
| **ET-05** | `Passed` | 損毀 JSON 行安全略過；`TestCoreEngine.test_atomic_swap_dir_cleans_stale_old_and_staging_remnants` 通過。 | 2026-10-28 15:12 |
| **RT-01** | `Passed` | `core`: 195/195 (100% Passed)；`dev`: 79/79 (100% Passed)；`agents-workflow`: 134/134 (100% Passed)；`contributes check`: 15/15 files valid。 | 2026-10-28 15:18 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 於終端執行 `python yscb.py agents-workflow session-trace`（或加 `--json`），確認能自動定錨當前對話之 `transcript.jsonl`、串聯 `cache://core/telemetry.jsonl` 並輸出結構化摩擦訊號報告；以及確認 `.agents/skills/session-audit/SKILL.md` 已成功投影物化。 | `[測試通過]` | 開發者已驗收確認通過（2026-10-28） |

