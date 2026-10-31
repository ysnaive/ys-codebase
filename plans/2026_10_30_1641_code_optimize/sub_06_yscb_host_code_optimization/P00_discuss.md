# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_06_yscb_host_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Research Plan  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對根目錄引導宿主 `yscb.py` 本體執行 `/code-optimizer`（`Mode A：收斂期 / 允許破壞性清理`），立項併入既有 `2026_10_30_1641_code_optimize` 主計畫，目前先不接續實作，僅撰寫 `R01` 靜態診斷調研報告後執行 `/pause`。
- **核心目標**：
  1. 以「單一檔案（`yscb.py`，793 LOC）及其跨模組/測試調用邊界（`ys_codebase/source/core/` 與 `ys_codebase/source/dev/`）」為檢視範圍，執行五維度靜態診斷（`D1~D5`）。
  2. 以「`Mode A：收斂期（Convergence Mode / 允許破壞性清理）`」為生命週期模式，盤點 `yscb.py` 內所有 0 調用死代碼、未引用匯入/全域常數、歷史遺留轉發殼層（`_suggest_command`、`_print_global_help`、`cmd_event`、`_ensure_jit_lifecycle_pre/post`、`cmd_restore`、`_restore_module_package`、`_generate_internal_gitignore`），並精確映射 `core/tests/` 內直接呼叫上述舊殼層之測試座標。
  3. 制定 `S1~S6` 外科手術無損重構處方箋（含共用 HTTP 讀取與 localhost 繞過提煉、`_discover_latest_core` 與 `cmd_self_update` 階段拆解），落檔於 [`R01_code_optimization_audit.md`](./R01_code_optimization_audit.md)，並執行 `/pause` 生成 [`handoff.md`](./handoff.md) 凍結上下文。
- **邊界排除 (Explicitly Excluded)**：
  - 本階段僅完成 `sub_06` 立項、`R01_code_optimization_audit.md` 撰寫與 `/pause` 現場交接快照，暫不直接修改 `yscb.py` 或 `ys_codebase/source/core/tests/` 代碼。
- **架構影響範圍**：
  - 調研診斷標的：`yscb.py`（793 LOC）。
  - 入向調用與測試遷移盤點範圍：`ys_codebase/source/core/tests/test_cli_router.py`、`test_core_commands.py`、`test_events_pipeline.py`、`test_distribution_lifecycle.py`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 檢視範圍與生命週期定錨（`File Scope` × `Mode A`）**：
  - 範圍鎖定根目錄微核心引導宿主 `yscb.py`（793 LOC），嚴格對齊 `docs/core/cli_commands_architecture.md`（`DN-21`）定義之三大職責：冷啟動自舉命令（`init`、`self-update`）、運行環境探測與安全令牌注入（`YSCB_HOST_DISPATCH_TOKEN`、`.modules/` 路徑隔離）、Fresh Clone 自癒（`_auto_bootstrap_and_restore_if_needed`）與全權委派 `core.commands.dispatch`。
  - 生命週期鎖定 `Mode A（收斂期 / 允許破壞性清理）`：對 `yscb.py` 內 0 調用死常數/匯入及 8 個僅供舊測試呼叫的轉發殼層採零容忍清除策略，後續實作時同步將 `core/tests/` 測試案例對齊至 `core.commands.dispatcher` 與 `core.installer.Installer` 權威入口。
- **[P00:DR-02] 暫停交接節點定錨（`R01` 落檔後 `/pause`）**：
  - 依開發者指示，完成 `sub_06` 立項與 `R01_code_optimization_audit.md` 落檔後，不進入代碼實作，直接執行 `/pause` 於 `sub_06_yscb_host_code_optimization/handoff.md` 固化完整行號座標與下一步重啟指引。

---

## 3. 開放議題與確認紀錄

- 已完成 `P00_discuss.md` 與 `R01_code_optimization_audit.md` 落檔並執行 `/pause` 凍結，待下次 `/continue` 時裁決原地升級為 `Fast Track` 或 `Full Track` 執行 `yscb.py` 與 `core/tests/` 同步重構。

