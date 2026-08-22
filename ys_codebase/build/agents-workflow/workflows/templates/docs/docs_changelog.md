---
namespace: "[Namespace/Module]"
doc_type: "changelog"
status: "draft"
source_paths:
  - "[src/path/to/file]"
related_docs:
  - "./README.md"
last_updated: "YYYY-MM-DD"
---

# Baz — 架構演進歷史 (Changelog)

> 本文件記錄 `[Namespace/Module]` 模塊的**重大架構重構**歷史。
> 日常功能新增請見 `{plans_dir}`；API 層級的當前規格請見 `README.md` 及主題文件。

> [!NOTE]
> 本文件不記錄每次日常修改，**僅記錄**涉及架構變更、職責重劃或大規模重構的事件。

---

## [YYYY-MM-DD] 重構：[重構事件標題]

### 舊架構的問題

[描述重構前的設計是什麼樣子，以及它暴露出的問題或痛點。]

- **問題 1**：[例：FooClass 同時承擔了 A 和 B 兩個職責，導致每次修改 A 都容易誤傷 B]
- **問題 2**：[例：BarService 的初始化流程與 BazHandler 高度耦合，無法獨立測試]

### 本次重構做了什麼

[描述這次重構的核心改變。]

- [改變 1：例：將 FooClass 拆分為 FooReader 和 FooWriter 兩個職責明確的類別]
- [改變 2：例：引入 IBazHandler 介面，解除 BarService 與 BazHandler 的直接依賴]

### 參考開發計畫

- **Plan 歸檔路徑**：`{archive_dir}/{YYYY}/{MM}/{YYYY_MM_DD_HHMM_計畫名稱}/`
  *(註：對計畫統一參照歸檔路徑。若該計畫尚未歸檔，按名稱 `YYYY_MM_DD_HHMM_[計畫名稱]` 於 `{plans_dir}` 原位檢索即可)*

---

## [YYYY-MM-DD] 重構：[更早的重構事件標題]

> 按時間倒序排列（最新的在最上方）。

### 舊架構的問題

[...]

### 本次重構做了什麼

[...]

### 參考開發計畫

[...]
