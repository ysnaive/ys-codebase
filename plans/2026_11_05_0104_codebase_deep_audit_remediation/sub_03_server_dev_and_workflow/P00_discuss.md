# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_server_dev_and_workflow  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Unknown  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：執行全倉深度審計分類型主計畫（`2026_11_05_0104_codebase_deep_audit_remediation`）之子計畫 `sub_03_server_dev_and_workflow`（常駐服務 server、開發工具鏈 dev 與工作流引擎 agents-workflow 審計問題修復）。
- **核心目標**：依據主計畫 `R01_codebase_deep_audit.md` 經盲眼反向查驗確認之問題清單與防回歸紅線，完成 `ys_codebase/source/server/、ys_codebase/source/dev/ 與 ys_codebase/source/agents-workflow/` 範圍內所有確認缺陷之無損修復與單元測試驗證。
- **既有組件復用與查重 (Reuse Discovery)**：復用目標模組既有鎖機制、快取結構與 `YSCBTestCase` 隔離沙盒測試框架。
- **邊界排除 (Explicitly Excluded)**：嚴格限制寫入範圍於 `ys_codebase/source/server/、ys_codebase/source/dev/ 與 ys_codebase/source/agents-workflow/`，不觸碰其他子計畫負責之模組目錄，且不修改 `R01_codebase_deep_audit.md` 已駁回之偽陽性項目。
- **架構影響範圍**：`ys_codebase/source/server/、ys_codebase/source/dev/ 與 ys_codebase/source/agents-workflow/` 及對應 `tests/` 測試案例。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `module:server` 握手容錯、串流異常回傳與 Windows UTF-8 編碼加固（`SRV-01`~`06`）**：於 `server/master.py:_read_handshake` 迴圈內對單行 `json.loads` 獨立包裹 `try...except ValueError: continue` 防止非 JSON 雜訊行終止握手執行緒；於 `server/worker.py:execute_task` 在 `with streamer:` 關閉前將未捕獲例外寫入 `stderr` 並傳入 `send_task_finish(error=err_text)`；於 `_spawn_worker_locked` 設定 `PYTHONIOENCODING=utf-8` 並於 `worker_main` 執行 `reconfigure`；補齊 `/api/dispatch` 請求體檢查、`touch_activity` 節流與 `realpath`/`normcase` 路徑比對。
- **[P00:DR-02] `module:dev` 沙盒平行跑測、環境變數還原與子進程超時接線（`DEV-02` 已於 `2026_11_04_1739/sub_01` 修畢；聚焦剩餘 `DEV-01`, `DEV-03`~`05`）**：配合 `sub_02` 之 `core.uri` TLS 化確保 `create_sandbox` 平行解壓零競態；於 `YSCBTestCase.tearDown` 採用差集還原 `os.environ`、於 `builder.py` 直接執行原子 `os.replace`；將 `run_subprocess_with_tree_timeout` 接線至 `case.py:run_cli` 與 `tester.py`；於 `checker.py:_check_custom_rules` 支援連字號與底線名稱雙向正規化。
- **[P00:DR-03] `module:agents-workflow` 向後相容轉譯與計畫工具鏈打磨（`AW-03` 已於 `2026_11_04_1739/sub_01` 拔除手動 `sys.path` 補丁並新增 `dev.checker` 零豁免 AST 守門；聚焦剩餘 `AW-01`~`02`, `AW-04`~`06`）**：於 `compiler.py` 補回 `type: 'workflow' -> 'skill'` 自動轉譯並於 `publisher.py` 清理遺留目錄以對齊 `[DN-AW-05]`（嚴禁於非 `core` 模組寫入任何 `sys.path` 變動以免觸發 `_find_sys_path_mutations` FAIL）；於 `roadmap.py:promote_todos` 改為先寫入目標 `todo.md` 成功後再更新 `TODO.md`；於 `verifier.py:L228` 改用 `PlanStatusResolver.resolve_phase_file`；清理 `publisher.py` 未物化之 `agent_rules` 死分支、補齊 `cli.py:_normalize_bags` 空白分隔選項解析與 `session_trace.py` 單次掃描提取 `topic`。

---

## 3. 開放議題與確認紀錄

- **已確認事項**：子計畫範疇、防回歸紅線與修復方案已由主計畫 `R01_codebase_deep_audit.md` 定錨確認，可隨時啟動 Phase 01～07（或 `/auto`）推進實作。
