# 需求規格說明書 (Requirements Specification)

> 功能名稱：core_vfs_unified_virtual_file_system  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **VFS 與 URI 單向依賴解耦** | `core.uri` 維持底層純字串定址協議，不反向依賴 `core.vfs`；`core.vfs` 單向依賴 `core.uri` 進行語意解析，並承接所有統一檔案 IO 職責。`core.uri` 既有 IO helpers 轉發至 `core.vfs` 保持相容。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | **VFS 後端插槽化抽象與 OSBackend** | 於 `core/core/vfs/` 實作抽象基底類別 `VFSBackend` 與唯一具體後端 `OSBackend`。提供路徑讀寫、檢查、建立、列舉、搬移與刪除等標準方法。抽象層保留未來 `MemoryBackend` 介面但本階段不實作。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-03** | **同分區原子寫入防護** | `OSBackend` 實作 `atomic_write`（在目標檔案同一目錄下生成 `.tmp` 暫存檔，寫入後執行 flush 與 `os.fsync`，最後以 `os.replace` 原子覆蓋），杜絕斷電半寫入與跨分區 `EXDEV` 錯誤。 | P0 | [P00:DR-03] |
| **FR-04** | **工作區邊界防逃逸安全防護** | 提供安全邊界檢查機制（`assert_safe_path` / `is_safe_path`），當路徑試圖透過 `..` 或符號連結逃逸出授權工作區根目錄時主動拋出 `PermissionError`。 | P0 | [P00:DR-04] |
| **FR-05** | **全生態系原生檔案讀寫檢測** | 提供靜態 AST 掃描檢測工具，盤點現有所有模組（`core`, `dev`, `agents-workflow`, `knowledge-db`）中直接使用 `open()`、`pathlib` 與 `os.path` 進行檔案讀寫的操作點，輸出結構化清單。 | P0 | [P00:DR-05] |
| **FR-06** | **全模組檔案存取平滑遷移** | 依據盤點清單，依序將 `core` 模組內部及各領域模組之核心原生檔案讀寫點平滑遷移至 `core.vfs`，維持現有測試 100% 通過。 | P0 | [P00:DR-05] |
| **FR-07** | **重構期管制遵從** | 全程嚴格遵守禁止本地 `@build` 直裝與自部署管制，所有變更僅在 `source/` 與沙盒中執行與測試，統一對齊 `v1.1.0` 發布目標。 | P0 | [P00:DR-06] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 跨平台路徑與 URI 混用 | 無論傳入語意 URI (`project://...`)、POSIX 相對/絕對路徑、Windows 磁碟機路徑 (`C:\...`)，VFS 內部一律規範化解算為合法實體路徑。 |
| **EC-02** | 目錄穿越逃逸攻擊 (Path Traversal) | 傳入帶有 `../../../etc/passwd` 等逃逸字串時，安全守門阻斷並拋出 `PermissionError`。 |
| **EC-03** | 原子寫入過程異常中斷 | 寫入過程中若拋出異常，必須確保 `finally` 徹底清理暫存檔，且原檔案保持完整不被損毀。 |
| **EC-04** | 目標目錄不存在時寫入 | 寫入檔案時若其父層目錄不存在，自動遞迴建立目錄（`os.makedirs(exist_ok=True)`）。 |
| **EC-05** | 未設定或無效之語意協議 (!undefined) | 傳入無效或未配置之 URI 時，精準繼承或轉發 `UndefinedURIError` / `ValueError`，禁止非預期靜默吞噬。 |
| **EC-06** | 二進位與文字編碼異常 | 明確區分 `read_text` / `write_text`（預設 utf-8 編碼）與 `read_bytes` / `write_bytes`（二進位串流），支援自訂編碼。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴約束 | 100% Python 標準庫，零第三方套件依賴，維持 `core` 唯一微內核純淨性。 |
| **NFR-02** | 效能耗損 | VFS 封裝層開銷對比原生 `open` 與 IO 耗損 $\le 5\%$，檔案存在性檢查具備高吞吐能力。 |
| **NFR-03** | 相容約束 | `core.uri` 原有公有 IO helpers（`read_text`, `write_text`, `exists` 等）100% 向下相容，全生態系既有調用無損切換。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 跨平台原子寫入陷阱**：在 Linux/Windows 環境中，`os.replace` 在跨磁區（例如 `/tmp` 與 `/workspace` 為不同 mount 分區）時會拋出 `EXDEV: Invalid cross-device link`。因此原子寫入的暫存檔必須強制建立於目標檔案所在的同級目錄中，嚴禁使用系統通用臨時目錄。
- **`[!NOTE]` 路徑正規化防禦**：Windows 反斜線與 POSIX 正斜線混用可能引發路徑比對逃逸防護失效，所有傳入 VFS 的實體路徑必須統一進行 `os.path.normpath` 與 `os.path.abspath` 正規化。
- **`[!CAUTION]` 重構自部署禁止條款**：重構期間絕對禁止執行 `@build` 直裝或自部署，代碼驗證一律在 `source/` 與沙盒中執行。

---

## 5. 階段決策紀錄 (Phase Decisions)

- **[P01:DR-01] VFS 依賴 URI 之單向純淨架構**：`core.uri` 不依賴 `core.vfs`，`core.vfs` 依賴 `core.uri` 透過 `uri.resolve` 將語意目標轉為實體路徑。
- **[P01:DR-02] 後端插槽首期聚焦 OSBackend**：`VFSBackend` 介面規範定義完整的檔案與目錄語意操作，第一期僅實作 `OSBackend`，`MemoryBackend` 明確保留擴充介面但延後實作。
- **[P01:DR-03] 同目錄暫存檔原子寫入**：`atomic_write` 之暫存檔必須建立於與目標檔案相同的父目錄下，徹底防止跨磁區或掛載點引起的 `EXDEV` (Invalid cross-device link) 錯誤。
- **[P01:DR-04] 全生態系檔案讀寫靜態掃描與遷移清單**：使用 AST 靜態分析自動提取全模組 `open()` 與 `Path` 調用，形成檢測清單，作為平滑遷移之基準依據。
