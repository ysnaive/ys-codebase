# 需求規格說明書 (Requirements Specification)

> 功能名稱：agents_workflow_manifest_cache_placement  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Manifest 空間與路徑分流 | 發布引擎根據 Target 來源層級進行空間與格式分流：<br/>1. 來自 `config.local` 的 Target：Manifest 寫入 `cache://agents-workflow/release_manifest.json`，內部記錄實體絕對路徑。<br/>2. 來自 `config.project` 的 Target：Manifest 寫入 `storage://agents-workflow/release_manifest.json`，內部記錄 `project://` 語意協議路徑。 | P0 | [P00:DR-01] |
| **FR-02** | 雙軌獨立 Manifest 與孤立檔案清理 (Pruning) | 發布引擎獨立維護 Local 軌與 Project 軌之發布清單與指紋。執行原子發布時，各軌獨立比對自身先前的 `published_files` 與本次新產出檔案，安全刪除不再保留的孤立舊檔案。 | P0 | [P00:DR-02] |
| **FR-03** | 舊版 Storage Manifest 遷移與標準化 | 讀取既有 `storage://agents-workflow/release_manifest.json` 時，自動容錯相容歷史絕對路徑，並於本次發布時 100% 標準化為 `project://` 相對協議路徑，徹底消除 Git 追蹤污染。 | P0 | [P00:DR-03] |
| **FR-04** | 全專案換行符號 (LF) 歸一化 | 1. 於專案根目錄新增 `.gitattributes`，宣告純文字檔案 `eol=lf`。<br/>2. 發布引擎及相關寫檔邏輯顯式宣告 `newline="\n"`，杜絕 Windows 下 Python 文字模式自動轉為 CRLF。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 舊 Manifest 含有異機歷史絕對路徑 (如 `H:\...`) | Pruning 清理時若目標檔案不存在則安全略過，嚴禁拋出例外；新寫入時依規範格式儲存。 |
| **EC-02** | 單軌啟用情境 (僅 Local 或僅 Project) | 僅讀寫與更新對應啟用軌道之 Manifest，未啟用軌道之 Manifest 保持原狀不產生無效 I/O 與空記錄。 |
| **EC-03** | URI 解析失敗或降級情境 | 若 `uri.to_uri` 或 `uri.resolve` 無法解析特定路徑，安全使用相對於專案根目錄之相對路徑作為 `project://` fallback。 |
| **EC-04** | 混合 Target 包含重複檔案 | 若 Local 與 Project target 產生相同目標路徑，按優先級物化，兩份 Manifest 各自記錄所屬 target 產出。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與 I/O | 維持 Stage 0 來源指紋提前短路機制，指紋未變且檔案皆在時 0 次磁碟寫入。 |
| **NFR-02** | 依賴約束 | 100% 恪守 Python 標準庫，零引入任何第三方模組。 |
| **NFR-03** | Git 乾淨度 | `storage://agents-workflow/release_manifest.json` 在跨機器/跨開發者執行 reload/release 後 Git diff 保持為 0。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `storage://` 受 Git 追蹤，嚴禁包含任何本機特定之絕對路徑（如 `D:\...`、`H:\...`）。
- **`[!CAUTION]`** `cache://` 受 Git 忽略，用於儲存本機私有快取狀態，可安全使用絕對路徑以加速本機 I/O 驗證。
- **`[!IMPORTANT]`** Windows 環境下 Python `open(path, "w")` 預設會將 `\n` 轉換為 `\r\n`，所有生成文字檔案必須顯式指定 `newline="\n"`。
