# 修訂紀錄書 (Revision Log)

> 功能名稱：`module:gdrive-support` 對外 Google Drive API 非沙盒功能驗證與實機 DX 修訂 (`sub_03_live_gdrive_verification`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] OAuth 2.0 Client ID 互動式與兩階段授權流程、隨包 `README.md` 補全與真實 Google Drive REST API v3 全鏈路實機驗證
- **修訂類別**：UI/UX/DX | Docs
- **涉及檔案**：
  - `ys_codebase/source/gdrive-support/gdrive_support/transport.py`
  - `ys_codebase/source/gdrive-support/scripts/cli.py`
  - `ys_codebase/source/gdrive-support/contributes/core.json`
  - `ys_codebase/source/gdrive-support/README.md`
  - `docs/gdrive-support/README.md`
- **修訂摘要**：
  1. 於 `gdrive_support/transport.py` 與 `scripts/cli.py` 補齊標準庫 OAuth 2.0 Client ID (`credentials.json`) 授權流程（`load_oauth_client_config`、`build_oauth_authorize_url`、`exchange_oauth_code_for_token`、`run_oauth_loopback_flow`），支援本機 `http://127.0.0.1:8765` Loopback 自動回呼接收及無頭容器 `--no-launch-browser` + `--code` 兩階段兌換 `token.json`。
  2. 補齊 `ys_codebase/source/gdrive-support/README.md` 隨包導覽手冊，並以 `install gdrive-support@build --force` 熱部署。
  3. 針對開發者提供之真實 Google Drive 測試資料夾 (`root_folder_id = 1pbiL_R8TDq-s7afl_ZkdeV3RrpUWdMyO`) 完成全套實機驗證：
     - **OAuth 2.0 Loopback 實機授權**：`python yscb.py gdrive auth --port=8765` 成功接收瀏覽器授權回呼並儲存 `cache://gdrive-support/token.json`。
     - **雲端倉庫初始化與原子操作 (`init`, `mkdir`, `put`, `ls`, `get`, `rm`)**：成功於雲端建立 `.yscb_gdrive.json` (`169aXxqLDZ_-ZXMvBukVDaSpDVm1q8tVO`)、`README.md` (`1MA7kECfi8ejCsbA3OzjFwD5ZXrMhtwsK`)、`.history/`、`.trash/` 與 `main/`，並實測檔案上傳、列表與下載。
     - **Shortcut 差量分支、Copy-on-Write `.history/` 退避與 `.trash/` 自動回收 (`push`, `branch create/delete`)**：
       - Step 1：於 `main` 推送 v1 (`fid_v1 = 16xK1c8kZTzXjQM-UMVNtayP77si2Rg78`)；
       - Step 2：執行 `branch create v1.0 --from=main` 建立真實 Google Drive Shortcut (`mime_type = application/vnd.google-apps.shortcut`, `target_file_id = 16xK1c8kZTzXjQM-UMVNtayP77si2Rg78`)；
       - Step 3：於 `main` 修改同檔並推送，自動觸發 Copy-on-Write 將 `16xK1c8kZTzXjQM-UMVNtayP77si2Rg78` 移入 `.history/`，`main` 獲得新實體檔 `1G-n7X66Y05uG6K2Y7iG1e0yR3qG4vC_8`，且透過 `v1.0` Shortcut 下載仍 100% 取得凍結之 v1 內容；
       - Step 4：執行 `branch delete v1.0`，`.history/` 中引用計數歸零之 `16xK1c8kZTzXjQM-UMVNtayP77si2Rg78` 自動從 `.history/` 移入 `.trash/`（`gc_history_to_trash: ['16xK1c8kZTzXjQM-UMVNtayP77si2Rg78']`, `history_after = []`）。
- **驗證結果**：真實 Google Drive REST API v3 全鏈路實機驗證 100% 通過；`dev check gdrive-support` PASSED、`dev test gdrive-support -q` (`20/20 PASSED`)、`contributes check` PASSED。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `docs/` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `CHANGELOG.md`。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_04_0858_gdrive_bidirectional_sync_module` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

