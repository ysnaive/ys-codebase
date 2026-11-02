# `file-space` 模組擴充貢獻宣告清單 (Contributes Manifest)

本文件為 `file-space` 模組之雙向擴充契約總表，定義本模組對外開放之擴充點（Ingress）與向其他模組注入之貢獻項目（Egress）。

---

## 1. 對外開放之擴充點 (Ingress Schema — `_format.json`)

其他生態系模組可於其 `contributes/file-space.json`（或宿主專案於 `ys_codebase/config/file-space/contribute.json`）中，依據 `_format.json` 規範向 `file-space` 註冊工作空間：

- **`spaces`** (`dict[str, FileSpaceDef]`)：定義命名工作空間之包含目錄 URI 清單 (`include`)、排除規則 (`exclude`)、檔案萬用字元過濾 (`file_patterns`)、分級雜湊策略 (`hash_policy`: `adaptive` | `full_hash` | `stat_only` | `lazy_stabilized`)、大檔門檻 (`large_file_threshold_mb`)、符號連結追蹤 (`follow_symlinks`)、常駐監聽開關 (`watch`) 與權重 (`weight`)。

---

## 2. 向其他模組注入之貢獻 (Egress Contributes)

| 目標模組 | 宣告檔案 | 貢獻內容摘要 |
| :--- | :--- | :--- |
| **`core`** | `contributes/core.json` | 註冊 `file-space.storage://` 與 `file-space.cache://` URI Scheme；發布 `on_file_space_changed` 域事件；掛載 `file-space` CLI 命令群（`status`, `scan`, `files`, `diff`, `clean`）。 |
| **`server`** | `contributes/server.json` | 註冊 `file-space-watcher` (`file_space.service:FileSpaceWatcherServiceWorker`) 常駐背景檔案監聽與增量指紋更新服務。 |
| **`agents-workflow`** | `contributes/agents-workflow.json` | 將 `file-space` 模組操作指南與組態契約注入 `HOW_TO_YSCB_MODULES` 與 `HOW_TO_CONFIG_MODULES` 技能插槽。 |
