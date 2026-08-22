---
target: "CLI/Specification"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb_cli.py"
  - "yscb_installer.py"
  - "source/agents-workflow/scripts/cli.py"
related_docs:
  - "./ARCHITECTURE.md"
  - "../_project/STANDARDS.md"
last_updated: "2026-08-22"
---

# YS-Codebase CLI 指令規範 (CLI Specification)

`ys-codebase` 採用 **「統一轉接器 (`yscb_cli.py`) + 核心安裝器 (`yscb_installer.py`) + 模組專屬 CLI (`module/scripts/cli.py`)」** 的三層式調度架構。

---

## 🧭 1. 統一轉接器：`yscb_cli.py`

`yscb_cli.py` 是下游專案調用任何工具或模組的統一入口。

### 指令語法
```bash
python yscb_cli.py <module_name> [command] [options...]
```

### 核心特性
1. **Installer 轉接**：`python yscb_cli.py installer <args...>` 等效於 `python yscb_installer.py <args...>`。
2. **模組 CLI 轉發**：`python yscb_cli.py <module_name> <args...>` 自動查找並調用該模組的 `scripts/cli.py`。
3. **全局幫助與探索**：`python yscb_cli.py --help` 列出所有已安裝/可用模組與其 CLI 狀態。

### 調用範例
```bash
# 調用 Installer 檢視狀態
python yscb_cli.py installer status

# 調用 Installer 安裝模組
python yscb_cli.py installer install agents-workflow

# 調用 agents-workflow 的專屬 CLI 定式工具
python yscb_cli.py agents-workflow verify
python yscb_cli.py agents-workflow scan --all
python yscb_cli.py agents-workflow search --query "Architecture"

# 生成 / 清理 IDE 引用式指令 (Gemini / Antigravity)
python yscb_cli.py agents-workflow --ide-gemini -prefix "sop_"
python yscb_cli.py agents-workflow --ide-clear
```

---

## 🛠️ 2. 核心安裝管理器：`yscb_installer.py`

### 指令清單

| 指令 | 語法 | 說明 |
| :--- | :--- | :--- |
| `help` | `python yscb_installer.py help [command]` | 顯示系統說明或子指令手冊 |
| `init` | `python yscb_installer.py init [--repo <URL>] [--branch <BRANCH>] [--force]` | 初始化建立 `yscb_config.json` |
| `install` | `python yscb_installer.py install [<modules> ...] [--source] [--force]` | 安裝指定模組（`--source` 自動相依 `core`，安裝後觸發 `_installed.py`） |
| `pull` | `python yscb_installer.py pull [<modules> ...] [--source]` | 同步更新本機快取與已安裝模組 |
| `build` | `python yscb_installer.py build [<modules> ...] [--all]` | 編譯/封裝源碼至 `build/<module>`（自動相依連帶建置） |
| `push` | `python yscb_installer.py push -m "<msg>" [--branch <BRANCH>]` | 推送本地修改回中央庫 |
| `status` | `python yscb_installer.py status` | 檢視已安裝模組狀態矩陣 |
| `list` | `python yscb_installer.py list [--remote]` | 列出所有可用模組 |
| `remove` | `python yscb_installer.py remove <module> [--force]` | 卸載模組（卸載前觸發 `_uninstall.py`） |

---

## 🔌 3. 模組專屬 Scripts 規範

每個模組可選實作以下標準腳本（存放於 `module/scripts/`）：

1. **`cli.py`**：模組專屬 CLI 接口。若存在，**必須**支援 `--help` / `-h`。
2. **`_installed.py`**：安裝後置 Hook。當 `yscb_installer.py` 成功複製並註冊模組後自動調用。
3. **`_uninstall.py`**：卸載前置 Hook。當 `yscb_installer.py` 刪除模組目錄前自動調用。
