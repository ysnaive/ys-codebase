# 成果展示與結案報告 (Walkthrough)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 依據 P01~P06：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md), [P04_implementation_plan.md](./P04_implementation_plan.md), [P05_task.md](./P05_task.md), [P06_test_plan.md](./P06_test_plan.md)  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **建置與純淨發布職責分離 (`Builder` & `Releaser`)**：
     - `dev build`：移除 `--clean` 選項（打包前一律自動物理清空目標 `build/<mod>/` 目錄），100% 完整保留 `tests/` 與開發檔案，產出 `<ver>.build.zip` 並自動更新 `build/<mod>/index.json`。
     - `dev release`：重構為純淨打包器（嚴格排除 `tests/` 與 `.yscbignore`），產出 `release/<mod>/<ver>.zip`；移除舊版冗餘的 bump 選項，與 `build` 對標極簡簽名。
  2. **發布產物時序滑動窗口與跨三元組收斂淘汰演算法 (`3-Revision Retention Policy`)**：
     - 同三元組 `X.Y.Z` 依時序保留至多 3 份最新 Revision zip，第 4 份及更早者自動物理淘汰刪除。
     - 跨三元組升級時，所有歷史舊三元組自動收斂僅保留最後最高 1 份 Revision zip，徹底消除歷史延遲殘留。
     - 以磁碟真實存在的 zip 檔案為唯一事實來源 (SSOT) 同步生成 `release/<mod>/index.json`，已被物理刪除的舊 Revision 自動自清冊排除。
  3. **3-Gate 發布品質守門閘門 (`3-Gate Verification`)**：
     - Gate 1 (靜態合規性)：Manifest 格式完整性與 `scripts/cli.py` 語法/進入點存在性。
     - Gate 2 (版本不可變性 - Immutability)：檢查四元版本庫是否已存在同名 zip，重複發布拋出 `ReleaseVersionExistsError` 阻斷。
     - Gate 3 (版本單調遞增 - Monotonicity)：待發布版本號必須嚴格大於同三元組在庫最高 revision，防止倒退，拋出 `VersionRollbackError` 阻斷。
  4. **版本遞增、預檢與安全流水線 CLI 工具鏈 (`scripts/cli.py`)**：
     - 實作 `dev bump-[major|minor|patch|revision] <mod>`：單向遞增模組 `manifest.json` 版本號。
     - 實作 `dev release-check <mod>`：獨立執行 3-Gate 發布就緒預檢（明確阻斷 `--all`）。
     - 實作 `dev release-git <mod> "<msg>"`：依序執行 `test` ➔ `release-check` ➔ `release` ➔ 本地 `git commit & tag`（🚨 嚴禁遠端 push）。
  5. **測試流水線前置自動建置 (`Tester`)**：
     - `dev test` 預設自動前置執行 `dev build`，構建失敗立即阻斷；支援 `--no-build` 旗標跳過前置打包直接跑測。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/dev/dev/builder.py` | `Modify` | 實作自動清空 build 目錄、純淨 release 打包、3-Revision 滑動窗口保留與跨三元組收斂淘汰演算法及 index SSOT 同步 |
| `source/dev/dev/tester.py` | `Modify` | 升級 `_run_test` 支援預設前置 build、失敗即阻斷與 `--no-build` 旗標 |
| `source/dev/dev/releaser.py` | `Modify` | 重構為純淨發布調度器：定義 3-Gate 例外型別、`release_check`、`release_module`、DAG 拓撲批次發布與 `release_git` 安全流水線 |
| `source/dev/scripts/cli.py` | `Modify` | 重構 CLI 路由門面：簡化 build/release、新增 `bump-*`、`release-check`（阻斷 `--all`）與 `release-git` |
| `source/dev/tests/test_builder.py` | `Modify` | 更新測試案例對齊 3-Revision 滑動窗口保留演算法驗證 |
| `source/dev/tests/test_release_pipeline.py` | `Modify` | 更新測試案例對齊全新 Releaser 工具鏈與 3-Gate 校驗驗證 |
| `test/test_dev_toolchain_refactor.py` | `New` | 新增 15 個單元與整合測試案例（FT-01~08, ET-01~07） |
| `docs/dev/README.md` | `Modify` | 更新 Dev 工具鏈定位、五大核心引擎與 CLI 指令索引矩陣 |
| `docs/dev/architecture.md` | `New` | 記錄五層分層架構、3-Gate 發布守門模型與 3-Revision 滑動窗口演算法規格 |
| `docs/dev/user_guide.md` | `New` | 撰寫全新 CLI 指令手冊（`build`, `release`, `test`, `bump-*`, `release-check`, `release-git`） |
| `docs/dev/topics/release_governance.md` | `New` | 建立「發布產物治理與版本時序滑動窗口」專題架構手冊 |
| `CHANGELOG.md` | `Modify` | 追加本次 sub_02 Dev 模組工具鏈重構之高階發布摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - **專用重構測試套件 (`test/test_dev_toolchain_refactor.py`)**：**`15 / 15` 全部通過 (`100% Passed`)** (0.336s)。
  - **全系統沙盒端到端回歸測試 (`python yscb.py dev test --all`)**：**`109 / 109` 全部通過 (`100% Ready`)** (27.864s)。
- **實機 UX / 人工驗證**：
  - 開發者確認免測通過（`UX-01` 確認通過）。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **維度一** | `docs/dev/README.md` | ✅ 已交付 | 更新 Dev 工具鏈定位、五大引擎架構圖與 CLI 矩陣索引 |
| **維度二** | `docs/dev/architecture.md` | ✅ 已交付 | 記錄五層架構拓撲、3-Gate 守門機制與 3-Revision 滑動窗口演算法規格 |
| **維度三** | `docs/dev/user_guide.md` | ✅ 已交付 | 完整 CLI 操作手冊（包含 `bump-*`, `release-check`, `release-git` 等參數範例） |
| **維度七** | `docs/dev/topics/release_governance.md` | ✅ 已交付 | 發布產物治理專題：時序滑動窗口原理、跨三元組收斂、實體 SSOT 索引與依賴求解機制 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(dev): modernize build, release and verification toolchains

- refactor(builder): auto-clean build target, pure release packaging and 3-revision temporal sliding window retention policy
- refactor(tester): auto hermetic pre-build before tests with --no-build override flag
- feat(releaser): 3-gate release verification model, DAG topological batch release, and local-only release-git pipeline
- feat(cli): add bump-[major|minor|patch|revision], release-check (reject --all), and release-git commands
- test: add comprehensive test suite for toolchain refactor (15/15 Passed, 109/109 E2E Ready)
- docs(dev): complete 1:1 documentation deliverables (README, architecture, user_guide, topics/release_governance)
```
