# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Draft  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 下游專案反饋：`DEFAULT_PROVIDER_URL` 指向過期儲存庫路徑 `https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release`，且執行 `self-update` 時以 `provider.rstrip("/") + "/yscb.py"` 拼接導致 HTTP 404（`yscb.py` 位於儲存庫根目錄而非 `release/` 目錄下）；此外在近期的入口瘦身中 `cmd_self_update` 派發遺漏，導致指令失效。
  2. `yscb init` 執行時硬編碼 `1.0.0.0.zip` 與 `"version": "1.0.0.0"`，無法自適應 provider 當前最新 core 版本（如 1.1.0.1），新專案初始化後立即面臨舊版核心甚至 404 找不到檔案。
  3. 下游專案自舊版 v1.0.0.0 升級時，歷史目錄使用 `modules/`，新版改為隱藏目錄 `.modules/`，缺乏核心檢測與自癒機制，導致升級後找不到核心。
  4. 執行 `self-update` 產生的 `yscb.py.bak` 備份檔未被納入 `INTERNAL_IGNORE_PATTERNS` 與 `.gitignore`，污染專案 git 狀態；且模組更新/安裝完成後，`update_checker` 快取未及時清除/刷新，導致終端持續顯示過期的升級提示。
  5. 開發者明確指示：`init` 需添加功能需求（FR），除初次初始化外，提供 `fix` 功能/自癒機制：檢測 core 安裝是否正常；在 `yscb.config.json` 存在且設定正確時，若無法抓到 core module，自動更新並抓取新版本 core module，完成後自動連鎖觸發 `reload`；真正全新 `init` 時若未提供 `yscb_root`，預設路徑應為 `".yscb"`。
- **核心目標**：
  1. **修復發布提供者與 Self-Update 機制**：修正 `DEFAULT_PROVIDER_URL` 為現行官方儲存庫 `https://raw.githubusercontent.com/ysnaive/ys-codebase/main/release`；健全化 `self-update` 之 `yscb.py` 來源位址解算（自動錨定至 repo 根目錄）；恢復 `yscb.py` Host 端的 `self-update` 一級命令分流與語意宣告。
  2. **`yscb init` 動態解析最新 core 版本**：重構 `cmd_init`，支援自 Provider（本地目錄或遠端 `index.json`）動態探測並選取最高語意版本 core 壓縮包，動態寫入實際安裝之版本號至 `yscb.config.json`，徹底淘汰硬編碼 `1.0.0.0`。
  3. **Gitignore 補齊與 UpdateCheck 快取及時失效**：將 `yscb.py.bak` 納入內部 `.gitignore` 剛性區塊管理；在模組完成 `install`、`update` 或 `restore` 後，主動刷新/失效 `cache://core/update_check.json`，消除洗頻式過期提示。
  4. **`init` 支援自癒修復 (`--fix`)、預設 `".yscb"` 目錄與自動連鎖 `reload`**：全新初始化時，若命令列未指定 `yscb_root`，預設為 `".yscb"`；當 `yscb.config.json` 存在且配置正確但無法抓到 core 模組（含升級斷層或損毀）時，透過 `fix` 自癒修復自動自 Provider 抓取最新版 core 模組恢復 `.modules/core`，修復完成後強制自動連鎖觸發 `core reload`。
- **邊界排除 (Explicitly Excluded)**：
  - 本子計畫聚焦於 Host 自舉入口 (`yscb.py`)、`core` 分發與生命週期管理 (`installer.py`, `update_checker.py`, `uri.py`)。
  - 不引入獨立複雜的檔案移動式 `modules/` 遷移分支，統一以 `fix` 自癒機制拉取最新 core 模組處置。
  - `server` 依賴宣告與熱重載遷移交由 sub_04 處理；組態層級與 hook 可觀測性交由 sub_03 處理；agents-workflow 區塊保留交由 sub_05 處理。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] DEFAULT_PROVIDER_URL 與 self-update 雙軌位址解算定案**：
  - 統一更新 `DEFAULT_PROVIDER_URL` 為 `https://raw.githubusercontent.com/ysnaive/ys-codebase/main/release`。
  - `self-update` 來源解析演算法：
    - 若 provider 包含 `/release`，其對應之 `yscb.py` 預設定位於 `os.path.dirname(provider) + "/yscb.py"`（即 repo 根目錄）；
    - 若指定本地目錄，先檢查同層或父層之 `yscb.py`；
    - 支援 `--url=<custom_url>` 顯式指定遠端或本機腳本位址；
    - 恢復 `main()` 中對 `self-update` 指令的專屬分流，並將其列入 Host 免 core 初始化指令清單。
- **[P00:DR-02] yscb init 動態 Version Discovery 架構**：
  - 本地 Provider：掃描 `core/` 或 `release/core/` 下所有 `*.zip` 檔案，以純標準庫輕量 semver 比對解析最大版本；
  - 遠端 HTTP Provider：嘗試讀取 `<provider>/core/index.json` 取得 `versions` 陣列選取最新版；若不可達或逾時，則以內建已驗證之最新安全版本清單 fallback 兜底。
  - 初始化成功後，將動態解算之真實版本寫入 `yscb.config.json` 的 `installed_modules.core.version`。
- **[P00:DR-03] (已捨棄 / 由 DR-05 統一吸收)**：
  - 捨棄獨立之 `modules/` ➔ `.modules/` 實體檔案改名遷移邏輯，杜絕邊界脆弱性。
  - 舊版環境或歷史目錄升級導致無法載入 core 的問題，統一交由 `[P00:DR-05]` 之自癒修復管線覆蓋。
- **[P00:DR-04] yscb.py.bak 忽略規則與 UpdateCheck 快取失效閉環**：
  - 在 `INTERNAL_IGNORE_PATTERNS` 增加 `"yscb.py.bak"` 與 `"*.bak"`。
  - 在 `Installer.cmd_update` 與 `cmd_install` 成功後，調用 `UpdateChecker.invalidate_cache()` 或直接移除已更新模組的提示紀錄，保證下一次 CLI 呼叫不再呈現已解決的升級提示。
- **[P00:DR-05] yscb init 自癒修復機制 (`--fix`)、預設根目錄與連鎖 reload 定案**：
  - **預設根目錄規範**：全新 `init` 時若未傳入 `yscb_root` 參數，預設路徑變更為 `".yscb"`。
  - **自癒修復核心 (`init --fix`)**：
    - 當 `yscb.config.json` 已存在時：
      - 若使用者傳入 `--fix` 旗標，或常規呼叫但偵測到 core 模組損毀/缺失（如升級後遺失 `.modules/core`）時，觸發自癒修復流程；
      - 自癒流程自既有設定檔讀取 `default_provider` 與 `yscb_root`，依 `[P00:DR-02]` 動態探測並解壓最新版 core 壓縮包至 `.modules/core`，同步更新設定檔中 core 的 `version` 與 `provider`；
      - **強制連鎖觸發 reload**：core 模組物化完成後，**自動且強制連鎖調用 `core reload`**，立即刷新依賴注入與 JIT 產物，保證單次命令即刻恢復就緒；
      - 若設定檔已存在且 core 模組完好且未指定 `--fix`，則維持既有安全保護，提示環境已初始化並引導可使用 `--fix` 強制修復。

---

## 3. 開放議題與確認紀錄

- [x] `self-update` 在 Windows 下覆寫正在執行的 Python 腳本是否安全？已確認：Python 在 Windows 下讀取完腳本後不會鎖定 `.py` 檔案本體，採用先寫 `.tmp`、備份 `.bak`、再 `os.replace` 的原子替換方式已驗證完全安全。
- [x] `yscb init` 在無網路環境下是否仍能正常運作？已確認：指定本地目錄或 mock provider 時均走本地 filesystem 探測，離線 100% 可用。
- [x] 捨棄 DR-03 後如何確保舊專案升級？已確認：舊專案升級若發生 core 缺失，執行 `python yscb.py init --fix` 即可一鍵抓取最新 core 並連鎖 reload 恢復。
- [x] `init --fix` 是否會破壞已安裝的其他模組設定？已確認：自癒修復僅針對缺失之 `core` 模組進行抓取與刷新，嚴格保留既有 `installed_modules` 中其他模組宣告與自訂組態。
