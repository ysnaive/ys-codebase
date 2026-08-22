---
target: "Project/Standards"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb_cli.py"
  - "yscb_installer.py"
  - "source/core/manifest.json"
  - "source/core/yscb_core/"
  - ".gitignore"
  - "tests/test_installer.py"
related_docs:
  - "./ARCHITECTURE.md"
  - "./CLI_SPECIFICATION.md"
  - "./CONTRIBUTING.md"
last_updated: "2026-08-22"
---

# 專案工程標準與模組規範 (Project Standards)

本文件定義在 `ys-codebase` 體系中開發新模組、撰寫腳本與進行自動化測試時必須遵守的剛性標準。

---

## 1. 核心紀律：Zero External Dependency (零第三方依賴)

- **原則**：Installer 引擎、Core SDK 與核心定式腳本**嚴禁引入第三方套件**（如 `requests`、`click`、`pyyaml` 等），必須 100% 使用 Python 3.8+ 標準庫實現。
- **標準替代方案**：
  - HTTP 請求 ➔ `urllib.request`
  - 命令行解析 ➔ `argparse`
  - 檔案與路徑 ➔ `pathlib.Path`、`shutil`、`os`
  - 子進程調度 ➔ `subprocess`
  - 數據格式 ➔ `json`
  - 單元測試 ➔ `unittest`

---

## 2. 模組元數據規範 (`manifest.json` Schema)

每個模組根目錄必須包含 `manifest.json`：

```json
{
  "name": "module_name",
  "version": "1.0.0",
  "description": "模組功能的簡要說明",
  "dependencies": ["core"],
  "build_exclude": ["drafts/**", "*.tmp"]
}
```

### 欄位定義：
| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| `name` | string | **是** | 模組名稱（建議使用 lowercase + hyphen/underscore） |
| `version` | string | **是** | 模組語意化版本號 (SemVer) |
| `description` | string | 否 | 模組簡要說明（顯示於 `list` 與 `status`） |
| `dependencies` | array | **是** | 相依模組清單（業務模組必須包含 `"core"`） |
| `build_exclude`| array | 否 | 在標準 build 打包時需額外排除的檔案或 glob |
| `built_at` | string | 自動 | Build 產出時由 Installer 自動注入之 ISO 時間戳 |

---

## 3. 2 × 2 設定協定與 Git 規則

```text
+-----------------------+----------------------------------+----------------------------------+
| 範疇 \ 生命週期       | Project Level (進 Git 團隊規範)  | User Level (忽略 Git 個人偏好)   |
+-----------------------+----------------------------------+----------------------------------+
| Codebase (全專案基底) | yscb_config.json                 | yscb_config.local.json           |
+-----------------------+----------------------------------+----------------------------------+
| Module (特定單一模組) | config.project.json              | config.local.json                |
|                       | config.project.template.json     | config.local.template.json       |
+-----------------------+----------------------------------+----------------------------------+
```

### 規則要點：
1. **範本提供**：
   - 模組若需要專案級設定，必須提供 `config.project.template.json`。
   - 模組若需要本機個人偏好，必須提供 `config.local.template.json`。
2. **Git 忽略規範 (`.gitignore`)**：
   - 所有 `*.local.json` 與 `yscb_config.local.json` 必須被 `.gitignore` 忽略。
   - 所有 `*.project.json`、`*.template.json` 與 `manifest.json` 必須受 Git 追蹤。
3. **載入與無損合併**：
   - 模組透過 `yscb_core.ConfigManager.load("<module_name>")` 自動依優先級合併設定。

---

## 4. 模組引用 SDK 規範

模組內部腳本禁止使用硬編碼相對路徑查找專案根目錄，一律透過 `yscb_core`：

```python
from yscb_core import ProjectContext, ConfigManager, Console

# 1. 取得專案根目錄
project_root = ProjectContext.get_project_root()

# 2. 自動合併載入 2x2 設定
config = ConfigManager.load("module_name")

# 3. 解析相對於專案根目錄的路徑
target_path = ProjectContext.resolve(config.get("target_dir", "docs"))

# 4. 統一終端輸出
Console.success("操作成功！")
```

---

## 5. 測試與品質門檻 (Testing & Quality Gate)

- **測試框架**：採用純 Python 標準庫 `unittest`。
- **測試存放路徑**：`test/tests/`。
- **執行測試**：
  ```bash
  python test/run_regression.py
  ```
- **門檻要求**：所有核心管理工具、相依解析器、2x2 設定合併與 build 管線之修改，必須維持 100% 測試通過率。
