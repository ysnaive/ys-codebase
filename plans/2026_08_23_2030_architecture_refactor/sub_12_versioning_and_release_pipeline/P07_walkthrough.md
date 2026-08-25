# 變更摘要 (Walkthrough)

> 功能名稱：四段式版本號、雙軌來源庫 (Build vs Release)、三層安裝降級鏈、發布流水線與 Migration 機制重構  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述

本次開發全面落實了 R01~R03 調研與設計方案，實現了四段式語意化版本、雙軌套件來源庫、三層安裝降級鏈、全黑盒測試流水線、模組增量資料遷移與發布交易防護：
1. **四段式語意化版本 (`core.semver`)**：支援 `(major, minor, patch, revision)` 解析與正規化，前三段數值比大小（`1.10.0.0 > 1.9.0.0`），尾號 `revision` 支援微小修訂號或 `build` 本地標籤，日常三元版本常態安裝。
2. **雙軌來源庫架構 (`build://` vs `release://`)**：
   - `build/` (開發庫)：`dev build` 產出完整包（包含 `tests/`，版本強制為 `X.Y.Z.build`），供全黑盒測試直接解析與安裝。
   - `release/` (發布庫)：`dev release` 產出純淨發布包（排除 `tests/`），針對同 `X.Y.Z` 實施單一最新 Revision 淘汰清理。
3. **三層安裝降級鏈 (`build://` ➔ `mirror://` ➔ `provider`)**：依序滿足本地開發即時測試、離線快取與遠端發布庫解析，三層同構維護 `index.json`。
4. **模組增量遷移階梯調用引擎 (`act_migrate`)**：升級時依序遞增調用 `scripts/migrations/{minor}.x.py` 增量腳本，缺腳本自動靜默跳過，失敗自動 Snapshot 原子回滾。
5. **Dev Releaser 發布安全交易防護 (`dev release`)**：Pre-flight 4 大守門、Version Bump、純淨打包、智慧 Git Tag（Major/Minor 自動打 Tag，Patch/Revision 預設不打）與失敗 100% 原子回滾。
6. **運行空間純粹化與自治忽略**：模組物化安裝後自動剝除 `modules/` 內的 `config.*.json` 模板；`init` 自動生成 `yscb://.gitignore` 確保專案根目錄零污染。全量測試 70/70 項 100% Passed。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
|---------|:-------:|------|
| `ys_codebase/source/core/core/semver.py` | Modify | 升級為四段式 SemVer 解析、比大小、自動補齊、範圍約束與 `bump_version` |
| `ys_codebase/source/core/core/uri.py` | Modify | 註冊 `release://`, `release.root://`, `build://`, `storage://` 與雙軌來源庫協議 |
| `ys_codebase/source/core/core/engine.py` | Modify | 實作三層降級鏈依賴求解、Snapshot 擴充至 storage、`act_migrate` 增量階梯調用與 modules 純粹化 |
| `ys_codebase/source/core/core/installer.py` | Modify | 實施同 Major 升級鎖定原則與 Migration 階梯調用觸發 |
| `ys_codebase/source/dev/dev/builder.py` | Modify | `build_module` 打包含 tests 的 `X.Y.Z.build`；`package_release` 純淨打包與同 X.Y.Z 淘汰清理 |
| `ys_codebase/source/dev/dev/releaser.py` | Add | 實作 Pre-flight 4 大守門、Version Bump、純淨打包、智慧 Git Tag 與發布交易原子回滾 |
| `ys_codebase/source/dev/dev/tester.py` | Modify | 測試前自動執行 Hermetic dev build，沙盒內透過三層鏈黑盒測試 |
| `ys_codebase/source/dev/scripts/cli.py` | Modify | 接入 `dev release` 子指令 |
| `yscb.py` | Modify | 宿主自舉判定官方開發端 vs 第三方端，`init` 自動生成 `yscb://.gitignore` |
| `ys_codebase/source/core/tests/test_semver_v4.py` | Add | 四段式 SemVer 單元測試套件 |
| `ys_codebase/source/core/tests/test_migration_ladder.py` | Add | Migration 階梯調用單元測試套件 |
| `ys_codebase/source/dev/tests/test_release_pipeline.py` | Add | 發布流水線與打包單元測試套件 |
| `docs/core/SEMVER.md` | Modify | 升級為四段式版本規範說明書 (維度 3) |
| `docs/core/MIGRATION_LADDER.md` | Add | 模組增量資料遷移與階梯調用手冊 (維度 3) |
| `docs/core/DESIGN_NOTES.md` | Modify | 登記 `DN-09` (單一 Revision 淘汰)、`DN-10` (同 Major 鎖定) 與 `DN-11` (modules 純粹化) (維度 5) |
| `docs/dev/RELEASE_PIPELINE.md` | Add | 開發者工具模組發布流水線手冊 (維度 3) |
| `docs/dev/testing_guide.md` | Modify | 更新高階測試指令與全黑盒流水線說明 (維度 3) |
| `CHANGELOG.md` | Modify | 登記全域版本發布歷史摘要 (sub_12) |
| `plans/2026_08_23_2030_architecture_refactor/umbrella_overview.md` | Modify | 更新主計畫 sub_12 狀態為 Completed |

---

## 3. 測試與品質驗證結果

- **自動化測試**：`python yscb.py dev test --all` 實機執行 **70/70 項單元與整合測試 100% Passed**。
  - `core` 模組：44/44 Passed（Auto-Contract 3/3 + Custom Tests 41/41）
  - `dev` 模組：26/26 Passed（Auto-Contract 3/3 + Custom Tests 23/23）
- **雙軌建置與發布純淨性驗收**：
  - `build/` 目錄保留 `tests/`，版本為 `*.build`。
  - `release/` 目錄 100% 排除 `tests/` 與開發檔案，同 `X.Y.Z` 僅存單一最新 Revision。
- **運行空間驗證**：`modules/` 運行端目錄純淨無 `config.*.json` 殘留。
- **UX / 手動驗證**：開發者實機審閱、執行環境遷移與 commit 斷點保護，核准通過。
- **回歸測試耗時**：~6.7s。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

> 依據 P04 預排之文檔計畫，1:1 核對實際產出與更新的 `docs/` 文件：

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| `docs/core/SEMVER.md` | ✅ 已更新 | 四段式 SemVer 格式、前三段比大小、數值 vs build 比較、自動補齊 | P03 §1, P05 TASK-01, P06 FT-01 |
| `docs/core/MIGRATION_LADDER.md` | ✅ 已新建 | 增量遷移階梯調用原則、目錄結構、缺腳本跳過、同 Major 鎖定與 Snapshot 回滾 | P03 §4, P05 TASK-04, P06 FT-08, ET-04~06 |
| `docs/core/DESIGN_NOTES.md` | ✅ 已更新 | 登記 `DN-09` (單一 Revision 淘汰)、`DN-10` (同 Major 鎖定) 與 `DN-11` (modules 純粹化) | P05 TASK-01~05, P06 FT-02 |
| `docs/dev/RELEASE_PIPELINE.md` | ✅ 已新建 | Pre-flight 4 大守門、5 步發布流水線、智慧 Git Tag 矩陣與交易原子回滾 | P03 §5, P05 TASK-06, P06 FT-06~07, ET-02~03 |
| `docs/dev/testing_guide.md` | ✅ 已更新 | 高階 `dev test` 全黑盒流水線、自動 dev build 與三層鏈解析手冊 | P03 §6, P05 TASK-07, P06 FT-05 |
| `CHANGELOG.md` | ✅ 已更新 | 登記全域高階變更歷史（sub_12 四段式版本與發布流水線） | 全功能 |

---

## 5. 推薦 Commit 訊息

```text
feat(core,dev): implement 4-segment semver, dual-track providers, release pipeline, and migration ladder

- Implement 4-segment SemVer (major.minor.patch.revision) in core.semver with 3-segment auto-normalization
- Expand URI schemes with release://, release.root://, build://, storage:// in core.uri
- Establish dual-track providers: build:// for complete dev builds and release:// for clean release packages
- Implement 3-tier installation resolution chain (build:// -> mirror:// -> provider) in core.engine
- Add incremental migration ladder subsystem (act_migrate) with atomic snapshot rollback in core.engine
- Enforce major boundary upgrade lock in core.installer
- Implement dev.releaser pipeline with Pre-flight 4 gates, version bump, smart git tag matrix, and transaction rollback
- Purge config templates from modules runtime space upon reconciliation
- Generate yscb://.gitignore automatically on init for host zero pollution
- Deliver 100% 7-dimension documentation across docs/ (SEMVER, MIGRATION_LADDER, RELEASE_PIPELINE, DESIGN_NOTES)
- Pass 100% full regression tests (70/70 passed)
```
