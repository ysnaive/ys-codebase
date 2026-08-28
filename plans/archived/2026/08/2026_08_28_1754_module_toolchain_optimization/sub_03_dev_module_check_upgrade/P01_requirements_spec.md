# 需求規格說明書 (Requirements Specification)

> 功能名稱：Dev 模組狀態檢核工具升級 (Dev Module Check & Diagnostics Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_03)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 需求背景與核心目標 (Background & Goals)

隨著 YS-Codebase 模組化生態系演進至「自引用 (Dogfooding)」三層空間體系，既有的 `dev check` 工具僅涵蓋基礎 AST 語法與 `manifest.json` 基本欄位，缺乏針對 Contributes 注入、Configurable 模板標準、空間穿透防禦、以及反模式（如手寫繞過 SDK 讀取組態或 contributes 快取）的靜態架構守門機制。

本規格書將 `P00` 收斂之 7 大決策轉譯為具備剛性追溯性之功能需求清冊 (FR-01~07)、非功能需求 (NFR-01~03) 與邊界條件 (EC-01~03)。

---

## 2. 功能需求清冊 (Functional Requirements)

| 需求 ID | 需求名稱 | 追溯 P00 DR | 嚴重等級 | 需求詳細說明 |
| :--- | :--- | :---: | :---: | :--- |
| **FR-01** | **Manifest 完整性與 Core 依賴強制性** | `[sub_03:P00:DR-01]` | `[FAIL]` | 檢查 `manifest.json` 是否包含 `name`, `version`, `entry`, `dependencies`。`version` 必須符合 SemVer；`name` 必須與模組資料夾一致；`dependencies` 必須包含 `core` 模組（`core` 本體除外）。 |
| **FR-02** | **Core 注入完備性檢核** | `[sub_03:P00:DR-02]` | `[WARN]` | 檢查模組是否包含 `contributes/core.json`，並檢查是否宣告了 `commands`（CLI 指令）或 `uri_schemes` 協議。未具備時提示提醒。 |
| **FR-03** | **空間穿透防禦 (Zero Probing)** | `[sub_03:P00:DR-03]` | `[FAIL]` | 全量掃描模組內 `.py` 檔案，嚴禁出現 `module.source://` 或硬編碼 `source/` 等源碼空間路徑（`dev` 模組構建/檢查工具本身除外）。 |
| **FR-04** | **三級嚴重度與 Release 阻斷** | `[sub_03:P00:DR-04]` | 系統級 | 檢查結果以 `[PASS]`、`[WARN]`、`[FAIL]` 標註。當存在任何 `[FAIL]` 時，剛性阻斷 `dev release` 打包流程；但仍允許 `dev build` 以利開發調試。 |
| **FR-05** | **檔案結構與 Configurable 模板規範** | `[sub_03:P00:DR-05]` | `[FAIL]` / `[WARN]` | 進入點 `scripts/cli.py` 必須存在 (`[FAIL]`)；測試類別必須繼承 `YSCBTestCase` (`[FAIL]`)；預設組態模板必須置於 `configurable/`，**嚴禁模組根目錄散落 `config.*.json`** (`[FAIL]`)；殘留暫存檔 (`[WARN]`)。 |
| **FR-06** | **文檔合規檢查** | `[sub_03:P00:DR-06]` | `[WARN]` | 檢查模組目錄是否具備 `contributes.format.md` 規格手冊，未提供時列為 `[WARN]` 提醒。 |
| **FR-07** | **反模式靜態靶向攔截** | `[sub_03:P00:DR-07]` | `[FAIL]` | 靶向檢測非 `core` 模組業務代碼中出現 `"config.project.json"` / `"config.local.json"` 或 `"contributes.merged.json"`，提示改用 `core.config` 或 `core.contributes` SDK；放行一般原生 I/O。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求 ID | 維度 | 指標與約束 |
| :--- | :--- | :--- |
| **NFR-01** | **效能指標** | 單一模組完整 AST 與結構檢核耗時 $\le 100\text{ms}$，全生態系全量檢核 $\le 500\text{ms}$。 |
| **NFR-02** | **診斷輸出體驗** | 終端清晰展示 `[PASS]` (綠)、`[WARN]` (黃)、`[FAIL]` (紅)，並附帶檔案路徑與行號 (`file.py:line`)。 |
| **NFR-03** | **機器可讀支援** | `dev check` 支援 `--json` 參數輸出結構化診斷結果，以利 CI 與自動化腳本解析。 |

---

## 4. 邊界條件與例外處理 (Edge Cases)

| 邊界 ID | 邊界情境 | 防禦與處置行為 |
| :--- | :--- | :--- |
| **EC-01** | **Python AST 語法損毀** | 若 `.py` 檔案存在 `SyntaxError`，捕獲例外並記錄行號與錯誤訊息，標記為 `[FAIL]`，不導致 Checker 程序崩潰。 |
| **EC-02** | **白名單與測試目錄豁免** | `source/core/` 模組本體與各模組之 `tests/` 單元測試目錄完全豁免 FR-07 反模式檢驗與 FR-01 core 自身依賴檢驗。 |
| **EC-03** | **模組不存在或非目錄** | 傳入無效模組名稱時，輸出明確錯誤訊息並回傳 exit code 1，不拋出未捕獲例外。 |
