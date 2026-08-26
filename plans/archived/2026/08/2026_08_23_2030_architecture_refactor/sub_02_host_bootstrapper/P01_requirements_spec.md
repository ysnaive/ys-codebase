# 需求規格書 (Requirements Specification)

> 功能名稱：超薄宿主單檔實現 (Ultra-Thin Host Bootstrapper)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](../P00_semantic_requirements.md) / [R01](../R01_module_architecture_survey.md), [R02](../R02_yscb_responsibilities.md), [R04](../R04_lifecycle_invocation_flow.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | **原生自舉初始化 (`init`)** | 命令行輸入 `init {yscbRoot} [--provider="<source>"]` | 1. 檢查 `yscb.config.json` 防呆（已初始化則阻斷）。<br/>2. 確保 `yscbRoot` 根目錄存在。<br/>3. 寫入初始 `yscb.config.json`（`yscb_root`, `installed_modules: {}`）。<br/>4. 原生標準庫 HTTP 下載 `core` 純淨發布包至 `mirror://core/{version}/`。<br/>5. 物化部署至 `yscb://modules/core/` 並寫入清冊。<br/>6. 調用 `core` 執行 `RELOAD`。 | 輸出初始化成功訊息與版本資訊 | P00 期望 1 & 包含範疇 1.2；R02 §2.2；R04 §2.1 |
| **FR-02** | **宿主原生自我更新 (`self-update`)** | 命令行輸入 `self-update [--provider="<source>"]` | 1. 原生標準庫 HTTP 檢索遠端最新 `yscb.py` 腳本與雜湊值。<br/>2. 版本比對（已為最新則退出）。<br/>3. 下載至暫存檔並執行 Python 語法驗證。<br/>4. 備份當前 `yscb.py` 為 `.bak` 後原子覆蓋替換。 | 輸出宿主更新成功與最新版本號 | P00 期望 1 & 包含範疇 1.2；R02 §2.2；R04 §3.1 |
| **FR-03** | **Core 7 大套件指令智能自動轉發** | 命令行輸入 7 大 Core 指令之一（`install`, `update`, `remove`, `list`, `status`, `rollback`, `reload`）及其參數 | 1. 識別輸入命令為 Core 套件管理指令。<br/>2. 自動轉發委派至 `modules/core/scripts/cli.py`。<br/>3. 無需使用者手動前綴 `core`（即 `yscb.py install` 自動等同於 `yscb.py core install`）。 | 透傳 `core` 執行結果與 Exit Code | 2026-08-24 增補需求；R02 §3.1；R04 §2 |
| **FR-04** | **泛用模組 CLI 動態派發器** | 命令行輸入 `yscb.py {module} {any}`（目標為任意業務模組名） | 1. 檢查 `yscb.config.json` 是否已初始化。<br/>2. 探測目標模組之 `modules/{module}/scripts/cli.py` 是否存在。<br/>3. 以獨立子進程執行模組 CLI，透傳其餘命令列參數 (`sys.argv[2:]`)。<br/>4. 嚴格維持路徑封裝（不向業務模組傳遞實體路徑字串）。<br/>5. 透傳目標模組之 Exit Code 回終端。 | 透傳模組執行輸出與 Exit Code | P00 期望 1 & 包含範疇 1.3；R02 §2.3；R04 §2.9 |

---

## 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **零外部依賴** | 100% 僅使用 Python 3.8+ 標準庫（`sys`, `os`, `json`, `urllib.request`, `subprocess`, `shutil`, `ast` 等），杜絕任何第三方 Package。 | 於純淨 Python 虛擬環境（無任何 pip 套件）直接運行驗證 |
| **NFR-02** | **超薄體積** | 腳本維持極簡單檔自舉架構，純代碼行數控制在 150 行以內，杜絕單檔膨脹。 | 實體行數靜態檢查（行數統計） |
| **NFR-03** | **跨平台穩定性** | 支援 Windows、Linux 與 macOS 跨平台路徑解析與進程派發，無常駐檔案鎖問題。 | 跨平台檔案 I/O 與路徑標準化測試 |

---

## Edge Cases

| ID | 場景描述 | 預期行為 | 對應 FR |
| :--- | :--- | :--- | :--- |
| **EC-01** | 重複執行 `init`（`yscb.config.json` 已存在有效配置） | 阻斷執行並提示「環境已初始化，請勿重複執行」，避免誤覆蓋現有環境。 | FR-01 |
| **EC-02** | 未初始化即調用模組 CLI 或 Core 指令（`yscb.config.json` 缺失） | 阻斷執行並友善提示「尚未初始化環境，請先執行 yscb.py init <yscbRoot>」。 | FR-03, FR-04 |
| **EC-03** | 目標模組未安裝或缺少 `scripts/cli.py` | 阻斷執行並輸出清晰錯誤「Module '{module}' 未安裝或缺少 scripts/cli.py 進入點」。 | FR-04 |
| **EC-04** | `self-update` 網路異常或下載腳本語法損壞 | 語法驗證失敗立即阻斷，回滾保留原 `yscb.py` 腳本，輸出具體原因。 | FR-02 |
| **EC-05** | `init` 時 `core` 發布包下載中斷或無效 | 清理暫存產物並提示失敗原因，不寫入損壞的 `core` 模組目錄。 | FR-01 |

---

## 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `sop_ext` 清單 | `on_demand` | ❌ 排除 (Excluded) | 本子計畫為純原生宿主自舉器實現，不涉及 SOP 特化擴充 |

---

## Decision Records

### [P01:DR-01] 宿主原生指令集收斂與超薄定位
- **議題**：宿主 `yscb.py` 應包含哪些原生指令？
- **結論**：僅保留 2 項原生指令：`init`（自舉環境與 core）與 `self-update`（宿主自我更新）。其餘所有指令一律委派至模組 `scripts/cli.py`。
- **理由**：落實「宿主極簡自舉逃生艙」原則，將業務與套件管理複雜度完全下放至 `module:core`。

### [P01:DR-02] CLI 派發路徑封裝鐵律
- **議題**：宿主派發至模組 CLI 時如何傳遞參數？
- **結論**：僅透過標準命令列參數透傳，嚴禁向業務模組傳遞或暴露底層實體路徑字串。模組一律透過 `core.uri` SDK 進行語意路徑解算。
- **理由**：確保模組對底層實體路徑 100% 無知，杜絕跨模組硬編碼與路徑脆弱性。

### [P01:DR-03] Core 套件指令直呼與無前綴智能轉發 (Zero-Prefix Core Commands)
- **議題**：使用者調用 Core 套件管理指令時，是否必須每次輸入 `yscb.py core <command>`？
- **結論**：宿主內建 7 大 Core 指令識別清單（`install`, `update`, `remove`, `list`, `status`, `rollback`, `reload`）。若第一參數匹配此清單，自動智能轉發至 `core` 模組（`dispatch('core', argv[1:])`）。同時亦無損相容顯式帶有 `core` 前綴的調用（`yscb.py core install`）。
- **理由**：大幅提升 CLI 開發者體驗（DX），使套件管理指令如同宿主原生般流暢，同時底層仍維持 100% 模組化微內核解耦。
