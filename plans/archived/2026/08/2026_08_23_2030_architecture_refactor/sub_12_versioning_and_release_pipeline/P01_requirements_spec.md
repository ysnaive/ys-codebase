# 需求規格說明書 (Requirements Specification)

> 功能名稱：四段式版本號、雙軌來源庫 (Build vs Release)、三層安裝降級鏈、發布流水線與 Migration 機制重構  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00/調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md), [R01](./R01_release_and_build_distinction_analysis.md), [R02](./R02_release_cli_boundary_and_pipeline_analysis.md), [R03](./R03_migration_mechanism_and_gitignore_boundary_analysis.md)  
> 狀態：Draft (Phase 1 待審核)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格說明 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- |
| **FR-01** | 四段式 SemVer 運算器升級 | 1. 升級 `core.semver` 支援 `major.minor.patch.revision` 四段式版本解析。<br/>2. 實作數值比大小（`major`/`minor`/`patch` 決定大小，`revision` 在比大小中無大小意義）。<br/>3. 支援解析期自動補齊正規化（三段式 `X.Y.Z` 自動補齊為 `X.Y.Z.0`）。 | P00 §2 期望 1<br/>R01 §2 |
| **FR-02** | 同 X.Y.Z 單一 Revision 淘汰原則 | 1. 於 `release/` 發布庫中，相同的 `major.minor.patch` 嚴格僅允許存在單一最新 Revision。<br/>2. 當發布同 `X.Y.Z` 的新 Revision（如 `1.0.0.2` 覆蓋 `1.0.0.1`）時，系統自動淘汰刪除舊版目錄並更新 `index.json`。<br/>3. 外部安裝常態以三元版本號（如 `core@1.0.0`）宣告，微內核自動匹配該 `X.Y.Z` 之最新 Revision。 | P00 §2 期望 1<br/>R01 §2.3 |
| **FR-03** | 雙軌來源庫協議與拓撲支援 | 1. `core.uri` 註冊 `release://` 與 `release.root://` 協議，作為全系統唯一預設來源庫 (`default_provider`)。<br/>2. `build://`（`module.build.root://`）重定義為本地開發完整包來源庫。<br/>3. 宿主 `yscb.config.json` 之 `default_provider` 導向 Git 遠端相對索引。 | P00 §2 期望 2<br/>R01 §3 |
| **FR-04** | 模組安裝三層降級解析鏈 | 微內核在執行模組安裝/解析時，嚴格遵循三層降級鏈：<br/>• **優先層 ① `build://`**：本地 `build/<mod>/index.json` 存在且含有效 `*.build` 則優先採用（自帶 tests/）。<br/>• **次優層 ② `mirror://`**：本地快照存在則快速還原。<br/>• **兜底層 ③ `provider`**：由 Git 遠端或組態定義來源全新下載。 | P00 §2 期望 3<br/>R01 §4 |
| **FR-05** | `dev build` 完整打包與 Hermetic 清理 | 1. `dev.builder` 重構 `dev build` 為 100% 完整打包（不移除任何檔案，完整保留 `tests/` 與開發檔案）。<br/>2. 產物版本號之 revision 強制標記為 `"build"`（例：`1.0.1.build`）。<br/>3. 建置前清空同名目錄，版本遞進時自動清理舊 `*.build` 目錄，保持單一最新建置產物。 | P00 §2 期望 2<br/>R01 §3.2 |
| **FR-06** | `dev test` 去特例化黑盒測試流水線 | 1. `dev test [--all \| <mod>]` 測試前自動調用 `dev build` 打包待測模組至 `build://`。<br/>2. 沙盒內依三層降級鏈透過標準 `yscb install` 安裝模組。<br/>3. 沙盒內原地調用 `dev op-test` 執行測試，徹底移除人工 `source/` 拷貝特例，達成 100% 黑盒對稱。 | P00 §2 期望 3<br/>R01 §5 |
| **FR-07** | `dev release` 標準發布流水線 | 1. 實作 `dev release <mod> [bump_type \| explicit_version]` 指令。<br/>2. 支援四大層級 Version Bump（`major`, `minor`, `patch`, `revision`，高階進位時低階剛性歸零）。<br/>3. 執行純淨打包（依 `.yscbignore` 排除 `tests/`）寫入 `release/<mod>/<ver>/` 並更新 `index.json`。 | P00 §2 期望 2<br/>R02 §2, §3 |
| **FR-08** | 發布 Pre-flight 守門與交易原子回滾 | 1. 實作 4 大剛性守門：Git Clean 檢查、`dev test` 100% 通過、版本唯一性/Revision 合法覆蓋檢查、Manifest 合規。<br/>2. 實作發布交易防護（All-or-Nothing）：發布中途異常時，自動復原 Manifest、刪除殘留產物、還原 Index、刪除半成品 Tag。 | P00 §2 期望 2<br/>R02 §4, §5.2 |
| **FR-09** | 智慧 Git Tag 觸發矩陣 | 1. `major` 與 `minor` 級別發布預設自動建立 Git Tag (`{mod}/v{ver}`)。<br/>2. `patch` 與 `revision` 級別發布預設不打 Tag。<br/>3. 提供 `--tag`（強制建立）與 `--no-tag`（強制跳過）覆蓋旗標。 | P00 §2 期望 2<br/>R02 §6 |
| **FR-10** | 模組 Migration 階梯式調用引擎 | 1. 定義遷移腳本規範：`module://scripts/migrations/{major}.{minor}.x.py`（語意：從 `{A}.{B-1}.x` 升級為 `{A}.{B}.x`）。<br/>2. `core` 模組於更新/升級時，依版本階梯依序執行遷移腳本（找不到檔案自動靜默跳過）。<br/>3. `update` 實施「同 Major 鎖定」，跨 Major 升級需顯式指定版本並提示破壞性變更（跳過 Migration）。 | P00 §2 期望 5<br/>R03 §5 |
| **FR-11** | 模組組態雙軌解耦 | 1. 模組組態解耦為 `config://config.project.json`（專案級標準，Git 追蹤）與 `config://config.local.json`（本機個人覆蓋，.gitignore 忽略）。<br/>2. 運行時提供層疊 Deep Merge 產生模組 Effective Config。 | P00 §2 期望 4<br/>R03 §2.1, §3 |
| **FR-12** | Snapshot 範圍矩陣與雙粒度原子回滾 | 1. Snapshot 範圍剛性納入：`modules/`、`config://`（project 與 local）、`storage://`、宿主組態；排除揮發性 `cache://`、`mirror://`、`build://`。<br/>2. 支援單模組精準快照（`update <mod>`）與全系統快照，升級/遷移失敗時 100% 原子無損還原。 | P00 §2 期望 5<br/>R03 §6 |
| **FR-13** | `yscb://.gitignore` 零污染自動生成與自舉判定 | 1. `yscb init` 於 `yscb://.gitignore` 自動生成內部忽略規則（`/build/`, `/.yscb_cache/`, `*.local.json`），嚴禁污染專案根目錄。<br/>2. 依 `source/core/` 物理存在性判定官方開發端 vs 第三方端，決定 `yscb init` 與沙盒自舉指向。 | P00 §2 期望 4<br/>R01 §6, R03 §4.1 |

---

## 2. 邊界與異常情況處理 (Edge Cases)

| 邊界編號 | 邊界情境說明 | 防禦處置與預期行為 | 對應需求 |
| :--- | :--- | :--- | :--- |
| **EC-01** | 三段式版本號傳入四段式運算器 | `core.semver.parse("1.0.0")` 自動補齊為 `(1, 0, 0, 0)`，保證內部四元組結構完全一致，嚴禁拋出 IndexError。 | FR-01 |
| **EC-02** | `dev release` 發布完全重複之版本 | 嘗試發布已存在於 `release/<mod>/index.json` 之相同全版本（如重複發布 `1.0.0.1`）時，Gate 3 阻斷並拋出 `VersionConflictError`。 | FR-08 |
| **EC-03** | `dev release` 發布同 `X.Y.Z` 之新 Revision | 發布 `1.0.0.2` 覆蓋 `1.0.0.1` 時，Gate 3 判定為合法修復，打包新版後自動清理舊版 `1.0.0.1/` 目錄並更新 `index.json`。 | FR-02, FR-08 |
| **EC-04** | `dev release` 中途異常終斷 | 若打包、寫入 index 或 Git 操作失敗，交易防護自動還原 `source/manifest.json`、刪除殘留 release 目錄並還原 index。 | FR-08 |
| **EC-05** | Migration 階梯中某個 minor 版本無腳本 | 例如從 `1.0.0` 升級至 `1.3.0`，若缺少 `1.2.x.py`，系統自動靜默跳過並接續執行 `1.3.x.py`，不報錯。 | FR-10 |
| **EC-06** | Migration 腳本執行中拋出例外 | Migration 腳本拋錯或回傳 `False` 時，立即觸發 Snapshot 原子回滾，將代碼、組態與 `storage://` 還原回升級前乾淨狀態。 | FR-10, FR-12 |
| **EC-07** | `yscb update` 遇到遠端新 Major 版本 | 日常 `update` 自動鎖定在當前 Major 內升級；若無同 Major 更新則提示已是最新版，不自動跨入下一 Major。 | FR-10 |
| **EC-08** | 三層降級鏈各層皆無目標模組 | 若 `build://`、`mirror://` 與 `provider` 皆無目標版本產物，拋出精確的 `PackageNotFoundError` 並列出所有嘗試過的來源清單。 | FR-04 |

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01（100% Python 標準庫）**：所有新增模組（含 SemVer 四段式運算、發布打包器、Migration 執行器）100% 基於 Python 3.10+ 標準庫，零第三方依賴。
- **NFR-02（原子性交易保證）**：發布流水線與升級遷移具備 100% 失敗補償與快照回滾能力，保證工作區零髒狀態。
- **NFR-03（回歸測試通過率 100%）**：全模組（`core`, `dev`）單元、合約與整合測試 100% 綠燈通過。

---

## 4. 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充功能名稱 | 觸發模式 | 判定結果 | 評估理由 |
| :--- | :--- | :---: | :--- |
| `dogfooding_pipeline_ext` | always | **Excluded (排除)** | 本計畫為標準模組能力與發布流水線重構，依循標準四步閉環流水線執行。 |

---

## 5. 踩坑紀錄與設計註記巡檢 (Design Notes Pre-check)

- **DN-01（不可變鏡像庫保證）**：`mirror://` 為不可變版本庫，任何安裝/升級不得直接原地篡改既有版本目錄。
- **DN-02（微內核拓撲不變量）**：`core.uri._get_yscb_root()` 往上 3 層在微內核派發鏈條下為物理拓撲恆等式，是 Fast-Path 零 I/O 解析基礎。
- **DN-07（OS 原子鎖）**：快照還原與發布產物寫入時，遵循 OS 原子鎖保護，杜絕並發讀寫損毀。
- **DN-08（剛性拓撲無猜測邊界）**：三層降級鏈與 Provider 解析嚴格依 `index.json` 存在性判定，移除模糊猜測。
