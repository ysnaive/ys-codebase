---
target: "Project/Standards"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb_cli.py"
  - "yscb_installer.py"
  - "source/core/manifest.json"
  - ".gitignore"
  - "tests/test_installer.py"
related_docs:
  - "../_global/ARCHITECTURE.md"
  - "../_global/CLI_SPECIFICATION.md"
  - "./CONTRIBUTING.md"
last_updated: "2026-08-22"
---

# 專案工程標準與模組規範 (Project Standards)

本文件定義在 `ys-codebase` 體系中開發新模組、撰寫腳本與進行自動化測試時必須遵守的剛性標準。

---

## 1. 核心紀律：Zero External Dependency (零第三方依賴)

- **原則**：Installer 引擎與核心定式腳本**嚴禁引入第三方套件**（如 `requests`、`click`、`pyyaml` 等），必須 100% 使用 Python 3.8+ 標準庫實現。
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
  "dependencies": ["dependency_module_a"],
  "build_exclude": ["drafts/**", "*.tmp"]
}
```

### 欄位定義：
| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| `name` | string | **是** | 模組名稱（建議使用 lowercase + hyphen/underscore） |
| `version` | string | **是** | 模組語意化版本號 (SemVer) |
| `description` | string | 否 | 模組簡要說明（顯示於 `list` 與 `status`） |
| `dependencies` | array | 否 | 相依之其他模組名稱清單 |
| `build_exclude`| array | 否 | 在標準 build 打包時需額外排除的檔案或 glob |
| `built_at` | string | 自動 | Build 產出時由 Installer 自動注入之 ISO 時間戳 |

---

## 3. 模組設定檔與範本規範 (`config.template.json` / `config_global.json`)

為確保本地運行期設定檔與共享範本/全域配置清晰隔離，模組遵循以下規範：

1. **範本必備原則**：
   - 任何會產生/讀取本地 `config.json` 的模組，**必須**在源碼根目錄提供一份純淨的 `config.template.json`（或 `config.template`）。
   - 若為模組全域設定，必須命名為 `config_global.json`，且同樣**必須**提供一份 `config_global.template.json`（或 `config_global.template`）。
2. **Git 追蹤與忽略規則**：
   - **忽略項目**：`.gitignore` 忽略所有本地模組運行期產生的 `**/config.json`。
   - **追蹤項目（不被忽略）**：所有 `*template*` 檔案（如 `config.template.json`、`yscb_config.template.json`）與所有 `*global*` 檔案（如 `config_global.json`、`config_global.template.json`）**皆納入版本控制正常追蹤**。
3. **優雅降級初始化**：
   - 當模組執行時發現 `config.json` 尚未生成，必須自動讀取 `config.template.json` 作為基礎預設結構。

---

## 4. 模組標準 Scripts 接口規範 (`module/scripts/`)

為確保所有模組與 `yscb_cli.py` 轉接器及生命週期管理無縫協同，模組遵循以下腳本接口規範：

| 腳本名稱 | 必備/選用 | 調用時機與職責 | 規範要求 |
| :--- | :--- | :--- | :--- |
| **`cli.py`** | 按需 | 模組 CLI 入口。透過 `python yscb_cli.py <module> <command>` 調用。 | 若存在，**必須**支援 `--help` / `-h` 輸出完整指令手冊。 |
| **`_installed.py`** | 按需 | 安裝後置 Hook。在模組檔案複製與設定檔寫入完成後由 Installer 自動調用。 | 接收參數 `[<dest_path>, <mode>]`，用於環境初始化或資源掛載。 |
| **`_uninstall.py`** | 按需 | 卸載前置 Hook。在模組目錄被刪除前由 Installer 自動調用。 | 接收參數 `[<target_dir>, <mode>]`，用於清理自訂生成的檔案或解除註冊。 |

---

## 5. 測試與品質門檻 (Testing & Quality Gate)

- **測試框架**：採用純 Python 標準庫 `unittest`。
- **測試存放路徑**：`tests/`。
- **執行測試**：
  ```bash
  python tests/test_installer.py
  ```
- **門檻要求**：所有核心管理工具、相依解析器、Hook 機制與 build 管線之修改，必須維持 100% 測試通過率。
