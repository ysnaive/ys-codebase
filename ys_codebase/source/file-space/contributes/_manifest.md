# `file-space` 模組擴充貢獻宣告清單 (Contributes Manifest)

> **[Deprecated]** `file-space` 引擎已內聚併入 `core.space`；本模組僅保留最小相容宣告，建議將 `core` 更新至 `>=1.2.8.0` 後執行 `python yscb.py remove file-space` 移除本模組。

---

## 1. 對外開放之擴充點 (Ingress Schema — `_format.json`)

- **`spaces`** (`dict[str, FileSpaceDef]`)：[Deprecated] 舊版工作空間擴充點（新版請統一宣告於 `contributes/core.json` 或 `ys_codebase/config/core/contribute.json` 之 `spaces`）。

---

## 2. 向其他模組注入之貢獻 (Egress Contributes)

| 目標模組 | 宣告檔案 | 貢獻內容摘要 |
| :--- | :--- | :--- |
| **`core`** | `contributes/core.json` | [Deprecated] 保留 `file-space.storage://` 與 `file-space.cache://` 相容 URI Scheme 及 `file-space` CLI 轉發入口（`status`, `scan`, `files`, `diff`, `clean`），全數委派至 `core.space`。 |
