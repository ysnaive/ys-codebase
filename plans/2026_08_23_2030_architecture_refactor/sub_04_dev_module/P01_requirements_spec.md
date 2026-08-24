# 需求規格書 (Requirements Specification)

> 功能名稱：開發者工具模組 (Dev Developer Tools Module)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](../P00_semantic_requirements.md) / [R01](../R01_module_architecture_survey.md), [R02](../R02_yscb_responsibilities.md)
> 狀態：Confirmed
> 擴充項目：none
> 模板版本：v1.4

---

## 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | **模組腳手架產生器 (`dev create`)** | 模組名稱 `module_name`、描述與作者資訊 | 1. 檢查模組名稱是否符合 Python 識別碼規範。<br/>2. 於 `source/<module>/` 生成標準骨架：`manifest.json`、`scripts/cli.py`、`<module>/__init__.py`、`tests/test_<module>.py`。<br/>3. 初始化合法範例進入點代碼。 | 模組源碼目錄與建立成功回饋 | P00 包含範疇 3.1；R01 §2 |
| **FR-02** | **規範合規檢查器 (`dev check`)** | 目標模組名稱或 `--all` 旗標 | 1. 檢查 `manifest.json` 存在與必要欄位格式。<br/>2. 檢查 `scripts/cli.py` 進入點存在。<br/>3. 執行 Python AST 語法校驗 (`ast.parse`)。<br/>4. 檢查是否有非法硬編碼路徑。<br/>5. 輸出整齊之合規檢查報告。 | 合規檢查報告與狀態碼 (0/1) | P00 包含範疇 3.2；R02 §3.3 |
| **FR-03** | **純淨建置工具 (`dev build`)** | 目標模組名稱或 `--all` 旗標，可選 `--clean` | 1. 先行執行規範檢查（等同 `check`）。<br/>2. 於 `build/<module>/` 建立純淨目錄。<br/>3. 過濾排除 `__pycache__`、`.pyc`、`.tmp` 與暫存檔案。<br/>4. 產出 100% 純淨之模組發布產物。 | `build/<module>/` 純淨建置產物 | P00 包含範疇 3.3；R01 §1 |
| **FR-04** | **VFS 全面整合** | 語意 URI | 所有源碼讀取與建置輸出全面對接 `core.uri` 一級 VFS 操作（`module.source://`, `module.build://`, `temp://`），維持路徑無知性。 | VFS I/O 操作 | P00 包含範疇 2.3；R02 §3.2 |

---

## 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **零外部依賴** | 100% 僅使用 Python 3.8+ 標準庫（`sys`, `os`, `json`, `shutil`, `ast`, `typing`, `re` 等）。 | AST import 掃描驗證 |
| **NFR-02** | **建置純淨度與冪等性** | 建置產物絕不包含任何位元組碼快取 (`.pyc`) 或系統垃圾檔案；重複執行 `build` 結果完全一致。 | 產物目錄掃描比對 |

---

## Edge Cases

| ID | 場景描述 | 預期行為 | 對應 FR |
| :--- | :--- | :--- | :--- |
| **EC-01** | `create` 已存在的模組名稱 | 立即阻斷並報錯「Module already exists」，嚴禁覆蓋現有源碼。 | FR-01 |
| **EC-02** | `create` 非法模組名稱（如包含空格、特殊字元或以數字開頭） | 立即阻斷並提示符合 Python 識別碼規範之模組命名規則。 | FR-01 |
| **EC-03** | `check` 發現 Python 語法錯誤或缺少進入點 | 輸出具體檔案與行號錯誤，並返回非 0 Exit Code。 | FR-02 |
| **EC-04** | `build` 不存在的模組 | 報錯「Source module not found at source/<module>」，終止建置。 | FR-03 |

---

## 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `sop_ext` 清單 | `on_demand` | ❌ 排除 (Excluded) | 本子計畫為開發者工具集 SDK，不涉及業務特化擴充 |

---

## Decision Records

### [P01:DR-01] Dev 模組對 Core 模組之標準相依
- **議題**：`dev` 模組是否應直接依賴 `core`？
- **結論**：`dev` 在 `manifest.json` 中宣告依賴 `core@>=1.0.0`，並全面使用 `core.uri` 進行所有路徑與檔案操作。
- **理由**：驗證模組相依機制，落實模組化分工。

### [P01:DR-02] 純淨建置之過濾原則
- **議題**：`dev build` 應過濾哪些檔案以確保純淨發布？
- **結論**：嚴格過濾 `__pycache__`、`*.pyc`、`*.pyo`、`*.tmp`、`*.bak`、`.git*` 及 IDE 暫存目錄。
- **理由**：確保發布至 `mirror://` 或外部 Provider 的套件 100% 純淨可重現。
