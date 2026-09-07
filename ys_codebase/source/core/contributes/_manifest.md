# Core 模組貢獻導覽清冊 (Contributes Manifest)

> 本清冊記錄 `core` 微內核對外貢獻與自註冊之能力、協議與指令。

## 1. 外部注入清冊 (Egress Contributions)

### 1.1 `core.json`（微內核基礎設施）
- **語意 URI 協議**：`yscb://`, `yscb.host://`, `module.mirror://`, `snapshot://`, `module://`, `config://`, `cache://`, `storage://`, `yscb.venv://`。
- **核心 CLI 指令樹**：
  - `install`: 安裝模組套件或 local @build。
  - `update`: 升級模組版本。
  - `remove`: 移除環境模組。
  - `list`: 列出模組清單。
  - `status`: 環境健康與執行期診斷報告。
  - `reload`: 重載環境與刷新 contributes 快取。
  - `rollback`: 快照回滾。
  - `uri`: 語意 URI 解析、轉換與可用性檢查。
  - `config`: 模組組態讀取、設定與重載。
  - `restore`: 修復或補齊缺失模組。
  - `event`: 生命週期事件清冊檢索。
  - `contributes`: Contributes 擴充宣告與 Schema 剛性檢驗管理。
- **生命週期事件**：`pre_cli_dispatch`, `post_cli_dispatch`, `on_reload`, `on_installed`, `on_update`, `on_remove`。

### 1.2 `agents-workflow.json`（工作流擴充）
- 向 `agents-workflow` 註冊核心 CLI 規範與標準資產。
