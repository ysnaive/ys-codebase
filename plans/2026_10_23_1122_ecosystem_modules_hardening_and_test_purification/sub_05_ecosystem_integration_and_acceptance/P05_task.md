# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_05_ecosystem_integration_and_acceptance  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：核驗四大模組（`core`、`dev`、`server`、`knowledge-db`）`@build` 部署同步狀態、8 份已消費 Roadmap 儲備閉環歸檔與 43 支純化測試檔規模（`FR-04`, `FR-05`, `NFR-01`）
- [x] **TASK-02**：執行跨模組靜態合規檢查（`contributes check`、`dev check --all`）、全生態系沙盒回歸測試（`dev test --all -q`）與常駐 Server 託管／多層子命令熱派發端到端驗證（`FR-01`, `FR-02`, `FR-03`, `EC-01`~`EC-03`, `NFR-02`）
- [x] **TASK-DOC**：完成三層文檔最終對齊審計（`docs/`、源碼 `README.md`、`DESIGN_NOTES.md`），清理 `ys_codebase/source/server/README.md` 舊版殘留片段，確認全模組文檔與實作 100% 同步（`FR-05`）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-02** | Minor | 執行 `python yscb.py dev test --all -q` 時，`dev` 模組之 `TestDevTester.test_unknown_fails_tester_and_deducts_custom_passed` 因父進程設置環境變數 `YSCB_TEST_QUIET=1`，使內聯呼叫之 `_run_op_test` 誤進入 `quiet_mode` 導致摘要字串斷言不匹配 | 修正 `ys_codebase/source/dev/dev/tester.py` 之 `_run_op_test` 僅依自身 `argv` (`-q`/`--quiet`) 判定 `quiet_mode`（`quiet_mode = False` 預設），重新執行 `dev test dev -q --sync` 與 `dev test --all --no-build -q` 593/593 (100.0%) 全綠通過 |
| **TASK-DOC** | Minor | 審計 `ys_codebase/source/server/README.md` §2.2 時發現結尾殘留 8 行舊版 JSON 片段；另核對 `sub_01` 測試檔收斂映射表（28 檔刪除 7 檔 + 1 檔原地去重 = 21 檔），四大模組純化後測試檔精確總數為 `21 + 7 + 3 + 12 = 43` 檔 | 清理 `ys_codebase/source/server/README.md` 殘留片段，並同步校正 `P01`/`P04`/`P05`/`P06` 測試檔統計數據為 43 檔 |

