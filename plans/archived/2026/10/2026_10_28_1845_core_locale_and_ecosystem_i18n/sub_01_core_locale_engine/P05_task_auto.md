# 實作任務清單 (Task Breakdown)

> 功能名稱：實作 `core.locale` 多層語系引擎與宣告式 `definition` 契約校驗 (`sub_01_core_locale_engine`)  
> 建立日期：2026-10-29  
> 所屬主計畫：`2026_10_28_1845_core_locale_and_ecosystem_i18n`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `core/contributes/_format.json` 與 `_manifest.md` 新增 `"locales"` 擴充點 Schema（參見 `P04_implementation_plan_auto.md` §4）
- [x] **TASK-02**：更新 `core/contributes.py` 實作 `locales.__modules__` 按 Donor 分桶聚合與語系檔 `mtime` 追蹤（參見 `P04_implementation_plan_auto.md` §4）
- [x] **TASK-03**：新建 `core/locale.py` 並註冊於 `core/__init__.py`，實作顯式優先級退避鏈、遞迴專有名詞插值與 `validate_module_locales`（參見 `P04_implementation_plan_auto.md` §4）
- [x] **TASK-04**：更新 `core/commands/contributes_cmd.py` 與 `dev/checker.py` 串聯 `locales` 靜態契約校驗（參見 `P04_implementation_plan_auto.md` §4）
- [x] **TASK-05**：完成 `core/tests/test_locale.py` 與 `dev/tests/test_checker.py` 測試驗證及 `@build` 熱部署（參見 `P04_implementation_plan_auto.md` §4）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

