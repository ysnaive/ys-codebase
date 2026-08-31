`__@{BEGIN_HTML_ANNOTATION}__`

Phase 7 執行指引：
1. 目標：全量盤點交付成果、核對知識庫文檔 (docs/) 1:1 交付、追加高階版本日誌 (project://CHANGELOG.md)、提供 Conventional Commit 建議，完成計畫結案。
2. 成果展示：列出核心功能落地概述、變更檔案清單與測試驗證摘要。
3. 知識庫 1:1 交付驗收：嚴格依據 Phase 4 預排的文檔衝擊清單，1:1 核對宏觀發布日誌、中觀模組/專題手冊與微觀代碼 Docstrings 是否皆已完整交付或更新。
4. 日誌分離與發布：更新 workflow.plans://<plan>/changelog.md 為 Completed，並於 project://CHANGELOG.md 追加本次高階版本發布摘要。
5. 計畫結構合規驗證：最後收尾時需實機調用 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 指令驗證最終計畫產出之結構完整與合規性（確認無殘留 HTML 註解、標頭狀態合法）。
6. 目錄原位保留紀律：計畫預設留存原位 (workflow.plans://)，嚴禁主動執行歸檔操作，僅在開發者明確指示歸檔時才調度歸檔工具。
7. Checkpoint 等待關卡：等待開發者審查結案報告，完成本次 Dev Plan 生命週期。

`__@{PHASE07_AGENTS_GUILD}__`

`__@{END_HTML_ANNOTATION}__`

# 成果展示與結案報告 (Walkthrough)

`__@{PHASEXX_HEADER}__`

`__@{PHASE07_HEADER}__`

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| | New / Modify | |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
- **實機 UX / 人工驗證**：

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **模組手冊** | `docs/<Module>/README.md` | ✅ 已交付 | |
| **專題手冊** | `docs/<Module>/[topic].md` | ✅ 已交付 | |
| **設計決策** | `docs/<Module>/DESIGN_NOTES.md` | ✅ 已交付 | |
| **發布日誌** | `CHANGELOG.md` | ✅ 已交付 | |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [ ] **結構與註解檢核**：實機執行 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` (或 `plan check`) 驗證 100% Passed。

`__@{PHASE07_TEMPLATE}__`
