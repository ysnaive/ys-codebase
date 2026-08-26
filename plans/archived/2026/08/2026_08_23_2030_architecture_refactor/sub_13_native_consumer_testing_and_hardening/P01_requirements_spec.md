# 需求規格說明書 (Requirements Specification)

> 功能名稱：第三方真實使用者原生情境測試、問題排查與框架加固 (Native Consumer Testing & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00/調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md), [R01](./R01_native_consumer_e2e_testing_and_gap_analysis.md), [R02](./R02_full_zip_packaging_architecture_analysis.md)  
> 狀態：Draft (Phase 1 待審核)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格說明 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- |
| **FR-01** | 預設 Provider 遠端化與零猜測 | 1. 將 `yscb.py` 中的 `DEFAULT_PROVIDER_URL` 剛性設定為官方 GitHub 遠端穩定 Release 路徑：`https://raw.githubusercontent.com/ysnaive/agent.workflow/main/release`。<br/>2. 移除任何對本地 `./release` 的隱式強制依賴，貫徹零猜測原則。<br/>3. 本地開發/測試若需使用本機發布庫，透過顯式參數傳遞（例：`--provider=./release` 或 `--provider=../release`）。 | P00 §2.1<br/>R01 §2.1 |
| **FR-02** | 發布端純淨單檔 Zip 打包 | 1. 升級 `dev.builder.package_release` / `dev.releaser`，發布時直接產出 `release/<mod>/<ver>.zip`（例：`release/core/1.0.0.0.zip`）。<br/>2. 發布庫中**不再落地展開散裝目錄**，保持純淨單檔形式。<br/>3. Zip 內部結構包含 `manifest.json`, `scripts/`, 模組代碼；排除 `tests/` 與 `.yscbignore`。 | P00 §2.2<br/>R02 §2.1 |
| **FR-03** | 開發端建置單檔 Zip 打包 | 1. 升級 `dev.builder.build_module`，開發建置時直接產出 `build/<mod>/<ver>.build.zip`（例：`build/core/1.0.0.build.zip`）。<br/>2. 建置庫中**不再落地展開散裝目錄**。<br/>3. Zip 內部 100% 完整包含 `tests/` 供沙盒測試解包使用。 | P00 §2.2<br/>R02 §2.1 |
| **FR-04** | 同 X.Y.Z Revision 單檔淘汰管理 | 1. `release/<mod>/index.json` 維護版本清冊，記錄合法版本列表（如 `["1.0.0.0"]`）。<br/>2. 當同 `X.Y.Z` 發布新 Revision（如 `1.0.0.2` 覆蓋 `1.0.0.1`）時，系統自動刪除 `1.0.0.1.zip` 單檔並更新 `index.json`，零遞迴目錄刪除開銷。 | P00 §2.2<br/>R01 §3, R02 §2.2 |
| **FR-05** | 統一同構 Zip 解包自舉與安裝管線 | 1. `yscb.py:cmd_init` 與 `core.installer` / `AtomicEngine` 統一一律採用「取得 Zip（本地複製或遠端下載）➔ 解包」管線。<br/>2. 面對遠端 Provider 時，單次 HTTP 串流下載 `<provider>/<mod>/<ver>.zip` 至 `.tmp.zip`。<br/>3. 透過 Python 標準庫 `zipfile.ZipFile` 解包至 `modules/<mod>/`，自動剝除 `config.*.json` 模板並觸發 `reload`。 | P00 §2.2<br/>R01 §2.2, R02 §3 |

---

## 2. 邊界與異常情況處理 (Edge Cases)

| 邊界編號 | 邊界情境說明 | 防禦處置與預期行為 | 對應需求 |
| :--- | :--- | :--- | :--- |
| **EC-01** | 遠端下載中途網路中斷或 Zip 檔案損壞 | 1. 遠端 Zip 必須先完整寫入 `.tmp.zip`。<br/>2. 解包前使用 `zipfile.is_zipfile()` 與 `testzip()` 執行完整性驗證。<br/>3. 若損壞或校驗失敗，立即拋出 `DownloadCorruptedError`，清除 `.tmp.zip`，不污染 `modules/`。 | FR-05 |
| **EC-02** | 本地 Provider 模式 (`file:///` 或本機路徑) | 面對本地目錄 Provider 時，系統直接拷貝本機 `<provider>/<mod>/<ver>.zip`，解包流程與遠端 100% 同構。 | FR-05 |
| **EC-03** | 遠端請求逾時 (Network Timeout) | 所有遠端 `urllib.request` 請求設定 30 秒剛性 Timeout，附帶標準 `User-Agent: yscb-host/2.0` 標頭；逾時精準回報網路連線失敗訊息。 | FR-05 |
| **EC-04** | 遠端 Provider 缺少目標版本或 Zip 404 | HTTP 狀態碼非 200 時（如 404），精準拋出 `PackageNotFoundError: Remote package '<url>' not found`，不產生殘留空目錄。 | FR-05 |

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01（100% Python 標準庫）**：所有 Zip 打包與解包 (`zipfile`)、遠端下載 (`urllib.request`) 100% 基於 Python 3.10+ 標準庫，零任何外部第三方依賴。
- **NFR-02（完全同構管線）**：本地與遠端套件消費代碼路徑 100% 統一為單一 Zip 解包管線，消除雙軌維護成本。
- **NFR-03（極致乾淨檔案樹）**：全系統僅 `source/` 與 `modules/` 存在明文代碼目錄，中間產物與套件庫全部為單一 `.zip`。
- **NFR-04（回歸測試通過率 100%）**：全模組（`core`, `dev`）單元、合約與新增 Zip 自舉測試 100% 綠燈通過。

---

## 4. 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充功能名稱 | 觸發模式 | 判定結果 | 評估理由 |
| :--- | :--- | :---: | :--- |
| `dogfooding_pipeline_ext` | always | **Excluded (排除)** | 本計畫為標準遠端自舉與 Zip Bundle 強化，依循標準四步閉環流水線執行。 |
