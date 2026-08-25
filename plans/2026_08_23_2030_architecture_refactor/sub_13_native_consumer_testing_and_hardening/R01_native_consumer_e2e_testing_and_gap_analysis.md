# 原生消費者端到端測試障礙與遠端自舉解包機制調研報告 (R01)

> 子計畫名稱：`sub_13_native_consumer_testing_and_hardening`  
> 報告編號：`R01`  
> 調研日期：2026-08-25  
> 調研主題：第三方真實使用者原生情境測試問題排查、預設 Provider 策略與遠端模組自舉解包架構分析  
> 狀態：Confirmed (與開發者共同確認定稿)  

---

## 1. 調研背景與測試現場還原

在本次架構重構收尾驗收中，我們在全新獨立的 `./user/` 目錄中模擬 100% 真實下游使用者的操作流程：
1. 建立獨立資料夾 `./user/`。
2. 自 GitHub 實機下載最新起手腳本 `yscb.py`。
3. 執行初始化：`python yscb.py init ./ys-codebase`。

在執行步驟 3 時，立即暴露了真實消費者端開箱即用的兩大核心架構阻礙。

---

## 2. 核心問題排查與定稿方案

### 2.1 問題 1：預設 Provider URL 應為官方 GitHub 遠端

- **現象**：
  執行 `python yscb.py init ./ys-codebase` 時輸出：
  ```text
  [yscb] Error: Invalid provider './release'. Must be an existing local directory or valid URL.
  ```
- **根因**：
  - 目前 `yscb.py` 寫死 `DEFAULT_PROVIDER_URL = "./release"`。
  - 在官方開發端倉庫中，根目錄具備 `release/`，因此能順利自舉。
  - 但在第三方獨立工作區中，本地不存在 `./release` 目錄。若使用者未手動輸入 `--provider=<url>`，系統直接報錯崩潰。
- **定稿方案 (Zero Speculation)**：
  - **修改預設路徑為官方 GitHub 遠端**：
    將 `yscb.py` 中的 `DEFAULT_PROVIDER_URL` 預設值明確修正為官方遠端穩定 Release 倉庫：
    ```python
    DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/release"
    ```
  - 貫徹「零猜測」原則，預設一律指向官方遠端 Gateway；若開發者在本地需要測試，則顯式傳入 `--provider=./release` 或 `--provider=../release`。

---

### 2.2 問題 2：遠端 Provider 自舉時「無代碼下載」的重大缺陷 (Critical Gap)

- **現象**：
  深入檢視 `yscb.py:cmd_init` 中的遠端分支（Case B: Remote URL Provider）：
  ```python
  # Case B: Remote URL provider
  elif provider_arg.startswith(("http://", "https://", "file://")):
      manifest_url = provider_arg.rstrip("/") + "/core/manifest.json"
      with urllib.request.urlopen(req, timeout=10) as resp:
          m_data = json.loads(resp.read().decode("utf-8"))
      init_cfg["installed_modules"]["core"] = {
          "version": m_data.get("version", "1.0.0.0"), ...
      }
      # ⚠️ 嚴重缺陷：僅讀取了 manifest.json 並寫入 config，完全沒有下載 core 模組的任何代碼！
  ```
- **衝擊**：
  緊接著調用 `dispatch_module("core", ["reload"])` 時，因為 `modules/core/scripts/cli.py` 根本不存在，系統必然報錯：
  `Module 'core' is not installed or missing 'scripts/cli.py'`。
- **定稿方案：方案 A（標準庫 Zip Bundle 分發與解包機制）**：
  1. **發布端 (`dev.builder` / `dev.releaser`)**：
     - 在生成 `release/<mod>/<ver>/` 目錄時，同步產出純淨的 `<mod>.zip`（例如 `release/core/1.0.0.0/core.zip`）。
     - `core.zip` 內部只包含純淨的模組運行檔案（排除 `tests/` 與 `.yscbignore`）。
  2. **消費端 (`yscb.py init` 與 `core.installer`)**：
     - 面對遠端 Provider 時，單次 HTTP 串流下載 `<provider>/<mod>/<ver>/<mod>.zip` 至暫存檔 `.tmp.zip`。
     - 使用 Python 內建標準庫 `zipfile.ZipFile` 解包至 `.mirror/<mod>/<ver>/`。
     - 拷貝至 `modules/<mod>/` 並自動清理 `config.*.json` 模板，順暢完成 `reload` 自舉。

---

## 3. 三大技術方案評估對比表 (評估記錄存檔)

| 評估維度 | 方案 A：單一壓縮包分發 (Zip Bundle) [已採納] | 方案 B：Manifest 宣告檔案清單 (File Manifest) | 方案 C：遠端目錄 API 遍歷 (GitHub API Tree) |
| :--- | :--- | :--- | :--- |
| **運作原理** | `dev release` 同步打包 `core.zip`，HTTP 單次下載並由 Python `zipfile` 解包 | 在 `manifest.json` 宣告 `files: [...]`，依表單檔 HTTP 下載 | 調用 GitHub API 遍歷目錄樹遞迴下載 |
| **外部依賴** | **100% Python 標準庫** (`urllib` + `zipfile`) | 100% Python 標準庫 (`urllib`) | 依賴特定託管平台 API，受 Rate Limit 限制 |
| **傳輸效率** | **極高**（單次 HTTP 串流下載，內建壓縮） | 差（需多次 HTTP 連線請求） | 低（多次 API 往返） |
| **原子性保證** | **極高**（下載至 `.tmp.zip` 驗證完整後解包） | 差（中途斷線易產生半套殘留檔案） | 差 |

---

## 4. 調研結論與後續實施計畫

1. **結論已拍板**：
   - 預設 Provider 修正為官方遠端 GitHub URL。
   - 遠端自舉與安裝採用標準庫 `zipfile` Zip Bundle 機制。
2. **後續實施計畫**：
   - 本調研完成後，進入 Phase 1 (規格轉譯) ➔ Phase 2 (架構與循序圖) ➔ Phase 3 (API 介面) ➔ Phase 4 (實作計畫與測試定稿) ➔ Phase 5 (程式碼實作)。
