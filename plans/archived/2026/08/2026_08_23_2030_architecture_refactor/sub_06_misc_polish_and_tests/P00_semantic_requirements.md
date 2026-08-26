# 語意需求與概念共識 (Phase 0: Semantic Requirements)

> 功能名稱：核心模組雜項功能完善與 Core/Dev 標準測試套件建立 (Core Misc Polish & Core/Dev Standard Tests)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據調研報告：[R01](./R01_design_concept_vs_current_practice_survey.md), [R02](./R02_core_standard_test_suite_design.md), [R03](./R03_dev_standard_test_suite_design.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 核心願景與業務語意 (What & Why)

在前期五個子計畫中，我們完成了微內核宿主、包管理器、開發者工具與測試引擎的骨架建構。

本子計畫（`sub_06`）的願景是**「對齊主計畫設計藍圖，完善核心功能細節並建立持久化標準測試套件」**：
1. **補齊核心機制缺口 (Gap 1~5)**：
   - 實作遠端 Provider 多檔案清冊批次下載 (`act_download` 支援 `files: [...]`)；
   - 實作 `yscb update` 動態向 Provider 查詢 SemVer 版本清冊並升級；
   - 實作 `temp://.yscb.lock` 跨平台跨進程檔案鎖，保證環境操作之原子性；
   - 實作 5 大來源 Contributes 深度字典合併，並落地 [`source/core/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core) 規範說明書；
   - 實作 `yscb.py self-update` 單檔原子自我更新，並落地 `config.project.json` 專案組態標準模板。
2. **建立官方持久化標準測試套件**：
   - 於 [`source/core/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core) 建立 4 大持久化標準測試（URI, Engine, Installer, Contributes）；
   - 於 [`source/dev/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev) 建立 4 大持久化標準測試（Scaffold, Checker, Builder, Tester）；
   - 達成 `python yscb.py dev test --all` 兩階段測試探索 100% 通過之品質守門。

---

## 2. 核心使用情境與端到端旅程 (User Scenarios & Journeys)

### 情境 A：遠端 Provider 多檔案清冊批次抓取 (Remote Batch Download)
- **旅程**：
  1. 用戶執行 `python yscb.py install my_plugin --provider=https://example.com/repo/build`；
  2. `act_download` 偵測為遠端 URL，先抓取 `my_plugin/1.0.0/index.json`（或 `manifest.json`）取得 `files: [...]` 檔案清冊；
  3. 系統批次發起 HTTP 請求，逐一下載原始碼檔案至鏡像目錄；
  4. 驗證鏡像結構完整性，物化至 `modules/my_plugin/`。

### 情境 B：動態 SemVer 版本查詢與升級 (`yscb update`)
- **旅程**：
  1. 用戶執行 `python yscb.py update dev`；
  2. 安裝器向 Provider 查詢可用版本清冊（例 `["1.0.0", "1.1.0", "1.2.0"]`）；
  3. 系統依 SemVer 規則計算出最新相容版本 `1.2.0`，自動下載並完成升級。

### 情境 C：跨進程操作原子鎖保護 (`temp://.yscb.lock`)
- **旅程**：
  1. 當一個進程正在執行 `install` 或 `reload` 時，自動於 `temp://.yscb.lock` 上鎖；
  2. 若有第二個進程同時嘗試修改環境，將被鎖機制阻斷並提示「Another yscb process is holding the lock」；
  3. 操作完成（或異常中斷）時，鎖自動釋放或支援逾時自癒。

### 情境 D：Contributes 5 大來源層級合併與規範說明書
- **旅程**：
  1. 模組開發者查閱 `source/core/contributes.format.md` 了解如何向 `core` 擴充路徑佔位符、URI 協議與事件；
  2. 系統在 `act_reload` 時，依序合併 `manifest.json` ➔ `contributes.core.json` ➔ `config.project.json`，使專案層級的覆蓋設定優先級最高。

### 情境 E：宿主 `self-update` 與 `config.project.json`
- **旅程**：
  1. 用戶執行 `python yscb.py self-update`；
  2. 宿主從 Provider 下載最新版 `yscb.py` 至暫存檔，執行 `py_compile` 語法檢驗；
  3. 校驗通過後原子覆蓋本機 `yscb.py`。

### 情境 F & G：Core 與 Dev 模組官方標準測試套件持久化
- **旅程**：
  1. 開發者在 `source/core/tests/` 與 `source/dev/tests/` 撰寫持久化測試；
  2. 執行 `python yscb.py dev test --all`；
  3. 測試引擎自動探索並同時執行 **Auto-Contract Tests (6/6)** 與 **全量 Custom Tests (8 Suites, 30+ Cases)**；
  4. 執行 `python yscb.py dev build --all`，`tests/` 目錄自動被 Layer 1 排除，不污染發布包。

---

## 3. 核心限制與非目標 (Constraints & Non-Goals)

### 核心限制
- **零外部相依 (Zero External Dependency)**：所有新增功能（含檔案鎖、遠端批次下載、SemVer 比較）100% 基於 Python 3.8+ 標準庫。
- **建置發布排除鐵律**：`source/*/tests/` 下的所有持久化測試檔案在 `dev build` 時必須 100% 被排除，絕對不得出現在 `build/` 與 `modules/` 中。

### 非目標
- 本計畫不涉及複雜的 SAT-solver 相依衝突演算法（僅實作基礎 SemVer 範圍比對）。
- 本計畫不涉及線上 PyPI 倉庫索引，僅針對本地目錄與 HTTP/Git Raw Provider 規範。

---

## 4. 關鍵設計決策紀錄 (Decision Records)

- **[sub_06:DR-01] 遠端下載協議對齊**：支援 Provider `index.json` 之 `files: [...]` 陣列進行清冊批次抓取。
- **[sub_06:DR-02] 跨進程檔案鎖設計**：於 `temp://.yscb.lock` 採用 `os.open` 搭配 `O_CREAT | O_EXCL` 實作原子建立，並記錄 PID 與時間戳記支援逾時清理。
- **[sub_06:DR-03] 標準測試套件持久化規範**：測試檔案存放於 `source/<mod>/tests/test_*.py`，統一繼承 `dev.testing.YSCBTestCase`。
- **[sub_06:DR-04] contributes.format.md 與 config.project.json 模板交付**：於 `source/core/contributes.format.md` 與 `source/core/config.project.json` 提供正式規範檔案。

---

## 5. 待釐清問題與討論區 (Open Questions)

- [x] **開發者已明確宣告討論結束**，P00 語意需求內容已完整且正確。
