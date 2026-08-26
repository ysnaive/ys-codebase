# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：模組資料管理相關 URI 協議釐清與遷移 (Module Data Management URI Protocol Alignment & Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：子計畫 01，模組資料管理相關 uri 協議釐清與遷移。
- **核心目標**：
  1. 釐清並規範系統中與「模組資料管理」相關的語意 URI 協議體系（如：`storage://`、`cache.root://`、`module://`、`module.root://`、`module.source.root://` 等）的職責邊界、路徑映射規則與解析行為。
  2. 盤點現行代碼與各模組實作中直接使用硬編碼路徑（如 `os.path.join(..., "storage", ...)`、`os.path.join(..., ".cache", ...)`）或舊協議之處，全面遷移為標準 URI 體系。
  3. 確保 `core` 與 `dev` 的微內核資料持久化與快取讀寫邏輯 100% 透過 `uri` 系統安全統一管理。
- **邊界排除 (Explicitly Excluded)**：待本輪 Phase 0 開放式討論確認。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 四大深度調研維度確立 (R01~R04)**：
  - **`R01`**：語意空間分布與協議體系拓撲深度調研 (`R01_semantic_space_distribution.md`)。
  - **`R02`**：上下文隱式綁定 vs. 顯式跨模組尋址二義性深度調研 (`R02_module_context_ambiguity.md`)。
  - **`R03`**：模組資料生命週期與狀態治理深度調研 (`R03_module_data_lifecycle.md`)。
  - **`R04`**：全代碼庫硬編碼路徑盤點與 100% URI 全面遷移策略 (`R04_hardcoded_paths_migration.md`)。
- **[P00:DR-02] R01 模組資料三位一體全新定義與 temp 協議廢除**：
  - **`storage`**：任何需要被長久儲存 / Git 追蹤之資料（`yscb://storage/`，Git Tracked）。
  - **`cache`**：任何效能優化中繼檔案 / 可被 Git 忽略之資料 / 本機端使用者 UX 狀態 / 沙盒與臨時暫存（`yscb://.cache/`，Git Ignored）。
  - **`config`**：任何設定檔（`yscb://config/`，Git Tracked）。
  - **`temp`**：正式廢除，其職責 100% 併入 `cache`。
- **[P00:DR-03] R02 採納方案 B（全量 Root 化 + @/ 標籤語法模型）**：
  - 廢除所有 `*.root://` 協議（如 `storage.root://`, `module.root://` 等），協議體系精簡 50%。
  - 顯式跨模組存取：`{scheme}://{module}/{path}`（如 `storage://agents-workflow/manifest.json`）。
  - 當前模組自省存取：`{scheme}://@/{path}`（如 `storage://@/manifest.json`）。
  - 徹底消滅上下文雙重嵌套歧義。
- **[P00:DR-04] R03 模組資料全生命週期治理定式**：
  - `cache://@/`：在 `remove` 與 `update` 時一律**自動物理清空**，不留垃圾快取。
  - `storage://@/` 與 `config://@/`：在標準 `remove` 時**預設安全保留**；僅在顯式指定 `--purge` 時**強制物理刪除**。
- **[P00:DR-05] R04 全代碼庫硬編碼路徑盤點與全面遷移清冊定稿**：
  - 確立 `storage/core/agents-workflow/release_manifest.json` 誤建 Bug 根因與修復方案。
  - 盤點全系統 400+ 處 `*.root://` 與 `temp://` 調用，全面制定四步閉環遷移清冊。

---

## 3. 開放議題與確認紀錄

- [x] **調研規劃**：確立四大討論維度對應 R01~R04
- [x] **R01 調研定稿**：語意空間分布與模組資料三位一體定義（storage / cache / config / 廢除 temp）
- [x] **R02 調研定稿**：上下文二義性根治與方案 B（全量 Root 化 + `@/` 標籤）
- [x] **R03 調研定稿**：資料生命週期、狀態轉移與 `--purge` 清理邊界
- [x] **R04 調研定稿**：全系統硬編碼路徑掃描、錯誤路徑修復與 100% 全面遷移清冊
- [ ] **Phase 0 結案確認**：等待開發者宣告 Phase 0 討論結束並確認 P00 內容！
