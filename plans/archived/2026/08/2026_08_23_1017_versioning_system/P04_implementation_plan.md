# 最終實作計畫書 (Implementation Plan)

> 功能名稱：完善版本號系統、相依相容性檢查、鏈式增量遷移與更新覆蓋防護  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 交叉驗證與架構檢核 (Cross-Verification Checklist)

- [x] **FR 對齊**：P01 每個功能需求 (`FR-01 ~ FR-10`) 在 P03 均有對應的介面與函式簽名。
- [x] **EC 防護**：P01 每個 Edge Case (`EC-01 ~ EC-08`) 在 P03 均有明確的防禦/錯誤與回滾策略。
- [x] **架構一致**：P02 變更清單與 P03 類別、命名空間一致，依賴拓撲無環形依賴。
- [x] **規範約束**：100% 遵守 Zero External Dependency 公理，全面採用 UTF-8 編碼與 Windows 安全防護。
- [x] **Extension 注入**：Phase 1 納入之 `dogfooding_pipeline_ext` 已轉化為實作任務與測試驗證項目。

---

## 2. 靈魂拷問 (Stress Test)

### Q1: 在跨版本升級 (如 `1.0.0 ➔ 1.3.0`) 執行鏈式增量遷移時，若前兩個 step (`1.1.x`, `1.2.x`) 已經修改了專案部分檔案，而第三個 step (`1.3.x`) 執行失敗，如何保證專案狀態 100% 徹底乾淨還原？
**回答**：
在進入 Stage 3/4 任何檔案覆寫或 migration 之前，Stage 2 建立整組目標模組目錄與專案既有配置之完整 Snapshot 快照備份（存放於 `.yscb_cache/backup/<mod>_<old_ver>_<timestamp>/`）。一旦 Stage 4 執行過程捕獲任何例外或 returncode != 0，立即調用 `rollback_snapshot()`，將整個目標目錄與配置檔案原子覆蓋還原至升級前狀態，確保升級具備 All-or-Nothing 事務性。

### Q2: 既有模組 `manifest.json` 若僅寫 `"dependencies": ["core"]`（無版本號），新約束解析器如何處理？
**回答**：
`VersionConstraint.parse_dependency_spec()` 採用寬容向下相容設計：當未檢測到版本運算符時，自動將約束解析為萬用字元 `*`（任意版本皆相容），既有模組無需強制重寫即可平滑相容。

---

## 3. 實作順序 (按依賴拓撲排序)

| 順序 | 實作項目 | 變更檔案與目標 | 品質驗證方式 |
|:---:|:---|:---|:---|
| **1** | **SemVer 2.0.0 & Constraint 引擎** | `[NEW]` `source/core/scripts/semver.py`<br>實作 `SemVer` 與 `VersionConstraint` 類別。 | 單元測試 `test_semver.py` (涵蓋 FT-01, FT-02, ET-01~04, PT-01)。 |
| **2** | **鏈式線性增量遷移框架** | `[NEW]` `source/core/scripts/migration.py`<br>實作 `MigrationRunner` 裝飾器與執行器。 | 單元測試 `test_migration.py` (涵蓋 FT-08, EC-06)。 |
| **3** | **Core SDK 接口導出與 Context 擴充** | `[MOD]` `source/core/scripts/yscb_core.py`, `__init__.py`<br>導出新類別，實作 `ProjectContext.get_module_version()`。 | Import 測試與 SDK 接口簽名驗證。 |
| **4** | **Installer 5 階段事務升級與相依約束檢查** | `[MOD]` `yscb_installer.py`<br>實作 `check_module_dependencies`、快照備份、增量合併與 Rollback。 | 單元測試與 E2E 升級回滾測試 (FT-06, FT-07, FT-09, EC-05, EC-07)。 |
| **5** | **CLI 路由器版本子指令擴充** | `[MOD]` `source/core/scripts/cli.py`, `yscb_cli.py`<br>新增 `version status`, `version check-update`, `version bump`, `version check`。 | 實機命令列測試 (FT-03, FT-04, FT-05, UX-01, UX-02)。 |
| **6** | **verify_plan 抽象外掛式 Hook 實作** | `[MOD]` `source/agents-workflow/scripts/verify_plan.py`<br>實作 `sop_ext://<ext>_verify.py` 動態掃描調用。 | 驗證測試 (FT-10, ET-05)。 |
| **7** | **專案特化發布守門腳本與 SOP 擴充** | `[NEW]` `extensions/dogfooding_pipeline_verify.py`<br>`[MOD]` `extensions/dogfooding_pipeline_ext.md`<br>實作版本遞增、三態一致性檢查。 | 實機調用驗證發布守門 (FT-10)。 |
| **8** | **全套迴歸測試與 Dogfooding 閉環** | `[NEW]` `test/tests/test_semver.py`, `test/tests/test_migration.py`<br>`[MOD]` `test/run_regression.py`<br>執行 Stage 1~4 Dogfooding 閉環。 | `python test/run_regression.py` 100% Passed。 |

---

## 4. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 判定依據 (P03/P05/P06 錨點) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
|:---|:---|:---|:---|
| `P03: SemVer API & 約束語法` | 維度 3 (中觀動態機制) | `docs/Core/SEMVER.md` | `[NEW]` SemVer 2.0.0 解析比較、富運算符、約束表達式 (`^`, `~`, `>=`, `<=`, `==`, `*`) 使用指南與範例。 |
| `P03: MigrationRunner 框架` | 維度 3 (中觀動態機制) | `docs/Core/MIGRATION_FRAMEWORK.md` | `[NEW]` 鏈式線性增量遷移 `@runner.step("1.1.x")` 實作標準、演算法流程與 Rollback 復原機制。 |
| `P05: CLI & 5 階段升級流水線` | 維度 6 (人因操作引導) | `docs/Installer/README.md` | `[MOD]` 補充 `version status/bump/check-update` CLI 操作手冊與 5 階段升級流程圖。 |
| `P01: 專案適配 SemVer 公理` | 維度 1 (領域概念模型) | `docs/_project/STANDARDS.md` | `[MOD]` 寫入專案適配三級版本定義（Major: 典範轉移, Minor: 需 Migration 結構變更, Patch: 日常功能與修復）。 |
| `P05: 事務快照與回滾機制` | 維度 5 (工程妥協與暗角) | `docs/Core/DESIGN_NOTES.md` | `[MOD]` 登記 `DN-04` 寬容版本解析與 `DN-05` 升級快照備份與 Rollback 事務防護。 |

---

## 5. 關鍵決策速查 (Decision Records Reference)

- **`[REQ:DR-01]`**：外掛式擴充稽核機制 (Pluggable Extension Verifier)：通則 `verify_plan.py` 抽象調用 `sop_ext://<ext>_verify.py`，專案特化 `dogfooding_pipeline_verify.py` 負責版本發布防呆。
- **`[ARCH:DR-01]`**：純標準庫自研 SemVer 與 Constraint 引擎，100% 貫徹 Zero External Dependency。
- **`[API:DR-01]`**：相依表達式寬容語法支援純名稱與比較運算符直接切分，保障向後相容。
