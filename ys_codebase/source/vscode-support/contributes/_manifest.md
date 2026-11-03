# `vscode-support` 模組擴充貢獻宣告清單 (Contributes Manifest)

本文件為 `vscode-support` 模組之雙向擴充契約總表，定義本模組對外開放之擴充點（Ingress）與向其他模組注入之貢獻項目（Egress）。

---

## 1. 對外開放之擴充點 (Ingress Schema — `_format.json`)

其他生態系模組可於其 `contributes/vscode-support.json`（或宿主專案於 `ys_codebase/config/vscode-support/contribute.json`）中，依據 `_format.json` 規範向 `vscode-support` 註冊自訂 JSON Schema 映射規則：

- **`json_schemas`** (`dict[str, JsonSchemaRuleDef]`)：定義檔案匹配規則清單 (`file_match`)、Schema 來源類型 (`schema_source`: `contributes_format` | `configurable_template` | `static_file`)、靜態 Schema 語意 URI 路徑 (`schema_path`) 與說明 (`description`)。

---

## 2. 向其他模組注入之貢獻 (Egress Contributes)

| 目標模組 | 宣告檔案 | 貢獻內容摘要 |
| :--- | :--- | :--- |
| **`core`** | `contributes/core.json` | 掛載 `vscode-support` CLI 命令群（`status`, `sync`, `revert`）。 |
| **`vscode-support`** | `contributes/vscode-support.json` | 自注入 `format-meta`（校驗 `**/contributes/_format.json`）與 `manifest`（校驗 `**/manifest.json`）兩項元 Schema 規則。 |
| **`agents-workflow`** | `contributes/agents-workflow.json` | 將 `vscode-support` 操作指南與組態說明注入 `HOW_TO_YSCB_MODULES` 與 `HOW_TO_CONFIG_MODULES` 技能插槽。 |

