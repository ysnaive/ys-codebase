# 需求規格說明書 (Requirements Specification)

> 功能名稱：ecosystem_safe_hot_update_and_jit_synchronization  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.contributes` JIT 快照嗅探與自愈聚合 | 於 `core.contributes.get()` 讀取路徑前置 Freshness Gate。快照元資料儲存於 `cache://core/contributes.meta.json`，比對清單包含 `module://*/contributes/*.json`、`module://*/contributes.json`、`config://*/contribute.json` 與 `yscb.config.json`。若快取遺失或任一來源之 `mtime` 或 `size` 變更，自動原地觸發 `ContributesAggregator.scan_and_inject()` 重新聚合並更新快照。 | P0 | [P00:DR-02] |
| **FR-02** | `agents-workflow` JIT Release Targets 投影同步 | 於 `agents-workflow` CLI 入口管線前置加入指紋嗅探。比對既有 `ReleasePublisher.compute_source_fingerprint()` 與 Manifest 快照，當來源資產（`assets/`、`contributes`、`snippets/`）或 Target 配置變更時，自動調用 `ReleasePublisher.release_all()` 原子物化至 `.agents/` 等 Target 目錄與 `AGENTS.md`。 | P0 | [P00:DR-03] |
| **FR-03** | `yscb.py` / `core` 12 小時週期來源版本探測與非阻塞提示 | 於 `core` 實作 `UpdateChecker` 服務，維護 `cache://core/update_check.json`。記錄上次探測時間戳 `last_checked_at` 與版本比較結果。當時間間隔超過 43,200 秒（12 小時）時，發起 2 秒短超時輕量請求比對 Provider 端之 `index.json`；若發現更新，於 CLI 結束或 `core status`/`list` 呈遞非阻塞友善提示，支援 `--no-update-check` 與環境變數停用。 | P1 | [P00:DR-04] |
| **FR-04** | `dev` 模組 Dogfooding 閉環加固與 `--sync` 支援 | 於 `dev test <mod>` 測試成功後提供直裝指引提示；新增 `--sync` 快捷旗標，在單元與整合測試 100% Passed 後自動鏈式調用 `python yscb.py install <mod>@build`，達成測試兼安裝之一步閉環。 | P1 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 來源檔案遭刪除或非合法 JSON | JIT 嗅探檢測到檔案遺失或解析失敗時，原子清理損毀快取並重新聚合；對損毀之個別 Donor 檔案記錄 Warning 日誌並優雅跳過，避免阻塞微內核載入。 |
| **EC-02** | 來源更新探測網路超時、DNS 失敗或離線環境 | HTTP 請求設置 2.0 秒短超時，所有網路層例外（URLError、TimeoutError、HTTPError）強制以靜默 `try...except` 捕獲，絕不噴出 Traceback，並將 `last_checked_at` 更新為當前時間以防高頻重試。 |
| **EC-03** | Provider 回傳格式畸變或缺少 index.json | 嚴格驗證回應之 JSON 結構與 SemVer 格式；欄位異常時直接將該模組標記為無可用更新，記錄 Debug 日誌。 |
| **EC-04** | 多進程並發讀寫快取檔案衝突 | `contributes.meta.json` 與 `update_check.json` 寫入時強制遵循「先寫 `.tmp` 再 `os.replace`」之原子替換慣例，杜絕並發半寫狀態。 |
| **EC-05** | JIT 投影同步時目標檔案遭作業系統鎖定或唯讀 | 捕獲 `PermissionError` 與 `OSError`，輸出警告提示並跳過該檔案，保證 CLI 主指令正常執行完畢。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 延遲 | 在無變更（Clean）狀態下，JIT 檔案狀態嗅探比對耗時必須 $\le 2\text{ms}$；全生態系日常 CLI 保持 sub-100ms 內極速完成。 |
| **NFR-02** | 架構 / 零外部依賴 | 100% 依賴純 Python 標準庫（`os.stat`、`hashlib`、`json`、`time`、`urllib.request`），嚴禁引入 `watchdog` 或外部守護進程。 |
| **NFR-03** | 測試覆蓋率與向後相容 | 為 JIT 嗅探、自愈管線、12hr 節流、離線降級與 `--sync` 旗標編寫全量單元測試，全生態系既有 270+ 測試 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `yscb.py` 採用同進程 `runpy.run_path` 調度分發，因此在 CLI 入口實作時應避免污染全域模組單例快取，並注意進程結束前輸出提示之時機。
- **`[!IMPORTANT]`** 12 小時來源端探測嚴禁在無節流情況下發起網路請求，所有非必要操作必須依賴本地 `update_check.json` 快取以維持零開銷。
- **`[!CAUTION]`** `agents-workflow` 的 JIT 投影物化會直接修改專案目標檔案（如 `.agents/`），因此必須嚴格依據來源指紋比對結果，僅在確實發生實質變更時才執行物化，避免無意義修改檔案 mtime。
