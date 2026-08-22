---
target: "System/Architecture"
doc_type: "overview"
status: "active"
source_paths:
  - "ys_codebase/yscb_cli.py"
  - "ys_codebase/yscb_installer.py"
  - "ys_codebase/source/core/"
  - "ys_codebase/source/agents-workflow/"
related_docs:
  - "../README.md"
  - "./CLI_SPECIFICATION.md"
  - "./STANDARDS.md"
last_updated: "2026-08-22"
---

# 全域系統架構設計 (System Architecture)

`ys-codebase` 是一套專為個人獨立開發者、中小型團隊與接案專案量身打造的模組化 AI Agent 工程工具庫。

---

## 1. 核心設計原則

1. **100% 專案自包含 (Project Self-Contained & Zero Machine Global)**：
   - 捨棄任何作業系統/使用者全域路徑（無 `~/.yscb/`）。
   - 專案內部完全自給自足，複製專案或更換開發機時保證零環境污染與即開即用。
2. **2 × 2 設定與協定矩陣 (The 2x2 Matrix)**：
   - 將系統所有設定精確劃分為：影響範疇（`Codebase` vs. `Module`）× 生命週期與權限（`ProjectLevel` [進 Git] vs. `UserLevel` [忽略 Git]）。
3. **統一核心 Runtime SDK (`yscb_core`)**：
   - `core` 模組作為標準建置庫（具備 `source/core/` 與 `build/core/`），提供全模組共用的 `ProjectContext`、`ConfigManager` 與 `Console` 工具類。
4. **統一轉接與極簡起手 (Unified CLI Router & Bootstrap)**：
   - 下游專案僅需單檔 `yscb_cli.py` 與 `yscb_installer.py` 即可統一調度所有模組與安裝管理。
5. **Zero External Dependency (零第三方依賴)**：
   - 全套工具與 SDK 100% 基於 Python 3.8+ 標準庫實現，跨平台免安裝任何第三方套件。

---

## 2. 核心 2 × 2 設定架構矩陣

```text
+-----------------------+----------------------------------+----------------------------------+
| 範疇 \ 生命週期       | Project Level (進 Git 團隊規範)  | User Level (忽略 Git 個人偏好)   |
+-----------------------+----------------------------------+----------------------------------+
| Codebase (全專案基底) | [1] Codebase.ProjectLevel        | [2] Codebase.UserLevel           |
|                       |  - yscb_config.json              |  - yscb_config.local.json        |
|                       |  - 專案路徑綁定 (paths)          |  - 本地模組開發路徑重定向        |
|                       |  - 遠端倉庫與分支 (remote)       |  - 本機私有 Token / Proxy / 偵錯 |
+-----------------------+----------------------------------+----------------------------------+
| Module (特定單一模組) | [3] Module.ProjectLevel          | [4] Module.UserLevel             |
|                       |  - config.project.json           |  - config.local.json             |
|                       |  - 模組專案規範 (plans/docs 路徑)|  - 個人 IDE 偏好 (Gemini/Cursor) |
|                       |  - 專案共用 SOP 規約             |  - 個人指令前綴 / 快顯設定       |
+-----------------------+----------------------------------+----------------------------------+
```

### 多層設定繼承與覆寫優先級 (Cascade Hierarchy)
```text
[優先級由高到低]
1. CLI 即時參數 (Command Flags，如 --prefix sop_)
2. [4] Module.UserLevel (config.local.json)
3. [3] Module.ProjectLevel (config.project.json)
4. [2] Codebase.UserLevel (yscb_config.local.json)
5. [1] Codebase.ProjectLevel (yscb_config.json)
6. 模組內建預設範本 (config.project.template.json)
```

---

## 3. 三層環境架構體系 (Three-Tier Environment)

```text
[1. 工具庫源碼環境: :/ys_codebase/]
  ├── source/core/ (Core SDK 源碼: yscb_core)
  ├── source/<module>/ (模組完整源碼)
  ├── build/core/ & build/<module>/ (最小需求發布物)
  └── yscb_installer.py / yscb_cli.py
         │
         │ (installer build / 驗證)
         ▼
[2. 假專案測試環境: :/test/]
  ├── run_regression.py (一鍵全自動回歸套件)
  ├── tests/test_installer.py (單元與整合測試)
  └── 下游動態沙盒 (E2E 下游專案模擬驗證)
         │
         │ (installer install 發布物)
         ▼
[3. 下游專案 / 自引用 Dogfooding 環境: :/]
  ├── yscb_cli.py & yscb_installer.py
  ├── yscb_config.json (專案核心設定)
  ├── modules/core/ (安裝的 Core SDK 發布物)
  ├── modules/<module>/ (安裝的模組發布物)
  ├── docs/ (專案知識庫)
  └── plans/ (專案 Dev Plans)
```

---

## 4. 模組空間分流與相依規範

| 空間層級 | 路徑 | 角色定位 | 存取與打包規則 |
| :--- | :--- | :--- | :--- |
| **源碼空間 (Source)** | `ys_codebase/source/` | 完整模組原始碼 | 包含全套腳本、範本、開發期配置與測試。若以 `--source` 安裝，自動相依安裝 `source/core/`。 |
| **發布空間 (Build)** | `ys_codebase/build/` | 最小運行發布物 | 由 `installer build` 自動打包產出，過濾快取與測試檔，並在 `manifest.json` 注入 `built_at` 時間戳。 |
| **本地運行空間 (Modules)** | `modules/` | 下游專案執行空間 | 純使用端透過 `installer install` 安裝之空間，包含 `modules/core/` 與各業務模組。 |

---

## 5. Core SDK (`yscb_core`) 引用架構

所有模組皆宣告 `"dependencies": ["core"]`，並透過 `yscb_core` 存取標準工具類：

```text
yscb_core/
├── ProjectContext                  # 自動定位 project_root, yscb_root, module_dir
├── ConfigManager                   # 自動處理 2x2 矩陣設定合併與讀寫
└── Console                         # 統一跨平台終端輸出與日誌風格
```
