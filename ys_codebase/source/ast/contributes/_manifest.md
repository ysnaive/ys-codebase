# `ast` 模組擴充貢獻宣告清單 (Contributes Manifest)

本文件為 `ast` 模組之雙向擴充契約總表，定義本模組對外開放之擴充點（Ingress）與向其他模組注入之貢獻項目（Egress）。

---

## 1. 對外開放之擴充點 (Ingress Schema — `_format.json`)

其他生態系模組可於其 `contributes/ast.json`（或宿主專案於 `ys_codebase/config/ast/contribute.json`）中，依據 `_format.json` 規範向 `ast` 引擎註冊語言解析配置：

- **`languages`** (`dict[str, LanguageDef]`)：註冊支援的程式語言或領域檔案格式，支援 `"tree_sitter"`（指定 `grammar`、`query_file` / `query_files`、`spaces` 範圍約束、`processors` 單檔精煉器、`receiver_aliases`、`symbol_folding`、`module_resolver` 與 `edge_refiners`）與 `"custom"`（指定 `parser_entry` 類別路徑）兩種解析模式，並支援 `| merge` 策略覆寫或擴充副檔名清單 (`extensions`)。
- **`spaces`** (`list[str]`)：宣告模組欲納入 `ASTEngine` 全倉解析與快照同步之 `core.space` 目標空間清單。

---

## 2. 向其他模組注入之貢獻 (Egress Contributes)

| 目標模組 | 宣告檔案 | 貢獻內容摘要 |
| :--- | :--- | :--- |
| **`core`** | `contributes/core.json` | 註冊 `ast.storage://` 與 `ast.cache://` URI Scheme；發布 `on_ast_index_updated` 與 `on_register_ast_spaces` 域事件；掛載 `ast` CLI 命令群（`outline`, `slice`, `traverse`, `callers`, `callees`, `impact`, `status`, `clean`）。 |
| **`agents-workflow`** | `contributes/agents-workflow.json` | 貢獻 `ast` 用法速查卡 (`usage_guide`) 與設定體檢片段 (`config_guide`) 供 `/how-to-yscb` 與 `/how-to-config-yscb` 聚合檢索。 |
