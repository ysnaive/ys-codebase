---
target: "CLI/Specification"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb_cli.py"
  - "yscb_installer.py"
  - "source/core/yscb_core/"
  - "source/agents-workflow/scripts/cli.py"
related_docs:
  - "./ARCHITECTURE.md"
  - "./STANDARDS.md"
last_updated: "2026-08-22"
---

# YS-Codebase CLI 指令規範 (CLI Specification)

`ys-codebase` 採用 **「統一轉接器 (`yscb_cli.py`) + 核心安裝器 (`yscb_installer.py`) + 模組專屬 CLI (`module/scripts/cli.py`)」** 的調度架構，並由 `yscb_core` 自動注入執行環境。

---

## 🧭 1. 統一轉接器：`yscb_cli.py`

`yscb_cli.py` 是下游專案調用任何工具或模組的統一入口。

### 指令語法
```bash
python yscb_cli.py <module_name> [command] [options...]
```

### 核心特性
1. **Installer 轉接**：`python yscb_cli.py installer <args...>` 等效於調用核心安裝引擎。
2. **模組 CLI 轉發**：`python yscb_cli.py <module_name> <args...>` 自動查找並調用該模組的 `scripts/cli.py`。
3. **Core SDK 自動注入**：調度前自動將 `modules/core` (或 `source/core`) 掛載至 `sys.path` 與 `PYTHONPATH`，讓模組無痛引用 `yscb_core`。
4. **全局幫助與探索**：`python yscb_cli.py --help` 動態掃描專案已安裝模組並輸出指令手冊。

### 調用範例
```bash
# 調用 Installer 檢視狀態
python yscb_cli.py installer status

# 調用 Installer 安裝模組 (自動連帶安裝 core)
python yscb_cli.py installer install agents-workflow

# 初始化專案 SOP 路徑規範 (消除 !undefined)
python yscb_cli.py agents-workflow init --default
python yscb_cli.py agents-workflow init --plans-dir plans --archive-dir archive_plans --docs-dir docs --extensions-dir extensions

# 查詢專案可用 Extension 擴充清單與 Checklist (sop_ext://)
python yscb_cli.py agents-workflow ext list
python yscb_cli.py agents-workflow ext show ext_security_audit

# 調用 agents-workflow 的專屬 CLI 定式工具
python yscb_cli.py agents-workflow verify
python yscb_cli.py agents-workflow scan --all
python yscb_cli.py agents-workflow search --query "Architecture"
python yscb_cli.py agents-workflow archive 2026_08_22_1200_my_plan

# 知識庫 docs 健康守護與按需輔助
python yscb_cli.py agents-workflow docs init
python yscb_cli.py agents-workflow docs audit
python yscb_cli.py agents-workflow docs new-topic Core lifecycle

# 調用 core 核心 SDK CLI
python yscb_cli.py core info
python yscb_cli.py core uri list

# 語意 URI 解析與反向轉換 (Semantic URI Protocol)
python yscb_cli.py uri resolve docs://_project/STANDARDS.md
python yscb_cli.py uri list
python yscb_cli.py uri to-uri docs/_project/STANDARDS.md

# 生成 / 清理 IDE 引用式指令 (Google Antigravity / Gemini)
python yscb_cli.py agents-workflow --ide-antigravity -prefix "sop_"
python yscb_cli.py agents-workflow --ide-clear
```

---

## 🛠️ 2. 核心安裝管理器：`yscb_installer.py`

### 指令清單

| 指令 | 語法 | 說明 |
| :--- | :--- | :--- |
| `help` | `python yscb_installer.py help [command]` | 顯示系統說明或子指令手冊 |
| `init` | `python yscb_installer.py init [--repo <URL>] [--branch <BRANCH>] [-p <ROOT>] [--force]` | 初始化建立 `yscb_config.json` |
| `install` | `python yscb_installer.py install [<modules> ...] [--source] [--force]` | 安裝模組（自動解析相依如 `core`，安裝後觸發 `_installed.py`） |
| `pull` | `python yscb_installer.py pull [<modules> ...] [--source]` | 同步更新本機快取與已安裝模組 |
| `build` | `python yscb_installer.py build [<modules> ...] [--all]` | 編譯/封裝源碼至 `build/<module>`（自動遞迴相依建置） |
| `push` | `python yscb_installer.py push -m "<msg>" [--branch <BRANCH>]` | 推送本地修改回中央庫 |
| `status` | `python yscb_installer.py status` | 檢視已安裝模組狀態矩陣 |
| `list` | `python yscb_installer.py list [--remote]` | 列出所有可用模組 |
| `remove` | `python yscb_installer.py remove <module> [--force]` | 卸載模組（卸載前觸發 `_uninstall.py`） |

---

## 🔌 3. 模組專屬 Scripts 規範

每個模組可實作以下標準腳本（存放於 `module/scripts/`）：

1. **`cli.py`**：模組專屬 CLI 接口。若存在，**必須**支援 `--help` / `-h`。
2. **`_installed.py`**：安裝後置 Hook。當 `yscb_installer.py` 成功複製並註冊模組後自動調用。
3. **`_uninstall.py`**：卸載前置 Hook。當 `yscb_installer.py` 刪除模組目錄前自動調用。
4. **`_migration.py`**：版本升級遷移 Hook。當模組版本更新時自動調用。
