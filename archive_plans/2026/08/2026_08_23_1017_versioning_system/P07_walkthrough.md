# 變更摘要 (Walkthrough)

> 功能名稱：完善版本號系統、相依相容性檢查、鏈式增量遷移與更新覆蓋防護  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 變更概述

本次開發為 `ys-codebase` 建立了完整的工業級語意化版本與安全升級體系：
1. **SemVer 2.0.0 & 相依約束引擎**：純標準庫實現 SemVer 解析、優先級富比較、剛性 bump 與 `^, ~, >=, <=, ==, !=, *` 相依約束表達式。
2. **鏈式線性增量遷移框架 (`MigrationRunner`)**：提供 `@runner.step("X.Y.x")` 裝飾器與 $O(N)$ 線性代際遷移，支援跨版本平滑升級與自動回滾。
3. **五階段事務性安全升級流水線**：實作 Pre-flight 約束校驗、舊版快照備份至 `.yscb_cache/backup/`、2×2 專案配置增量深層合併、本地配置唯讀保留、`AGENTS.md` 標記軟合併與例外自動 Rollback 還原。
4. **統一 CLI 版本工具鏈**：提供 `python yscb_cli.py version <status|check|check-update|bump>` 全景管理。
5. **Installer 單檔自舉升級 (`installer self-update`)**：支援 Windows `.tmp` 原子安全替換，杜絕檔案鎖定問題。
6. **抽象外掛式 Extension Verifier Hook**：`verify_plan.py` 動態調用 `sop_ext://dogfooding_pipeline_verify.py`，把關版本號遞進與【源碼 == 建置 == 安裝】三態完全同步。

---

## 2. 變更檔案清單

| 檔案路徑 | 變更類型 | 說明 |
|---------|---------|------|
| `source/core/scripts/semver.py` | Add | SemVer 2.0.0 解析比較器與 VersionConstraint 約束匹配器 |
| `source/core/scripts/migration.py` | Add | MigrationRunner 鏈式線性增量遷移框架 |
| `source/core/scripts/context.py` | Modify | 新增 `get_module_version()` 與 `get_module_manifest()` |
| `source/core/scripts/yscb_core.py` | Modify | 導出 SemVer、MigrationRunner，版本升級至 `2.1.0` |
| `source/core/scripts/__init__.py` | Modify | 導出新增模組 |
| `source/core/manifest.json` | Modify | 版本號正式遞進至 `2.1.0` |
| `source/agents-workflow/manifest.json` | Modify | 版本號遞進至 `1.0.1`，相依宣告升級為 `core >= 2.0.0` |
| `source/agents-workflow/scripts/verify_plan.py` | Modify | 實作 `run_pluggable_extension_verifiers` 外掛式動態調度 |
| `extensions/dogfooding_pipeline_verify.py` | Add | 專案特化發布守門外掛（校驗版本遞進與三態同步） |
| `extensions/dogfooding_pipeline_ext.md` | Modify | 注入 Version Bump Checkpoint 規範 |
| `ys_codebase/yscb_installer.py` & `yscb_installer.py` | Modify | 整合 SemVer/VersionConstraint、5 階段事務升級、快照 Rollback、`self-update` 原子替換，升級至 `2.1.0` |
| `ys_codebase/yscb_cli.py` & `yscb_cli.py` | Modify | 新增 `version <status|check|check-update|bump>` 與 `installer self-update` 調度 |
| `test/test_semver.py` | Add | SemVer 單元測試套件 (8 項測試) |
| `test/test_migration.py` | Add | MigrationRunner 單元測試套件 (3 項測試) |
| `test/test_installer.py` | Modify | 擴充快照回滾、相依阻斷、`installer self-update` 等整合測試 (25 項測試) |
| `docs/Core/SEMVER_ENGINE.md` | Add | SemVer 2.0.0 與相依約束引擎專題手冊 (維度 3) |
| `docs/Core/MIGRATION_FRAMEWORK.md` | Add | 鏈式線性增量遷移框架手冊 (維度 3) |
| `docs/Installer/UPGRADE_PIPELINE.md` | Add | 五階段事務性安全升級流水線手冊 (維度 3) |
| `docs/Installer/DESIGN_NOTES.md` | Modify | 登記 `DN-04 ~ DN-06` 專案適配 SemVer、快照回滾與 Windows 原子替換 (維度 5) |
| `docs/AgentsWorkflow/EXTENSION_VERIFIERS.md` | Add | 抽象外掛式 Extension Verifier Hook 規範手冊 (維度 3) |
| `CHANGELOG.md` | Modify | 登記本計畫版本發布歷史摘要 |

---

## 3. 測試與品質驗證結果

- **自動化測試**：`python test/run_regression.py` 實機執行 **36/36 項單元與整合測試 + E2E 下游沙盒模擬 100% Passed**。
  - `test_installer.py`：25/25 Passed（含 5 階段升級、相依阻斷、快照回滾、AGENTS.md 軟合併、`self-update`）
  - `test_semver.py`：8/8 Passed（含解析、富比較、Caret/Tilde 約束、萬用字元）
  - `test_migration.py`：3/3 Passed（含鏈式線性執行、同 Minor 免執行、異常傳播中斷）
- **效能基準測試 (PT-01)**：10,000 次 SemVer 解析與比較耗時 **36.24ms**（`< 100ms`）。
- **合規性與發布守門**：`python yscb_cli.py agents-workflow verify` 100% 合規通過，`sop_ext://dogfooding_pipeline_verify.py` 驗證全專案【源碼 == 建置 == 安裝】三態版本完全一致（`[SYNCED]`）。
- **UX / 手動驗證**：開發者實機驗證 UX-01~04 終端互動與排版無誤，核准結案。
- **偏差記錄 (Defect Log)**：修復 BUG-01（`VersionConstraint` 解析帶空格條件問題）。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

> 依據 P04 預排之文檔計畫，1:1 核對實際產出與更新的 `docs/` 文件：

| 規劃文檔路徑 | 交付狀態 | 實際修改章節 / 核心知識點 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :--- | :--- | :--- |
| `docs/Core/SEMVER_ENGINE.md` | ✅ 已新建 | SemVer 2.0.0 解析比較、約束表達式語法 (`^`, `~`, `>=` 等) 與 `parse_dependency_spec` | P03 API-01, P05 Task 1, P06 FT-01~02 |
| `docs/Core/MIGRATION_FRAMEWORK.md` | ✅ 已新建 | `@runner.step("X.Y.x")` 裝飾器、線性執行演算法、異常回滾連動 | P03 API-02, P05 Task 2, P06 FT-08 |
| `docs/Installer/UPGRADE_PIPELINE.md` | ✅ 已新建 | 5 階段事務流水線流程、2x2 深層配置合併、快照備份回滾、`self-update` 原子替換 | P03 API-04, P05 Task 4 & 9, P06 FT-06~09, FT-11 |
| `docs/Installer/DESIGN_NOTES.md` | ✅ 已更新 | 登記 `DN-04` (專案適配 SemVer)、`DN-05` (快照回滾策略)、`DN-06` (Windows 原子自更新) | P05 Task 4 & 9, P06 EC-01~04, BUG-01 |
| `docs/AgentsWorkflow/EXTENSION_VERIFIERS.md` | ✅ 已新建 | 抽象外掛 Hook 機制、`sop_ext://<ext>_verify.py` 約定與專案守門實踐 | P05 Task 6 & 7, P06 FT-10 |

---

### Extension: dogfooding_pipeline_ext 執行結果
| 檢查項目 | 狀態 | 發現與備註 |
|:---|:---:|:---|
| Stage 1: 源碼空間確認 (ys_codebase/) | ✅ | 100% 於 source 目錄進行修改，已 bump core v2.1.0, agents-workflow v1.0.1, installer v2.1.0 |
| Stage 2: 模組打包構建 (build) | ✅ | build/ 目錄產物已重新生成並繼承最新版本號 |
| Stage 3: 全量回歸測試 (test) | ✅ | python test/run_regression.py 36/36 單元測試 + E2E 沙盒 100% 通過 |
| Stage 4: 自引用同步 (install/ide) | ✅ | modules/ 已強制覆蓋安裝，起手腳本已覆蓋同步，IDE 指令已重新生成，狀態為 [SYNCED] |

**結論**：已通過 Dogfooding 自引用標準四步流水線驗收。

---

## 5. 推薦 Commit 訊息

```text
feat(core,installer): implement complete semver, dependency constraints, migration runner, and self-update

- Add SemVer 2.0.0 and VersionConstraint engine (zero external dependency) in yscb_core
- Implement linear sequential MigrationRunner with @runner.step decorator
- Upgrade installer to 5-stage transactional pipeline with snapshot backup and rollback
- Add CLI version status, check, check-update, and bump commands
- Add installer self-update mechanism with Windows atomic replacement
- Add pluggable extension verifier hook in verify_plan.py and dogfooding release gate
- Update test suite to 36 tests with 100% regression and E2E pass rate
- Deliver comprehensive topic documentation (SEMVER_ENGINE, MIGRATION_FRAMEWORK, UPGRADE_PIPELINE, EXTENSION_VERIFIERS, DESIGN_NOTES)
```
