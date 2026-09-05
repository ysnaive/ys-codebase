# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_jit_self_healing_integration  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `core.events.broadcast` 成功尋址 `module://{mod}/scripts/hook.{Sender}.py` 並執行 `on_{event}` / `{event}` 函式 | FR-01 | `python yscb.py dev test core -k test_core_events_broadcast_basic` |
| **FT-02** | 單元測試 | 驗證 `Engine.act_broadcast_event` 已徹底移除，`installer.py` 與 `engine.py` 調用 `core.events.broadcast` 正常派送事件 | FR-01 | `python yscb.py dev test core -k test_engine_decoupling_and_installer_events` |
| **FT-03** | 單元測試 | 驗證 `yscb.py` 分發命令時依序執行微環境檢查、`pre_cli_dispatch` 廣播、模組分發與 `post_cli_dispatch` 廣播生命週期 | FR-02 | `python yscb.py dev test core -k test_yscb_host_lifecycle_pipeline` |
| **FT-04** | 整合測試 | 驗證 `agents-workflow` 的 `hook.core.py::on_pre_cli_dispatch` 能在來源指紋變更時成功調用 `ensure_jit_release()`，一致時極速短路跳過 | FR-03 | `python yscb.py dev test agents-workflow -k test_agents_workflow_hook_jit_release` |
| **FT-05** | 靜態檢核 | 驗證 `agents_workflow/scripts/cli.py` 已徹底移除 Ad-hoc `ensure_jit_release` 調用，但透過 `yscb.py` 執行時仍能自動完成 JIT 自癒 | FR-03 | `python yscb.py dev test agents-workflow -k test_agents_workflow_cli_adhoc_removal` |
| **FT-06** | 整合測試 | 驗證 `dev.testing.sandbox` 移除自建函式後，透過 `core.events.broadcast(..., emit_module="dev")` 成功觸發 `hook.dev.py` 之 `on_test_setup` | FR-04 | `python yscb.py dev test dev -k test_dev_sandbox_hook_convergence` |
| **FT-07** | CLI 測試 | 驗證 `python yscb.py event list` 能正確聚合各模組之 `contributes.events` 中繼資料並格式化輸出事件清冊 | FR-05 | `python yscb.py dev test core -k test_event_list_cli` |
| **FT-08** | 整合測試 | 驗證 `core.contributes` JIT 快照自癒與生命週期管線協同無衝突，維持雙層防護 | FR-06 | `python yscb.py dev test core -k test_contributes_jit_coordination` |
| **ET-01** | 邊界測試 | 驗證缺少 `hook.<Sender>.py` 或未宣告對應事件處理常式之模組安全略過，不拋出任何例外 | EC-01 | `python yscb.py dev test core -k test_hook_missing_graceful_skip` |
| **ET-02** | 邊界測試 | 驗證特定模組 Hook 內部拋出例外時，事件總線捕獲並記錄警告，絕不阻斷主 CLI 命令執行 | EC-02 | `python yscb.py dev test core -k test_hook_exception_isolation` |
| **ET-03** | 邊界測試 | 驗證執行 `init`、`restore`、`bootstrap` 等自舉指令時自動短路跳過前置廣播 | EC-03 | `python yscb.py dev test core -k test_bootstrap_commands_short_circuit` |
| **ET-04** | 效能測試 | 驗證 Clean（無變更）狀態下全套 `pre_cli_dispatch` 生命週期廣播與嗅探總體耗時 $\le 5\text{ms}$ | EC-04, NFR-01 | `python yscb.py dev test core -k test_clean_state_performance_benchmark` |
| **ET-05** | 邊界測試 | 驗證未定義 `events` contribute 節點之模組在執行 `event list` 時優雅容錯不拋異常 | EC-05 | `python yscb.py dev test core -k test_event_list_empty_contributes_resilience` |
| **RT-01** | 全量回歸 | 全生態系現有測試回歸，確保全模組單元測試 100% 通過 | NFR-02 | `python yscb.py dev test --all -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core.events.broadcast` 成功尋址 `module://mock_listener/scripts/hook.core.py` 並精確觸發 `on_pre_cli_dispatch` 與 `custom_event` | 2026-09-04 07:58 |
| **FT-02** | `Passed` | 嚴格斷言 `AtomicEngine.act_broadcast_event` 門面徹底移除；`engine.act_reload` 與 `installer.cmd_remove` 正常調用 `core.events.broadcast` | 2026-09-04 08:02 |
| **FT-03** | `Passed` | 驗證 `yscb.py` 前置與後置生命週期管線均依序廣播 `pre_cli_dispatch` 與 `post_cli_dispatch` | 2026-09-04 08:02 |
| **FT-04** | `Passed` | 驗證 `agents-workflow/scripts/hook.core.py` 導出 `on_pre_cli_dispatch` 並正確調用 `ensure_jit_release()` | 2026-09-04 07:57 |
| **FT-05** | `Passed` | 驗證 `agents-workflow/scripts/cli.py` 原始碼已徹底剔除 Ad-hoc `ensure_jit_release()` 呼叫 | 2026-09-04 07:57 |
| **FT-06** | `Passed` | 驗證 `dev.testing.sandbox` 移除 `_dispatch_test_hooks` 後，成功透過 `core.events.broadcast(..., emit_module="dev")` 觸發 `hook.dev.py` | 2026-09-04 07:57 |
| **FT-07** | `Passed` | 驗證 `python yscb.py event list` CLI 成功聚合並格式化輸出各模組註冊之事件清冊 | 2026-09-04 08:02 |
| **FT-08** | `Passed` | 驗證 `core.contributes` 與 `events.get_contributed_events()` 協同運作正常，事件清冊完整呈現 | 2026-09-04 08:02 |
| **ET-01** | `Passed` | 模組缺失 `hook.<Sender>.py` 或無對應處理常式時，事件總線安全略過且無任何未捕獲例外 | 2026-09-04 08:02 |
| **ET-02** | `Passed` | 模組 Hook 內部拋出例外時，總線捕獲並記錄警告，結果標記為 `warning:`，完全隔離不阻斷主流程 | 2026-09-04 08:02 |
| **ET-03** | `Passed` | 自舉命令（`init`, `restore`, `bootstrap`, `self-update`）自動短路跳過前置廣播，零副作用 | 2026-09-04 08:02 |
| **ET-04** | `Passed` | Clean 狀態下全套 `pre_cli_dispatch` 生命週期廣播與嗅探總體耗時 < 5ms (平均延遲 < 0.5ms) | 2026-09-04 08:02 |
| **ET-05** | `Passed` | 當模組或系統未宣告 `events` 擴充節點時，`get_contributed_events()` 穩健返回空字典 | 2026-09-04 08:02 |
| **RT-01** | `Passed` | 全生態系現有測試回歸 `python yscb.py dev test --all -q`：Pass: 384(100.0%), Fail: 0, Skip: 0 | 2026-09-04 08:02 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：[開發者指示免測] 實機修改 `config/agents-workflow/snippets/header.md` 內容，不手動執行任何 reload/release，直接呼叫 `python yscb.py agents-workflow plan status`，確認由宿主 `pre_cli_dispatch` 事件管線驅動之 JIT 自癒物化成功生效，且終端輸出維持毫秒級流暢體驗。
- [x] **UX-02**：[開發者指示免測] 實機調用 `python yscb.py event list`，確認終端格式化呈現全生態系可派送事件中繼資料清單。
