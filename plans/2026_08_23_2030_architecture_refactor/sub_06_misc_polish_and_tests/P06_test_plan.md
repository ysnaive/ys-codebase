# 測試計畫書 (Test Plan)

> 功能名稱：核心模組雜項功能完善與 Core/Dev 標準測試套件建立 (Core Misc Polish & Core/Dev Standard Tests)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01 / P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Passed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 測試案例矩陣 (Test Cases Matrix)

| 測試編號 | 測試項目 | 驗證目標 | 執行方式 | 預期結果 | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | 遠端 Provider 清冊批次下載 | 驗證 `act_download` 根據 `index.json` 之 `files` 清單抓取全量檔案 | `test_engine.py` | 完整建立鏡像目錄且內容一致 | ✅ Passed |
| **FT-02** | `yscb update` 動態版本查詢與升級 | 驗證向 Provider 查詢版本清冊並依 SemVer 升級 | `test_installer.py` | 成功升級至最新相容版本並更新組態 | ✅ Passed |
| **FT-03** | 跨進程檔案鎖排他性與逾時自癒 | 驗證 `act_lock` / `act_unlock` 互斥防護與 10s 逾時清理 | `test_engine.py` | 雙進程衝突時拒絕並發，崩潰逾時自動自癒 | ✅ Passed |
| **FT-04** | Contributes 5 大來源多層合併 | 驗證 `manifest.json` ➔ `contributes.core.json` ➔ `config.project.json` 覆蓋 | `test_contributes.py` | 專案層級設定正確覆蓋模組層級設定 | ✅ Passed |
| **FT-05** | 宿主 `self-update` 與組態範本 | 驗證 `yscb.py self-update` 下載與 `py_compile` 原子替換 | `test_installer.py` | 宿主腳本更新成功且語法完整 | ✅ Passed |
| **FT-06** | `core` 模組 4 大持久化標準測試 | 驗證 `source/core/tests/` 全量單元測試執行通過 | `python yscb.py dev test core` | 4 大測試模組 (12 Cases) 全數 Passed | ✅ Passed |
| **FT-07** | `dev` 模組 4 大持久化標準測試 | 驗證 `source/dev/tests/` 全量單元測試執行通過 | `python yscb.py dev test dev` | 4 大測試模組 (10 Cases) 全數 Passed | ✅ Passed |
| **ET-01** | 遠端下載檔案 404 / 斷網中斷 | 驗證下載失敗時自動清理暫存鏡像並拋出明確例外 | `test_engine.py` | 鏡像庫保持純淨，操作中斷回滾 | ✅ Passed |
| **ET-02** | 殘留死鎖 (Deadlock) 10s 逾時自癒 | 驗證殘留鎖超時時自動覆蓋並記錄 Warning | `test_engine.py` | 成功清除死鎖並完成操作 | ✅ Passed |
| **ET-03** | `update` 遇到已是最新版本 | 驗證已為最新版本時之提示 | `test_installer.py` | 輸出 Already up-to-date，Exit Code 0 | ✅ Passed |
| **PT-01** | 完整回歸測試執行效能 | 驗證全量回歸測試 (Core+Dev 28 Cases) 執行開銷 | 計時斷言 | 實測 0.370s (< 500ms 門檻) | ✅ Passed |

---

## 2. 雙階段驗證流程與檢核關卡 (Two-Stage Verification & Checkpoints)

### 2.1 雙階段驗證時序 (Two-Stage Verification Workflow)

- [x] **Stage 0（建置與安裝部署物化 - 前置守門）**：
  1. 原始碼完成修改後，執行 `dev build --all --clean` 產出純淨套件；
  2. 部署至 `modules/` 運行端，保證測試引擎在已部署之正確環境下運行。
- [x] **Stage 1（隔離沙盒前置試跑）**：
  1. 將包含最新部署之 `yscb.py`、`yscb.config.json` 與 `ys_codebase/` 複製至 `./sandbox/`；
  2. 於 `./sandbox/` 執行整套流程（28/28 Passed）；
  3. 觀察驗證 100% 無誤後，**已正式完全刪除 `./sandbox/` 臨時目錄**。
- [x] **Stage 2（正式環境全量自動化驗收）**：
  1. 於專案正式環境執行 `python yscb.py dev test --all --verbose`；
  2. 驗證全量 Auto-Contract (6/6) + 持久化 Custom Tests (22/22) **100% 全部通過 (28/28 Passed, 0.370s)**。
- [x] **建置發布排除檢驗**：執行 `python yscb.py dev build --all`，確認 `build/` 與 `modules/` 100% 無 `tests/` 與 `.yscbignore`。
- [x] **開發者 UX / 手動測試確認**：開發者於控制台實機執行 `python yscb.py dev test --all --verbose` 驗證通過 (Status: PASSED 100% Ready)，正式結案。
