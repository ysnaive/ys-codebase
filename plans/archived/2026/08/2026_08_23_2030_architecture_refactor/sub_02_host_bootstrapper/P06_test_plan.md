# 測試計畫 (Test Plan)

> 功能名稱：超薄宿主單檔實現 (Ultra-Thin Host Bootstrapper)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Passed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 核心自動化測試矩陣 (Automated Test Matrix)

> 本子計畫專注於 `yscb.py` 宿主本體之路由、自舉目錄生成、自更新與派發機制驗證（真實 `core` 模組於 `sub_03` 建立）。

| ID | 類別 | 對應項目 | 測試描述與操作步驟 | 預期結果 | 實測狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **FT-01** | 功能 | FR-01 | 在暫存沙盒目錄執行 `python yscb.py init ./ys_codebase` | 1. 成功建立初始 `yscb.config.json`（寫入 `yscb_root`）；<br/>2. 確保 `ys_codebase` 目錄存在；<br/>3. 輸出初始化完成引導。 | ✅ Passed |
| **FT-02** | 功能 | FR-02 | 執行 `python yscb.py self-update` 進行版本比對與自我更新 | 1. 檢索版本資訊；<br/>2. 語法驗證（`ast.parse`）通過並完成 `.bak` 備份與覆蓋；<br/>3. 輸出更新成功訊息。 | ✅ Passed |
| **FT-03** | 功能 | FR-03/04 | 在沙盒建立 Dummy 測試模組，執行 `python yscb.py dummy_mod run --test` 與 `python yscb.py install dummy` | 1. 泛用派發：無損透傳參數 `['run', '--test']` 並精確透傳 Exit Code；<br/>2. Core 指令轉發：`install` 精確路由至 `core` 模組派發進入點。 | ✅ Passed |
| **ET-01** | 邊界 | EC-01 | 在已初始化的環境重複執行 `python yscb.py init ./ys_codebase` | 立即阻斷並提示「環境已初始化，請勿重複執行」，組態檔未被破壞。 | ✅ Passed |
| **ET-02** | 邊界 | EC-02 | 在未初始化的目錄直接執行任何指令（如 `python yscb.py status`） | 阻斷並輸出友善提示，引導使用者執行 `init`。 | ✅ Passed |
| **ET-03** | 邊界 | EC-03 | 調用未安裝或缺少進入點的模組 `python yscb.py nonexistent` | 輸出清晰錯誤提示「Module 'nonexistent' 未安裝或缺少 scripts/cli.py 進入點」。 | ✅ Passed |
| **ET-04** | 邊界 | EC-04 | 模擬 `self-update` 下載到語法錯誤之腳本 | 語法驗證攔截失敗，立即回滾保留原 `yscb.py`，不破壞現有檔案。 | ✅ Passed |
| **PT-01** | 效能 | NFR-01/02 | 檢查 `yscb.py` 代碼行數與依賴庫清單 | 1. 100% 純標準庫（`sys`, `os`, `json`, `urllib.request`, `subprocess`, `shutil`, `ast` 等），零第三方 pip 依賴；<br/>2. 非空代碼行數 167 行 <= 200。 | ✅ Passed |

---

## 2. UX 與手動視覺互動驗證 (UX Validation)

| ID | 驗證主題 | 測試描述與操作路徑 | 開發者體驗與視覺反饋 | 驗證狀態 |
| :--- | :--- | :--- | :--- | :---: |
| **UX-01** | 命令列幫助與未初始化提示 | 執行 `python yscb.py` 或未初始化時的提示訊息 | 終端文字簡明排版、語意清晰且具備具體引導。 | ⬜ Pending (待開發者確認) |
| **UX-02** | 宿主更新進度回饋 | 執行 `self-update` 時的終端輸出 | 具備清晰的步驟指示（比對中、驗證中、完成）。 | ⬜ Pending (待開發者確認) |

---

## 3. Bug 修復記錄 (Defect Log)

### BUG-01: `cmd_self_update` 代理與本地路徑相容性增強
- **發現於**：FT-02 / ET-04
- **Root Cause & 修復方案**：在 IDE 沙盒環境或本地自訂 Provider 時，`urllib.request` 預設可能受全域 Proxy 攔截 localhost 導致 400 錯誤，且缺乏對本地檔案路徑與 `file://` 協議的直接解析。修復方案：增加本地路徑/`file://` 直接讀取邏輯，並對 loopback/localhost 請求使用 `ProxyHandler({})` 自動直連。
- **回歸確認**：重新執行 FT-02 與 ET-04 ➔ ✅ 全部通過。

---

## 4. 測試結論與 Phase 6 Checkpoint

- [x] **Agent CLI 自動化測試**：已實機完成自動化測試（8 項自動化測試矩陣 100% Passed，0 Error / 0 Warning）
- [x] **開發者 UX / 手動測試確認**：開發者明確回覆「UX 驗證通過」或指示免測，允許進入 Phase 7
