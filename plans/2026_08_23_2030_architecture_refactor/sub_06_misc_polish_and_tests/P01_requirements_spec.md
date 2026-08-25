# 需求規格書 (Requirements Specification)

> 功能名稱：核心模組雜項功能完善與 Core/Dev 標準測試套件建立 (Core Misc Polish & Core/Dev Standard Tests)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md) / [R01](./R01_design_concept_vs_current_practice_survey.md), [R02](./R02_core_standard_test_suite_design.md), [R03](./R03_dev_standard_test_suite_design.md)  
> 狀態：In Progress  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | **遠端 Provider 清冊批次下載 (`act_download`)** | 遠端 HTTP/Git URL 與目標模組/版本 | 1. 抓取 `index.json` 或 `manifest.json` 取得 `files: [...]` 清冊。<br/>2. 批次 HTTP 請求下載所有原始碼檔案至鏡像目錄。<br/>3. 雙重名稱校驗後完成鏡像建立。 | 完整鏡像目錄 `mirror://<mod>/<ver>/` | P00 情境 A；R01 GAP-1 |
| **FR-02** | **動態 SemVer 版本探測與升級 (`cmd_update`)** | 模組名稱（可選）與 Provider URL | 1. 向 Provider 查詢版本清冊。<br/>2. 比對本地版本，篩選大於當前版本之最新相容版本。<br/>3. 調用 `act_prepare` 與 `act_reload` 完成升級。 | 終端升級成功報告與狀態碼 0 | P00 情境 B；R01 GAP-2 |
| **FR-03** | **跨進程排他檔案鎖 (`act_lock` / `act_unlock`)** | 鎖識別碼與逾時時間 (預設 10s) | 1. 於 `temp://.yscb.lock` 以原子模式建立鎖。<br/>2. 記錄 PID 與時間戳記；逾時自動覆蓋並記錄警告。<br/>3. 操作完成或例外時原子刪除鎖。 | 成功上鎖/解鎖或拋出並發例外 | P00 情境 C；R01 GAP-3 |
| **FR-04** | **Contributes 5 大來源多層合併與規範說明書** | 模組宣告與專案組態 | 1. 依序合併 `manifest.json` ➔ `contributes.core.json` ➔ `config.project.json`。<br/>2. 交付 [`source/core/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core) 說明書。 | 合併後注入之 Contributes 字典 | P00 情境 D；R01 GAP-4 |
| **FR-05** | **宿主 `self-update` 與 `config.project.json` 範本** | 宿主更新指令 | 1. 自 Provider 下載最新 `yscb.py` 經 `py_compile` 驗證後原子覆蓋。<br/>2. 交付 `source/core/config.project.json` 專案組態範本。 | 更新後的 `yscb.py` 與設定檔範本 | P00 情境 E；R01 GAP-5 |
| **FR-06** | **`core` 模組官方標準測試套件** | `python yscb.py dev test core` | 實作 `source/core/tests/` 4 大測試檔案：<br/>• `test_uri.py` (VFS & URI 協議)<br/>• `test_engine.py` (12 大原子操作)<br/>• `test_installer.py` (7 大 Installer 指令)<br/>• `test_contributes.py` (5 來源聚合與注入) | 測試全數通過 (4 Suites, 16+ Cases) | P00 情境 F；R02 全節 |
| **FR-07** | **`dev` 模組官方標準測試套件** | `python yscb.py dev test dev` | 實作 `source/dev/tests/` 4 大測試檔案：<br/>• `test_scaffold.py` (模組建立與範本)<br/>• `test_checker.py` (AST 語法與 Schema)<br/>• `test_builder.py` (雙層排除與版本化輸出)<br/>• `test_tester.py` (測試組裝與 CLI 派發) | 測試全數通過 (4 Suites, 16+ Cases) | P00 情境 G；R03 全節 |

---

## 2. 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **零外部相依** | 100% 維持純 Python 3.8+ 標準庫（`os`, `sys`, `json`, `urllib`, `shutil`, `tempfile`, `unittest`）。 | import 靜態檢查與純淨環境驗證 |
| **NFR-02** | **建置發布排除鐵律** | `tests/` 目錄與 `tests/*` 檔案在 `dev build` 時必須 100% 被排除，絕對不得出現在發布產物中。 | `test_builder.py` 自動化斷言 |
| **NFR-03** | **跨平台一致性** | 檔案鎖與路徑解析在 Windows 與 POSIX 環境下運作一致，零編碼亂碼。 | 跨平台測試與路徑標準化斷言 |

---

## 3. 邊界情境 (Edge Cases)

| ID | 場景描述 | 預期行為 | 對應 FR |
| :--- | :--- | :--- | :--- |
| **EC-01** | 遠端 Provider 清冊中某檔案下載 404 或網路中斷 | 立即清理已下載之暫存鏡像，拋出明確例外，不污染 `mirror://`。 | FR-01 |
| **EC-02** | `update` 發現本地已為最新版本 | 終端輸出提示 `[core:update] Module 'xxx' is already up-to-date (v1.0.0).`，正常退出 (Exit 0)。 | FR-02 |
| **EC-03** | 前次進程異常崩潰導致 `.yscb.lock` 殘留 | 檢測鎖建立時間若超過 10s 逾時門檻，自動清理殘留鎖並發出 Warning 接續執行。 | FR-03 |
| **EC-04** | 模組未提供 `contributes.format.md` | 僅視為可選文檔缺失，不阻斷模組的安裝與執行。 | FR-04 |
| **EC-05** | 離線環境下運行包含網路依賴之測試 | 測試案例透過 `@require(Requirement.NETWORK)` 自動跳過，不產生假性紅燈。 | FR-06, FR-07 |

---

## 4. 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `sop_ext` 清單 | `on_demand` | ❌ 排除 (Excluded) | 本子計畫為核心功能完善與基礎測試建立，不涉及特化業務 SOP 擴充 |

---

## 5. 決策紀錄 (Decision Records)

- **[sub_06:DR-01] 遠端下載協議對齊**：支援 Provider `index.json` 之 `files: [...]` 陣列進行清冊批次抓取。
- **[sub_06:DR-02] 跨進程檔案鎖設計**：於 `temp://.yscb.lock` 採用 `os.open` 搭配 `O_CREAT | O_EXCL` 實作原子建立，並記錄 PID 與時間戳記支援逾時清理。
- **[sub_06:DR-03] 標準測試套件持久化規範**：測試檔案存放於 `source/<mod>/tests/test_*.py`，統一繼承 `dev.testing.YSCBTestCase`。
- **[sub_06:DR-04] contributes.format.md 與 config.project.json 模板交付**：於 `source/core/contributes.format.md` 與 `source/core/config.project.json` 提供正式規範檔案。
