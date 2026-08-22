# YS-Codebase (`ys-codebase`)

一套專為個人獨立開發者、中小型團隊與 Case-by-Case / 接案專案打造的輕量、模組化 AI Agent 代碼庫工程工具與管理系統。

---

## 🌟 核心架構特色

1. **100% 專案自包含 (Self-Contained)**：無任何機器/使用者全域依賴，即開即用，零環境污染。
2. **2 × 2 設定與協定矩陣 (The 2x2 Matrix)**：
   - 範疇：`Codebase`（全專案基底） vs. `Module`（單一模組）
   - 權限與生命週期：`ProjectLevel`（`*.project.json`，進 Git 團隊規範） vs. `UserLevel`（`*.local.json`，忽略 Git 個人偏好）
3. **統一核心 Runtime SDK (`yscb_core`)**：`core` 模組作為標準建置庫，提供全模組共享的 `ProjectContext`、`ConfigManager` 與 `Console`。
4. **自引用（Dogfooding）三層架構**：
   - **`:/ys_codebase/` [工具庫源碼環境]**：工具庫核心源碼（Installer、CLI、`source/` 源碼庫、`build/` 發布產物空間與模組架構設計文檔）。
   - **`:/test/` [假專案測試環境]**：模擬下游真實消費者專案，配置獨立沙盒與自動化回歸測試套件（`run_regression.py`）。
   - **`:/` [自引用 Dogfooding 環境]**：根專案自引用使用 `ys-codebase` 工具（包含 `modules/`、`docs/` 知識庫與 `plans/` 計畫紀錄）。
5. **統一 CLI 調度器 (`yscb_cli.py`)**：統一轉接各模組專屬 CLI（如 `python yscb_cli.py agents-workflow verify`）與 Installer 管理指令。
6. **Zero External Dependency**：純 Python 3 標準庫實現，跨平台（Windows / macOS / Linux）免安裝額外套件。

---

## 📁 倉庫結構

```text
ys-codebase/ (專案根目錄，代表 ":/"，自引用 Dogfooding 環境)
├── yscb_cli.py                        # [自引用] 統一 CLI 調度轉接器
├── yscb_installer.py                  # [自引用] 核心安裝管理引擎
├── yscb_config.json                   # [Codebase.Project] 專案核心設定檔
├── yscb_config.template.json          # 純淨設定檔範本
├── README.md                          # 專案說明
├── docs/                              # 專案頂層說明與架構索引知識庫
├── plans/                             # 專案 Plans 與需求規劃紀錄
│
├── modules/                           # [自引用運行空間] 根專案自引用安裝的發布物模組
│   ├── core/                          # Core Runtime SDK (yscb_core)
│   └── agents-workflow/               # AI Agent SOP 工作流模組 (運行實例)
│
├── ys_codebase/                       # [完整原始碼開發環境 (":/ys_codebase/")]
│   ├── yscb_cli.py                    # 工具庫核心 CLI 調度器
│   ├── yscb_installer.py              # 工具庫核心安裝管理引擎
│   ├── yscb_config.template.json      # 模組設定模板
│   ├── source/                        # [源碼空間] 模組完整源碼 (開發者模式目標)
│   │   ├── core/                      # 核心基座 (yscb_core SDK)
│   │   └── agents-workflow/           # AI Agent SOP 工作流模組源碼
│   ├── build/                         # [發布產物空間] 最低執行需求產物
│   │   ├── core/                      # Core SDK 發布物
│   │   └── agents-workflow/           # 由 source/ 打包產出，供下游純使用端拉取
│   └── docs/                          # 工具庫專屬架構、規範與設計文檔
│
└── test/                              # [假專案測試環境 (":/test/")]
    ├── yscb_cli.py                    # 測試沙盒 CLI
    ├── yscb_installer.py              # 測試沙盒安裝引擎
    ├── yscb_config.json               # 測試沙盒配置檔
    ├── run_regression.py              # 一鍵全自動回歸測試腳本
    └── tests/                         # 自動化單元與整合測試套件 (含 test_installer.py)
```

---

## 🔄 標準作業流程 (Standard Workflow)

```text
[1. 開發階段 (:/ys_codebase/)]
  - 源碼修改於 :/ys_codebase/source/
  - 執行 installer build 將 source/ 打包成 build/
        │
        ▼
[2. 回歸測試階段 (:/test/)]
  - 執行 python test/run_regression.py (單元/整合 + 下游沙盒 E2E 回歸)
        │
        ▼
[3. 自引用更新階段 (:/)]
  - 測試通過後，在 :/ 執行更新同步套用最新產物
```

---

## 🚀 快速上手 (Quick Start)

### 1. 檢視可用模組與指令
```bash
python yscb_cli.py --help
```

### 2. 執行自動化回歸測試
```bash
python test/run_regression.py
```

### 3. 使用 Installer 管理模組
```bash
# 初始化設定檔
python yscb_cli.py installer init

# 安裝模組 (發布物模式，自動連帶安裝 core)
python yscb_cli.py installer install agents-workflow

# 檢視模組安裝狀態
python yscb_cli.py installer status
```

### 4. 調用已安裝模組專屬 CLI
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
