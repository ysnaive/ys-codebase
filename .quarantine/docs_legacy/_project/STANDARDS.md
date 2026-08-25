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

## 5. Codebase 專用語意 URI 協定 (Semantic URI Protocol)

為了消除深層子目錄跳轉（如 `../../../../`）造成的路徑脆弱性，`ys-codebase` 建立了統一的語意 URI 體系：

| URI 協議 | 核心語意 | 解析邏輯 | 狀態異常處理 |
| :--- | :--- | :--- | :--- |
| **`project://`** | 專案根目錄 | `ProjectContext.get_project_root()` | 找不到根目錄回傳 `!undefined` |
| **`yscb://`** | 工具庫安裝目錄 | `ProjectContext.get_yscb_root()` | 未安裝回傳 `!undefined` |
| **`plans://`** | 活躍開發計畫目錄 | 讀取 `agents-workflow` 之 `paths.plans_dir` | 模組未裝或未配置回傳 `!undefined` |
| **`archive://`** | 歷史計畫歸檔目錄 | 讀取 `agents-workflow` 之 `paths.archive_dir` | 模組未裝或未配置回傳 `!undefined` |
| **`docs://`** | 專案知識庫目錄 | 讀取 `agents-workflow` / 專案之 `paths.docs_dir` | 模組未裝或未配置回傳 `!undefined` |
| **`sop_ext://`** | 專案 SOP 擴充清單目錄 | 讀取 `agents-workflow` 之 `paths.extensions_dir` | 模組未裝或未配置回傳 `!undefined` |

### Python SDK 調用範例：
```python
from yscb_core import ProjectURI

# 解析為本機實體 Path (若未設定回傳 "!undefined")
standards_path = ProjectURI.resolve("docs://_project/STANDARDS.md")

# 反向匹配最短 URI
uri_str = ProjectURI.to_uri(standards_path) # "docs://_project/STANDARDS.md"
```

### CLI 調度指令：
```bash
python yscb_cli.py uri resolve docs://_project/STANDARDS.md
python yscb_cli.py uri list
python yscb_cli.py uri to-uri docs/_project/STANDARDS.md
```

---

## 6. 測試與品質門檻 (Testing & Quality Gate)

- **測試框架**：採用純 Python 標準庫 `unittest`。
- **測試存放路徑**：`test/tests/`。
- **執行測試**：
  ```bash
  python test/run_regression.py
  ```
- **門檻要求**：所有核心管理工具、相依解析器、2x2 設定合併、語意 URI 解析與 build 管線之修改，必須維持 100% 測試通過率。

---

## 7. 專案知識庫 7 大抽象維度與維護規範 (Documentation Standards)

專案知識庫（`docs://`）只陳述「當前客觀事實與坑點」，不記錄歷史探索爭辯過程（留於 `plans://`）：

1. **7 大抽象知識維度**：
   - ① 領域概念模型 ➔ `docs/_project/ARCHITECTURE.md`、`docs/<Module>/README.md`
   - ② 靜態邊界拓撲 ➔ `docs/<Module>/README.md`（職責邊界）
   - ③ 中觀動態機制 ➔ `docs/<Module>/[topic].md`（**跨物件協同、狀態機、資料管線、協議強制獨立專題**）
   - ④ 介面合約承諾 ➔ Typed Docstrings / Public Headers
   - ⑤ 工程妥協暗角 ➔ `docs/<Module>/DESIGN_NOTES.md`（`DN-XX` + `[!CAUTION]`）
   - ⑥ 人因操作引導 ➔ `docs/<Module>/README.md` / `CLI_SPECIFICATION.md`
   - ⑦ 架構重構歷史 ➔ `docs/<Module>/CHANGELOG.md`
2. **對話視窗 vs. 文檔檔案排版與語法邊界鐵律**：
   - **對話視窗 (Chat Window / CLI Output)**：
     - 🚫 **嚴禁使用 Mermaid 圖表**（一律使用純文字樹狀圖、ASCII 與 Markdown 表格）。
     - 🚫 **嚴禁使用 LaTeX 數學公式**（一律使用純文字表示，如 `O(N log N)`、`x >= y`）。
   - **Markdown 文檔檔案本體 (`.md` 文件)**：
     - ✅ **盡量使用強定義語法**：圖表排版優先級為 Markdown 表格 > 垂直 Mermaid (TD) > 橫向 Mermaid > ASCII；數學公式盡量使用標準 LaTeX（如 `$O(N^2)$`）。
   - **超連結規範**：文檔內部超連結一律採用標準相對路徑（確保原生點擊跳轉）。
3. **P03/P05/P06 三維錨點驗收**：Phase 4 預排交付清單，Phase 7 結案前 1:1 交叉對齊驗收。

