# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 快取隔離零 Fallback 固化與搜尋輸出 URI 連結格式重構  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 快取儲存根目錄零 Fallback 固化 | 重構 `SpaceManager._get_storage_root()`，當 `_safe_resolve_uri("cache://knowledge-db/")` 失敗且未傳入自訂 `storage_dir` 時，強制拋出 `InvalidSpaceConfigError`，徹底廢除 `Path("./.cache/knowledge-db")` 隱式回退。 | P0 | [P00:DR-01] |
| **FR-02** | 檔案 URI 與 Markdown 連結解算能力 | 於 `KnowledgeEngine` 實作 `to_file_uri(file_path, line=None)` 與 `format_file_link(file_path, line=None, end_line=None)`，支援將工作區路徑轉譯為 IDE 相容之 `file:///` 超連結與 `[rel_path:line](file:///...)` Markdown 標籤。 | P0 | [P00:DR-02] |
| **FR-03** | CLI 檢索輸出全面適配 Markdown 連結 | 重構 `scripts/cli.py` 中 `search` 指令之 3 種文字呈現模式（簡易模式、預覽模式、詳細模式），檔案標頭統一顯示為可點擊之 Markdown 連結；`--json` 輸出模式於各結果項目擴充 `file_uri` 欄位。 | P0 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 跨平台 (Windows / POSIX) 檔案 URI 協議相容性 | Windows 路徑轉為 URI 時需確保前置斜線與正斜線轉換（例如 `H:\path\file.py` ➔ `file:///H:/path/file.py`），並支援 `#L{line}` 錨點格式。 |
| **EC-02** | 獨立沙盒測試環境無 core 上下文 | 在無 `core` 模組環境下直接實例化 `KnowledgeEngine()` 或呼叫 `SpaceManager.storage_dir` 時，精準拋出 `InvalidSpaceConfigError`，防止任何 CWD 寫入副作用。 |
| **EC-03** | 單行號 vs 跨行區間格式化防禦 | 當符號具備跨行區間（`end_line > line_number`）時，連結標籤顯示為 `L{line}-{end_line}`，錨點指向起點 `file:///...#L{line}`；無行號時僅顯示檔名。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 純原生零依賴 | 100% 採用 Python 原生標準庫 (`pathlib`, `urllib.parse`)，零第三方套件依賴。 |
| **NFR-02** | 效能與相容性 | URI 格式化在 CLI 輸出時即時解算，不增加檢索與反序列化索引之計算負擔；保持既有資料結構向下相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 專案全生態系測試執行器（`dev.testing.runner`）會在加載模組自訂測試時清理 `sys.path`，因此所有自包含測試若需存取檔案快取，必須在測試案例中顯式透過 `tempfile.TemporaryDirectory()` 傳入 `storage_dir`。
