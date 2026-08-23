# 需求規格書 (Requirements Specification)

> 功能名稱：完善版本號系統、相依相容性檢查、鏈式增量遷移與更新覆蓋防護  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md) / [R01_versioning_rigidity_and_progression.md](./R01_versioning_rigidity_and_progression.md) / [R02_version_control_update_and_override_mechanisms.md](./R02_version_control_update_and_override_mechanisms.md)  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
|----|---------|------|------|------|-------------|
| **FR-01** | 純標準庫 SemVer 2.0.0 解析與比較引擎 (`SemVer`) | 版本字串 (如 `"2.1.0"`, `"v1.0.0-beta+exp"`) | 依正規表達式解析 Major/Minor/Patch/Prerelease/Build，支援富比較運算符 (`<, <=, ==, !=, >=, >`) | `SemVer` 物件或解析異常 | P00 情境 1, 情境 2 |
| **FR-02** | 版本相依約束表達式匹配引擎 (`VersionConstraint`) | 版本字串與約束條件 (如 `"core >= 2.0.0"`, `"^1.2.0"`, `"~1.1.0"`, `*`) | 支援精確比對、區間比對、Caret(`^`)、Tilde(`~`) 與萬用字元解析與比對 | `bool` (是否滿足約束) | P00 情境 2 |
| **FR-03** | 全專案全模組版本狀態矩陣查詢 CLI (`version status`) | 執行 `python yscb_cli.py version status` | 掃描所有模組之【源碼版本】(`source/`)、【建置版本】(`build/`) 與【安裝版本】(`modules/`) | 終端輸出 Markdown 表格，標註同步狀態 (`[SYNCED]`, `[OUTDATED]`, `[NOT_INSTALLED]`) | P00 情境 1 |
| **FR-04** | 一鍵檢查可用更新 CLI (`version check-update`) | 執行 `python yscb_cli.py version check-update` | 比對遠端/源碼最新版本與本機安裝版本 | 終端輸出可用更新清單、變更級別 (Patch/Minor/Major) 與 Migration 需求提示 | P00 情境 1 |
| **FR-05** | SemVer 剛性版本遞進 CLI (`version bump`) | 模組名稱與 Bump 級別 (`major / minor / patch`) | 依專案適配公理（Major: 典範轉移, Minor: 資料格式變更, Patch: 日常功能與修復）遞進 `source/<module>/manifest.json` 版本 | 更新 `manifest.json` 並回傳新版本號 | P00 情境 1 |
| **FR-06** | 模組相依性相容約束安裝防呆 | 執行 `yscb_installer.py install` / `build` 或 `python yscb_cli.py version check` | 比對當前已安裝/已建置相依模組版本是否滿足 `manifest.json` 之 `dependencies` 約束 | 滿足則放行；不相容時中止並輸出明確衝突與修復指引 | P00 情境 2 |
| **FR-07** | 三大資產分級安全覆蓋與範本增量合併 | 執行模組安裝 / 升級 / 強制覆寫 (`install --force`) | ① 純代碼產物 100% 冪等原子覆蓋<br>② `config.project.json` 採 `deep_merge(template, user_config)` 增量合併（保留自訂值、注入新欄位預設值）<br>③ `config.local.json` 唯讀保留<br>④ `AGENTS.md` 標記軟合併 | 安全完成覆蓋，下游專案自訂設定與規範無損保留 | P00 情境 3 |
| **FR-08** | 鏈式線性增量遷移框架 (`MigrationRunner`) | 呼叫 `_migration.py <old_version> <new_version>` | 模組以 `@runner.step("1.1.x")` 註冊 Minor 代際步階，按 `old_ver < step_base <= new_ver` 依序循序執行 step handlers | 成功完成資料遷移；任一步階失敗立即拋錯中斷 | P00 情境 4 |
| **FR-09** | 五階段事務性安全升級與快照回滾 | 執行 `installer upgrade` 或 `version update` | 執行 Pre-flight -> Snapshot Backup -> Protected Merge -> Migration -> Finalize 流水線；若 Migration 失敗立即觸發 Rollback | 成功完成升級，或失敗時 100% 還原舊版快照並提示錯誤原因 | P00 情境 4, R02 |
| **FR-10** | 抽象外掛式擴充稽核機制 (`verify_plan.py` Hook) | 執行 `python yscb_cli.py agents-workflow verify` | 通則讀取 Plan Header `> 擴充項目：`，動態掃描並調用 `sop_ext://<ext_name>_verify.py`；本專案落地 `extensions/dogfooding_pipeline_verify.py` 負責本地發布版本遞增守門 | 通則保持 100% 純淨解耦，特化擴充自動完成版本發布合規檢查 | P00 情境 5, `[REQ:DR-01]` |

---

## 2. 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
|----|------|---------|---------| 
| **NFR-01** | 零外部依賴 | 核心 SDK、SemVer 引擎、MigrationRunner 與 Installer 必須 100% 使用 Python 3.8+ 標準庫（`urllib`, `pathlib`, `json`, `shutil`, `re`, `subprocess`, `unittest`），嚴禁第三方 pip 套件。 | 靜態掃描 imports、乾淨無外部 pip 環境執行驗證。 |
| **NFR-02** | 跨平台與 Windows 安全 | 全面使用 UTF-8 編碼保護與 `errors='replace'`，處理路徑時考量 Windows 長路徑與權限鎖定，避免終端 `UnicodeEncodeError` 或崩潰。 | 於 Windows PowerShell / CMD 環境實機執行測試。 |
| **NFR-03** | 冪等性與原子性 | 重複執行 `version sync` 或 `install` 不產生非預期副作用；升級失敗時透過 Snapshot 回滾機制確保專案目錄不處於半損壞狀態。 | 模擬 Migration 中斷測試回滾完整性。 |

---

## 3. 邊界條件 (Edge Cases)

| ID | 場景描述 | 預期行為 | 對應 FR |
|----|---------|---------|--------|
| **EC-01** | 輸入非法的版本字串（如 `"1.a.2"`, `""`, `None`） | 拋出明確的 `ValueError` 或自訂 `InvalidVersionError`，提示正確 SemVer 格式。 | FR-01 |
| **EC-02** | 版本字串帶有 `v` 前綴（如 `"v2.1.0"`）或空白 | 自動寬容去除前綴 `v` 與首尾空白，安全解析為標準 SemVer。 | FR-01 |
| **EC-03** | 短格式版本字串（如 `"1.0"`） | 寬容解析補齊為 `"1.0.0"`，保持最大相容性。 | FR-01 |
| **EC-04** | 相依模組未安裝或版本約束不滿足（如相依 `"core >= 2.0.0"` 但本機僅裝 `"1.9.0"`） | `installer` 安裝或 `version check` 立即阻斷，輸出清晰錯誤訊息指出衝突模組與版本缺口。 | FR-02, FR-06 |
| **EC-05** | 升級時 `_migration.py` 執行拋出異常或返回非 0 狀態碼 | 立即終斷升級流水線，自動從 `.yscb_cache/backup/` 快照恢復舊模組目錄，印出詳細 Traceback。 | FR-08, FR-09 |
| **EC-06** | 跨越多個 Minor 代際升級（如 `1.0.0` ➔ `1.3.0`） | 鏈式增量執行器依序執行 `Step(1.1.x) ➔ Step(1.2.x) ➔ Step(1.3.x)`，不跳步、不遺漏。 | FR-08 |
| **EC-07** | 下游專案已自訂 `config.project.json` 且新版範本追加了新欄位 | 增量合併後，自訂欄位完整保留，新欄位預設值順利注入，無同名沖刷。 | FR-07 |
| **EC-08** | Plan 宣告了不存在對應 `_verify.py` 的 Extension | `verify_plan.py` 抽象 Hook 安全略過，不阻斷其他通用合規檢查。 | FR-10 |

---

## 4. 專案擴充特化判定矩陣 (Extension Specialization Matrix)

> 執行 `python yscb_cli.py agents-workflow ext list` 盤點 `sop_ext://` 下所有可用擴充：

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `dogfooding_pipeline_ext` | `always` | ✅ **納入 (Included)** | 本專案為 Dogfooding 自引用架構，本次計畫修改 `core`、`installer` 與 `agents-workflow` 源碼與發布守門，必須遵循四步閉環流水線，並建立 `dogfooding_pipeline_verify.py` 進行發布版本守門。 |

> **標頭宣告同步**：頂部 Header 已宣告 `> 擴充項目：dogfooding_pipeline_ext`。

---

## 5. 外部研究與調研結論摘要

| 主題 | 關鍵發現 / 結論 | 來源 | 可信度 |
|------|----------------|------|--------|
| **SemVer 專案適配公理** | Major (全域心智/典範轉移)、Minor (需 Migration 之結構變更)、Patch (日常功能遞增與修復)。 | [R01_versioning_rigidity_and_progression.md](./R01_versioning_rigidity_and_progression.md) | 高 |
| **資產分級保護與事務升級** | 純代碼原子覆蓋、配置增量深層合併、文檔標記軟合併；Stage 1~5 升級流水線 + 快照回滾。 | [R02_version_control_update_and_override_mechanisms.md](./R02_version_control_update_and_override_mechanisms.md) | 高 |
| **鏈式線性增量遷移** | `@runner.step("1.1.x")` 按代際排序線性執行，達到 $O(N)$ 線性維護複雜度與確定性。 | [R02_version_control_update_and_override_mechanisms.md](./R02_version_control_update_and_override_mechanisms.md) | 高 |
| **外掛式擴充稽核解耦** | 通則 `verify_plan.py` 抽象調用 `sop_ext://<ext>_verify.py`，專案特化落地 `dogfooding_pipeline_verify.py`。 | `[REQ:DR-01]` / Phase 0 決策 | 高 |

---

## 6. Decision Records

### `[REQ:DR-01]`: 外掛式擴充稽核機制 (Pluggable Extension Verifier)
- **議題**：如何在本地開發發布時確認模組已正確遞增版本號，同時不污染通用 SOP 模組 (`agents-workflow`)？
- **結論**：採用「通則動態外掛 Hook (`verify_plan.py`) + 專案特化腳本 (`extensions/dogfooding_pipeline_verify.py`)」完全解耦架構。
- **理由**：通則維持 100% 零業務特化代碼，可安全分發至任何下游專案；專案特化邏輯 100% 隔離於 `extensions/` 資料夾內。
- **排除方案**：直接在 `verify_plan.py` 寫死 `dogfooding_pipeline_ext` 檢查（造成特化污染通則，破壞下游通用性）。
