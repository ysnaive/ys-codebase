# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：合併落實 `core_microkernel_purification_and_cli_hardening.md`（`C-01` ～ `C-06`）與 `core_test_suite_purification_roadmap.md`（`T-01` ～ `T-06`），作為全生態系加固之第一棒基石。
- **核心目標**：
  1. 徹底清除 `core` 微內核對 `agents-workflow` 的歷史耦合殘留（`providers.py` 階段導引函式、`uri.py` 特例分支、`test_events_pipeline.py` 跨模組 `patch`）。
  2. 補齊 `contributes check` 對專案級 `config://<target>/contribute.json` 的單檔與全量 Schema 驗證（含自動剝殼與父目錄模組推導）。
  3. 修復 `dispatcher._try_hot_dispatch` 多層子命令路徑列表（`cmd_path: List[str]`）傳遞、打通 `list --remote` 與 `config list --local / inspect / unset`，並統一群組命令未知子命令攔截與 `HelpRenderer` 輸出。
  4. 將 `core/tests/` 由 28 個碎片測試檔收斂為 20 個子系統 1:1 對齊測試檔，消除死代碼 `print_global_help`、改寫 5 處虛假測試、補齊 `@require` 沙盒隔離與 `tearDown` 清理，並新增 4 大高風險路徑回歸測試。
- **邊界排除 (Explicitly Excluded)**：不修改上層業務模組（`dev`、`server`、`knowledge-db`、`agents-workflow`）之內部實作，維持 100% Python 標準庫零外部依賴。
- **架構影響範圍**：`ys_codebase/source/core/core/{providers.py,uri.py,contributes.py,installer.py}`、`core/commands/{contributes_cmd.py,dispatcher.py}`、`contributes/core.json`、`scripts/cli.py` 與 `tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **雙路線圖同步交付**：由於 `C-01`～`C-06` 與 `T-01`～`T-06` 高度重疊於同一批測試檔且新測試直接驗證新修復項，定調於同一子計畫同步完成。
- **[P00:DR-02]** **保護跨模組群組命令無參數預設行為 (`C-06`)**：`dispatcher.py` 步驟 8 移除 `has_fn` 繞過以統一攔截 `yscb uri checkk` 拼寫錯誤；步驟 7 保持 `if not has_fn:` 以保護 `agents-workflow plan/roadmap/todo` 無參數預設動作，並將 `core/scripts/cli.py` 四個群組函式內部無參數 fallback 改為呼叫 `HelpRenderer.render_cmd_help`。
- **[P00:DR-03]** **對齊 `dev check` 1:1 葉節點函式契約 (`C-05`)**：於 `core/scripts/cli.py` 明確定義 `def config_inspect(cmd_bags: CmdBags) -> int:` 與 `def config_unset(cmd_bags: CmdBags) -> int:`。

---

## 3. 開放議題與確認紀錄

- 規格與防呆邊界已於前置路線圖審查中 100% 確認收斂，狀態標記為 `Confirmed`。

