# 計畫變更紀錄 (Changelog)

> 功能名稱：[填入功能名稱]
> 模板版本：v1.0

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
|---------|------|------|
| [YYYY-MM-DD HH:MM] | `PHASE` | Phase N → Phase N+1：[Checkpoint 通過] |
| [YYYY-MM-DD HH:MM] | `DECISION` | [{Phase}:DR-XX] [決策結論一句話摘要] |
| [YYYY-MM-DD HH:MM] | `DEVIATION` | [等級] [偏差內容摘要] |
| [YYYY-MM-DD HH:MM] | `SUB-PLAN` | 新增子計畫：sub_XX_[名稱] |
| [YYYY-MM-DD HH:MM] | `SUB-DONE` | 子計畫完成：sub_XX_[名稱] |
| [YYYY-MM-DD HH:MM] | `CONTEXT` | [跨 Conversation 新增指示摘要] |
| [YYYY-MM-DD HH:MM] | `EXTENSION` | [擴充名稱] 執行完畢 |

---

## 類型標籤說明

| 標籤 | 用途 |
|------|------|
| `PHASE` | Phase 轉換（含 Checkpoint 通過） |
| `DECISION` | Deep Discussion 結論 |
| `DEVIATION` | 偏差處理記錄 |
| `SUB-PLAN` | 子計畫新增 |
| `SUB-DONE` | 子計畫完成 |
| `CONTEXT` | 跨 Conversation 的新增指示或偏好調整 |
| `EXTENSION` | 專案擴充機制的執行記錄 |
