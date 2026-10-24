# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_02_dev_toolchain_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：基礎契約與延遲載入 — `contributes/core.json` 補齊 `test/op-test/op-mksb` 選項契約與 `events` 宣告；`dev/__init__.py` 實作 PEP 562 延遲載入與匯出 `Releaser` (`D-01`, `D-08`)
- [x] **TASK-02**：CLI 選項轉譯與測試引擎加固 — `scripts/cli.py` 正規化帶值選項；`tester.py` 組裝單一 Token `--pattern=<pat>`，落實 `UNKNOWN > 0` 剛性阻斷與統計扣除；`runner.py` 保留 `_FailedTest` 並納入 `NETWORK` 預設發現 (`D-01`, `D-03`)
- [x] **TASK-03**：發布流水線加固 — `releaser.py` Gate 3 全庫最高版本防回退、字母序穩定 DAG 阻斷、`release_git` 錯誤攔截；`cli.py:release_check` 支援預設全模組 (`D-02`)
- [x] **TASK-04**：檢核器修復與腳手架/沙盒現代化 — `checker.py` 自訂規則運行時隔離、源碼 Schema 優先讀取與 CLI 對稱性檢核；`scaffold.py`、`sandbox.py`、`case.py`、`builder.py` 汰除 `process(args)`、修正 SemVer 排序、還原 CWD 與 `clean` 參數修復 (`D-04`, `D-05`, `D-06`)
- [x] **TASK-05**：測試集收斂 10 檔 $\rightarrow$ 7 檔與補盲 — 裁撤 3 個碎片檔，重寫 5 處虛假測試，消滅暫存洩漏，並於 7 個主測試檔補齊 `D-01`~`D-08` 五大回歸路徑 (`DT-01`~`DT-05`)
- [x] **TASK-DOC**：三層文檔與手冊同步 — 更新 `assets/skills/yscb-module-dev/references/cli_and_commands.md`、`docs/dev/README.md`、`docs/dev/DESIGN_NOTES.md` 與 `contributes/_manifest.md` (`D-07`)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | 100% 依 P04 規劃之拓撲順序進行實作 |
