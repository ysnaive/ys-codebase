# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Passed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修改 `yscb.py`，更新 `DEFAULT_PROVIDER_URL`，實作 `_resolve_self_update_target_url` 與 `cmd_self_update`，恢復 `main()` 派發
- [x] **TASK-02**：修改 `yscb.py`，實作自包含版本探測 `_discover_latest_core`，重構 `cmd_init` 支援預設 `".yscb"`、`--fix` 自癒修復與連鎖自動觸發 `core reload`
- [x] **TASK-03**：同步修改 `yscb.py` 與 `source/core/core/installer.py`，將 `yscb.py.bak` 與 `*.bak` 納入 `INTERNAL_IGNORE_PATTERNS`
- [x] **TASK-04**：修改 `source/core/core/update_checker.py` 實作 `invalidate_cache`，並於 `installer.py` 中的 `cmd_install` 與 `cmd_update` 成功後調用
- [x] **TASK-05**：編寫單元測試套件 `source/core/tests/test_distribution_lifecycle.py`，完整覆蓋 FT-01 ~ FT-08
- [x] **TASK-DOC**：更新 `source/core/README.md` 說明 `init --fix` 與 `self-update`

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
