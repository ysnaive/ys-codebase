# YS-Codebase (`ys-codebase`)

一套專為個人獨立開發者、中小型團隊與 Case-by-Case / 接案專案打造的輕量、模組化 AI Agent 代碼庫工程工具與管理系統。

---

## 🌟 核心架構特色

1. **統一 CLI 調度器 (`yscb_cli.py`)**：統一轉接各模組專屬 CLI（如 `python yscb_cli.py agents-workflow verify`）與 Installer 管理指令。
2. **極簡單檔起手**：下游專案僅需 checkout [`yscb_installer.py`](./yscb_installer.py) 與同層 [`yscb_config.json`](./yscb_config.json) 即可運作。
3. **Zero External Dependency**：純 Python 3 標準庫實現，跨平台（Windows / macOS / Linux）免安裝額外套件。
4. **Source / Build / Modules 三層空間分流**：
   - **標準使用者模式 (Build ➔ Modules)**：從遠端 `build/<module>`（最低執行需求發布物）拉取並安裝至本地 `modules/<module>` 運行（含本地 `config.json` + `config.template.json`）。
   - **開發者源碼模式 (Source Mode, `--source`)**：安裝 `source/<module>` 完整原始碼至本地 `source/<module>`，並**自動強制相依安裝 `source/core` 基礎庫**，解鎖本地 Modify、Build 與 Push 能力。
5. **模組 Scripts 與 Hook 規範**：
   - `module/scripts/cli.py`：模組專屬 CLI 入口（支援 `--help`）。
   - `module/scripts/_installed.py`：安裝完成後置 Hook。
   - `module/scripts/_uninstall.py`：卸載前置 Hook。

---

## 📁 倉庫結構

```text
ys-codebase/
├── yscb_cli.py                    # 統一 CLI 調度轉接器
├── yscb_installer.py              # 核心安裝管理引擎
├── yscb_config.json               # 專案核心設定檔
├── yscb_config.template.json      # 純淨設定檔範本
├── README.md                      # 專案說明
├── docs/                          # 系統架構與規範知識庫
│
├── source/                        # [源碼空間] 完整開發原始碼 (開發者模式目標)
│   ├── core/                      # 核心基座 (任何 --source 模組的強制相依底層)
│   └── <module_name>/             # 各模組原始碼 (含 scripts/cli.py, _installed.py 等)
│
├── build/                         # [發布產物空間] 僅包含最低執行需求內容 (ex: 僅含 config.template)
│   └── <module_name>/             # 由 source/ 編譯/打包產出，供純使用端拉取
│
├── modules/                       # [本地運行空間] 於本機端運行的模組 (ex: 含 config + config.template)
│   └── <module_name>/             # 純使用端安裝目標，由遠端/本地 build/ 複製而來
│
└── tests/                         # 自動化測試套件
    └── test_installer.py
```

---

## 🚀 快速上手 (Quick Start)

### 1. 檢視可用模組與指令
```bash
python yscb_cli.py --help
```

### 2. 使用 Installer 管理模組
```bash
# 初始化設定檔
python yscb_cli.py installer init

# 安裝模組 (發布物模式)
python yscb_cli.py installer install agents-workflow

# 檢視模組安裝狀態
python yscb_cli.py installer status
```

### 3. 調用已安裝模組專屬 CLI
```bash
# 查看 agents-workflow 指令手冊
python yscb_cli.py agents-workflow --help

# 執行 Dev Plan 合規稽核
python yscb_cli.py agents-workflow verify

# 掃描計畫狀態矩陣
python yscb_cli.py agents-workflow scan --all
```

---

## 📄 License
MIT License
