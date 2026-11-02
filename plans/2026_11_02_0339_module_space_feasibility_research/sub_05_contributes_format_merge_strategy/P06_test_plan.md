# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`core.contributes` 格式驅動合併策略與 `file-space` 來源追蹤修正  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `ContributesValidator.parse_type_signature` 解析 `\| extend`、`\| replace`、`\| merge`、`\| unique` 及 `validate_format_schema` 檢驗通過 | FR-01, NFR-01 | `python yscb.py dev test core -q` (`test_validator_types`, `test_validator_format_meta_check`) |
| **FT-02** | 單元測試 | 驗證 `_tag_provider` 注入 `"__providers__"` 清單及 `_deep_merge` 依據 `_format.json` 執行 `extend`、`replace`、`merge` 策略與來源累加 | FR-02, EC-03 | `python yscb.py dev test core -q` (`test_provider_tagging`, `test_schema_driven_merge_strategies_and_providers`) |
| **FT-03** | 單元與整合測試 | 驗證 `FileSpaceManager` 依據 `"__providers__"` 正確判定 `FileSpaceOrigin.PROJECT`、`MODULE` 與 `MERGED`，且實機 `file-space status` 中 `[source]` 為 `origin=project` | FR-03, FR-04, EC-04 | `python yscb.py dev test file-space -q` (`test_ft01_dual_track_aggregation_and_override`) & `python yscb.py file-space status` |
| **ET-01** | 邊界測試 | 驗證 `_format.json` 填寫非法合併策略時 `validate_format_schema` 攔截報錯 (`ERROR`)，以及 `\| unique` 攔截跨模組同名碰撞同時放行 `project` 覆寫 | EC-01, EC-02 | `python yscb.py dev test core -q` (`test_validator_format_meta_check`, `test_schema_driven_merge_strategies_and_providers`) |
| **RT-01** | 回歸測試 | 驗證 `core` (219/219)、`file-space` (12/12) 全套單元測試與 `contributes check --all` 100% 通過 | NFR-01 | `python yscb.py dev test core -q && python yscb.py dev test file-space -q && python yscb.py contributes check --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_validator.py` 全數通過，`parse_type_signature` 與 `validate_format_schema` 正確解析並校驗合併策略 | 2026-11-02 08:23 |
| **FT-02** | `Passed` | `test_contributes.py` 全數通過，`_deep_merge` 依 `_format.json` 執行 `extend`/`replace`/`unique` 並累積 `__providers__` | 2026-11-02 08:23 |
| **FT-03** | `Passed` | `file-space` 測試 `Pass: 12(100.0%)`；實機 `file-space status` 顯示 `[source] origin=project`、`[docs]/[plans] origin=module` | 2026-11-02 08:23 |
| **ET-01** | `Passed` | 非法策略觸發 `_types.SpaceDef.include` 與 `spaces.merge` 錯誤攔截；`unique` 成功拒絕 `mod_b` 碰撞並允許 `project` 覆寫 | 2026-11-02 08:23 |
| **RT-01** | `Passed` | `core` 測試 `Pass: 219(100.0%), Fail: 0`；`file-space` 測試 `Pass: 12(100.0%), Fail: 0`；`contributes check --all` 全綠 | 2026-11-02 08:23 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `python yscb.py file-space status` 與 `contributes check --all` 輸出：確認純專案空間 `[source]` 正確顯示為 `origin=project`（不再誤標為 `merged`），且 `_format.json` 支援 `\| merge/extend/replace/unique` 策略宣告 | `[測試通過]` | 開發者確認通過（後續顯示格式改為 `origin(A)` / `merged(A, B, ...)` 於 `revision_log.md` `[REV-01]` 執行） |

