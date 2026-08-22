---
doc_type: "overview"
status: "active"
last_updated: "YYYY-MM-DD"
---

# 知識地圖 (Knowledge Map)

> 本文件是 `docs/` 的全域索引，也是 AI Agent 進入專案知識庫的**第一站**。
> 每次新增或移除模塊的文件時，必須同步更新此索引。

---

## 全系統模塊索引

| 模塊（Namespace）| 文件路徑 | 狀態 | 簡述 |
| :--- | :--- | :--- | :--- |
| `[Namespace/Module]`（示例）| [docs/[Module]/[SubModule]/README.md](../Foo/Bar/Baz/README.md) | `active` | [一句話模塊簡介] |
| `[Namespace/Module].Qux`（示例）| [docs/Foo/Bar/Qux/README.md](../Foo/Bar/Qux/README.md) | `active` | [一句話模塊簡介] |

> 請依實際建立的模塊替換上方示例列。狀態欄位直接對應該模塊 `README.md` Frontmatter 中的 `status`。

---

## 全系統架構圖

> 見 [architecture-overview.md](./architecture-overview.md)。

---

## 文件規範

> 所有文件的撰寫規範、模板清單與 Agent 操作規範，見 [DocumentationStandards.md](../../.agents/workflows/DocumentationStandards.md)。

---

## Agent 入口指引

Agent 進入知識庫時，建議按以下順序讀取：

1. 閱讀本文件，確認改動涉及的模塊。
2. 前往對應模塊的 `README.md`，建立基本認識。
3. 根據 README 的「文件導覽」，按需讀取相關主題文件或 `DESIGN_NOTES.md`。
4. 若需要了解歷史背景，閱讀模塊的 `CHANGELOG.md` 或 `{archive_dir}/`。
