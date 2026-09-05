# 需求規格說明書 (Requirements Specification)

> 功能名稱：yscb_venv_core  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 私有微環境隔離空間管理 (`core.pip_manager`) | 實作 `PipManager`，管理 `yscb.venv://`（即 `yscb://.venv/`）空間；依當前運行之 Python 大小版本（`py{major}{minor}`，如 `py310`、`py311`、`py312`）分層建立獨立微環境，強制 `include-system-site-packages = false`，達成零全域污染。 | P0 | [P00:DR-01]<br/>[P00:DR-02] |
| **FR-02** | Wheel-Only 靜默安裝引擎 | `PipManager` 提供 `install_packages(specs)` 介面，調用微環境內之 `pip` 並強制附加 `--only-binary=:all:`、`--no-warn-script-location`、`--quiet` 等安全參數；安裝失敗不崩潰，拋出結構化 `PipInstallError`。 | P0 | [P00:DR-01]<br/>[P00:DR-04] |
| **FR-03** | `manifest.json` 依賴解析與安裝器對接 | `core.installer` 擴充支援解析模組 `manifest.json` 之 `"pip_dependencies": { "pkg": ">=ver" }` 宣告；於 `install`、`update` 與 `restore` 時收集已安裝模組之依賴聯集，自動調用 `PipManager` 進行靜默物化。 | P0 | [P00:DR-04] |
| **FR-04** | 宿主啟動動態注入 (`yscb.py`) | `yscb.py` 於同進程分發指令前，自動探測當前 Python 版本對應之微環境 `site-packages` 目錄，若存在且未注入則動態插入 `sys.path` 前端，使生態系模組可直接無感 `import` 私有依賴。 | P0 | [P00:DR-03] |
| **FR-05** | 空間協議定義與 Git 忽略 | 於 `core.uri_resolver` 註冊 `yscb.venv://` 語意空間協議（實體解析指向 `yscb://.venv/`）；於 `docs/_project/STANDARDS.md` 增補該協議並標記 `🚫 忽略`；於 `yscb://.gitignore` 內部維護標記區塊軟合併生成 `/.venv/` 忽略規則。 | P0 | [P00:DR-02] |
| **FR-06** | 模組安裝自動感知與具明確標示之可復原 IDE 軟合併 | 於模組安裝/更新/還原 (`install` / `update` / `restore`) 流程中，自動探測 `project://.vscode` 目錄是否存在：<br/>1. 若不存在則完全靜默略過，絕不主動創建目錄；<br/>2. 若目錄存在，比照 `internal yscb gitignore` 標記防護哲學，以具備**明確標示（如 `_yscb_managed` 宣告式清冊結構）之非破壞性軟合併**更新 `project://.vscode/settings.json`（增量合併 `python.analysis.extraPaths` 與 `python.defaultInterpreterPath`），保留使用者自訂項，且支援依標示清冊進行 100% 無損精準復原與舊路徑清理。 | P1 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 本機 Python 環境缺少 `ensurepip` 或 `venv` | 捕獲建立微環境失敗異常，輸出友善提示（例如提示安裝 `python3-venv`），不引發未預期崩潰。 |
| **EC-02** | 目標套件無預編譯 Wheel（純源碼包需 C 編譯器） | 因 `--only-binary=:all:` 旗標而失敗時，捕獲日誌並明確提示套件缺失 Pre-built Wheel，阻止本機執行高風險編譯。 |
| **EC-03** | 跨 Python 版本切換執行 (如 3.10 ➔ 3.11) | 依 `py{major}{minor}` 自動分流至獨立子目錄（`py310/`、`py311/`），彼此隔離，杜絕 ABI 衝突與共享破壞。 |
| **EC-04** | `project://.vscode` 存在既有使用者設定或過期 YSCB 路徑 | 透過 `_yscb_managed` 明確標記區塊進行差集運算：僅更新或移除曾由 YSCB 注入之路徑，絕不覆蓋、刪除或修改使用者自訂之任何項目；若模組卸載可按標記乾淨復原。 |
| **EC-05** | 離線或無網路環境執行 `install` / `restore` | 若模組依賴已在微環境中安裝且版本相容，跳過網路請求；若缺失且無網路，記錄錯誤日誌並確保純 Python 核心功能不受破壞。 |
| **EC-06** | 跨作業系統路徑拓撲差異 (POSIX vs Windows) | 微環境結構抽象化：POSIX 為 `bin/python` 與 `lib/python{X}.{Y}/site-packages`；Windows 為 `Scripts/python.exe` 與 `Lib/site-packages`，程式碼統一路徑適配。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 安全性 / 零全域污染 | 所有 pip 相依性 100% 局限於 `yscb.venv://`（`ys_codebase/.venv/`），本機全域 Python 環境零寫入、零干擾。 |
| **NFR-02** | 核心相容性 (Zero-Pip for Core) | `core` 核心模組自身 100% 依賴 Python 原生標準庫，開箱即用，無任何外部 pip 前置依賴需求。 |
| **NFR-03** | 啟動與分發效能 | `yscb.py` 啟動嗅探微環境與動態注入 `sys.path` 耗時 $< 0.1\text{ms}$；安裝時自動感知探測與可復原軟合併投影耗時 $< 5\text{ms}$。 |
| **NFR-04** | Git 歷史純淨性 | `yscb.venv://` 目錄 100% 納入 `yscb://.gitignore` 內部標記區塊自動忽略，嚴禁任何依賴或快取產物入庫。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 跨平台 venv 目錄差異**：
  POSIX 系統（Linux/macOS）之 `site-packages` 位於 `lib/python{major}.{minor}/site-packages`，二進位檔位於 `bin/`；Windows 系統之 `site-packages` 位於 `Lib/site-packages`，二進位檔位於 `Scripts/`。路徑計算需由專門工具方法統一封裝。
- **`[!CAUTION]` Wheel-Only 強制隔離禁令**：
  調用 pip 安裝時必須強制附加 `--only-binary=:all:` 與 `--no-warn-script-location`，杜絕任何可能在使用者端觸發 C/C++ 原始碼編譯（如 setuptools/gcc/clang 缺失）導致的終端掛起或建置崩潰。
- **`[!NOTE]` 明確標記與可復原軟合併防護**：
  IDE 投影嚴格以 `project://.vscode` 實體存在為前提，且在 `settings.json` 內部比照 `internal yscb gitignore` 哲學建立顯式標記清冊（`_yscb_managed`），確保任何注入均「可識別、可追溯、可精準復原、零污染」。
