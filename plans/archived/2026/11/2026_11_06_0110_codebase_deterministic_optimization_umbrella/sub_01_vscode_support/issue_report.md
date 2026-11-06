# 原業務功能缺失紀錄 (Original Missing Feature Issue Report)

> 功能名稱：vscode-support 原業務功能缺失紀錄 (vscode-support Issue Report)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Confirmed
> 模型：Unknown
> 模板版本：v1.0

---

## 1. 紀錄原則與盲眼子代理閱讀規範

- 本文件為 `sub_01_vscode_support` 唯一允許盲眼子代理（Subagent A / B / D / E）閱讀之落檔文件。
- 僅限屬於「原業務功能缺失（尚未設計或未定義之產品功能規格、需跨模組新增架構契約之能力缺口）」方得登錄於下方清單並於本次計畫中忽略；凡屬「實作邏輯錯誤、併發問題、型別/邊界防禦疏失、狀態殘留」皆已納入本子計畫直接修復並補齊單元測試。

---

## 2. 已識別之原業務功能缺失清單 (Identified Missing Feature Issues)

| 編號 | 檔案路徑與行號 | 問題類別 | 原業務功能缺失描述與影響 | 處置狀態 |
| :---: | :--- | :---: | :--- | :---: |
| **ISS-01** | `vscode_support/schema_compiler.py:294-305` | 功能缺失（範例推導限制） | `_infer_value_schema` 在未提供 `_format.json` 契約、僅能從 `config.*.json` 範例字典推導型別時，若陣列範例值為空陣列 `[]`（無樣本元素），無法憑空推導陣列元素型別，故 `items` 為 `{}`。需搭配 `configurable/_format.json` 方能聲明強型別陣列元素。 | Ignored |
| **ISS-02** | `scripts/cli.py:104-122` | 功能缺失（CLI 細分退出碼規格） | `cli.py:revert` 透過 `SettingsProjector.last_revert_error` 區分「無 `_yscb_managed` 可還原之冪等 no-op（回傳 0）」與「底層讀寫或解析 `settings.json` 失敗（回傳 1）」。 | Fixed |
