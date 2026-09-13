# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | DEFAULT_PROVIDER_URL 修正與 self-update 位址解算 | 修正 `DEFAULT_PROVIDER_URL` 指向 `https://raw.githubusercontent.com/ysnaive/ys-codebase/main/release`；`self-update` 正確自 repo 根目錄（`.../main/yscb.py`）取得更新腳本，支援 `--url` 覆寫；恢復 `main()` 中 `self-update` 專屬派發。 | P0 | [P00:DR-01] |
| **FR-02** | yscb init 動態 Version Discovery | `cmd_init` 淘汰寫死 `1.0.0.0.zip`；本地探測 `core/*.zip` 或 `release/core/*.zip` 最高 semver，遠端探測 `core/index.json` 之 `versions`；動態寫入解算版本至 `yscb.config.json`。 | P0 | [P00:DR-02] |
| **FR-03** | yscb init 支援 `--fix` 自癒與預設 `".yscb"` 根目錄 | 全新 `init` 未傳入 `yscb_root` 預設為 `".yscb"`；當 `yscb.config.json` 存在但 core 遺失/損毀（或指定 `--fix`），自動自 Provider 抓取最新 core 重新安裝並**強制連鎖自動調用 `core reload`**。 | P0 | [P00:DR-05] |
| **FR-04** | yscb.py.bak 內部 gitignore 管理 | 將 `yscb.py.bak` 與 `*.bak` 納入 `INTERNAL_IGNORE_PATTERNS`，透過 `generate_internal_gitignore` 自動非破壞性維護 `.gitignore`，杜絕備份檔污染 git status。 | P1 | [P00:DR-04] |
| **FR-05** | UpdateChecker 快取及時失效與刷新 | `UpdateChecker` 提供快取失效與已更新模組清除能力；於 `cmd_update`、`cmd_install` 成功後主動刷新，消除終端過期升級提示洗頻。 | P1 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Provider 離線或找不到可用 core 套件 | 輸出 `[yscb] Error: Cannot locate core package in provider '{provider}'.` 並終止，不建立或損毀既有設定檔。 |
| **EC-02** | `init --fix` 時既有設定檔損毀 (非合規 JSON) | 捕捉 JSONDecodeError，提示設定檔損毀並拒絕覆寫，保護環境。 |
| **EC-03** | `self-update` 下載腳本語法錯誤 (例如代理伺服器回傳 HTML 報錯) | 透過 `ast.parse` 語法驗證，攔截 SyntaxError，放棄替換並清理臨時檔。 |
| **EC-04** | `self-update` 檔案替換因 OS 權限或鎖定失敗 | 清理 `.tmp` 檔案，恢復原檔，輸出結構化錯誤原因。 |
| **EC-05** | 既有設定檔已存在且 core 模組完好，未傳入 `--fix` | 輸出警告提示 `[yscb] Configuration already exists... Use --fix to repair.`，維持退出碼 1。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方依賴 | `yscb.py` 宿主與 `core` 模組實作 100% 採用標準函式庫，嚴禁引入任何額外 pip 套件。 |
| **NFR-02** | 執行效率與逾時保護 | 本地檔案掃描與 semver 比對耗時 $< 5\text{ms}$；遠端網路探測 timeout 嚴格限制在 5~10 秒，網路不可達時靜默或優雅降級。 |
| **NFR-03** | 冪等性與安全性 | `generate_internal_gitignore` 具備冪等性；`self-update` 與 `init --fix` 具備失敗原子回滾保護。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `yscb.py` 為全生態系單檔宿主，在尚未載入 `core` 前僅依賴自身的純標準庫函式；因此 `cmd_init`、`cmd_self_update` 等功能必須保持自包含 (Self-Contained)，不得在函式頂層直接依賴 `core` 套件。
- **`[!NOTE]`** `self-update` 在 Windows 平台上覆寫自身時，直接覆寫被佔用的檔案會報 `PermissionError`，因此必須遵循「寫入 `.tmp` -> 複製原始至 `.bak` -> `os.replace` 原子替換」的最佳實踐。
