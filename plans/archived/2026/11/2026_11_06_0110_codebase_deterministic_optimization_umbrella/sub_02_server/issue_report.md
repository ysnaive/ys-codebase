# 原業務功能缺失紀錄 (Original Missing Feature Issue Report)

> 功能名稱：server 原業務功能缺失紀錄 (server Issue Report)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Confirmed
> 模型：Unknown
> 模板版本：v1.0

---

## 1. 紀錄原則與盲眼子代理閱讀規範

- 本文件為 `sub_02_server` 唯一允許盲眼子代理（Subagent A / B / D / E）閱讀之落檔文件。
- 僅限屬於「原業務功能缺失（尚未設計或未定義之產品功能規格、需跨模組新增架構契約之能力缺口）」方得登錄於下方清單並於本次計畫中忽略；凡屬「實作邏輯錯誤、併發問題、非同步生命週期缺陷、型別/邊界防禦疏失、狀態殘留」皆已納入本子計畫直接修復並補齊單元測試。

---

## 2. 已識別之原業務功能缺失清單 (Identified Missing Feature Issues)

| 編號 | 檔案路徑與行號 | 問題類別 | 原業務功能缺失描述與影響 | 處置狀態 |
| :---: | :--- | :---: | :--- | :---: |
| **ISS-01** | `scripts/cli.py:203-209` | 功能缺失（強制強殺後之外部日誌歸檔規格） | 當 `server stop --force`（或 HTTP 優雅關閉逾時）由外部 CLI 直接呼叫 `kill_process_tree` 強殺 Master 進程時，由 CLI 直接呼叫 `ServerLogger(yscb_root=state.root).archive_and_close()` 立即歸檔 `.cache/server/log` 並更新 `fallback_summary["archive_log"]`。 | Fixed |
