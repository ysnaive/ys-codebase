# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：core_vfs_unified_virtual_file_system  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「接下來打算建立兩大體系，VFS(結合現有 uri，正在考量要併入 core 還是獨立為 vfs module，但這樣就不是唯一內核 core 了) 和 server module，是否應未來遷移至這兩部分處理?」
  - 「vfs 改為與 uri 解耦，正確來說，是 vfs 相依於 uri，並檢測現在所有模組程式碼之原生檔案讀取，遷移至 vfs，目前先建置 1 種 backend 就好 (os backend)，未來預計添加 mem backend，但目前先不做」
- **核心目標**：
  - 在 `core` 模組內部建立統一的虛擬檔案系統 `core.vfs`，維持 `core` 作為生態系唯一微內核之定位。
  - **VFS 相依於 URI**：`core.uri` 作為底層純字串語意協議定址器，`core.vfs` 單向依賴 `core.uri`，將 URI 協議與底層檔案 IO 操作完美結合。
  - **Backend 插槽抽象**：設計 `VFSBackend` 抽象基底類別，第一階段落地並專注打磨 `OSBackend`（跨平台路徑正規化、同分區原子寫入 `atomic_write`、目錄邊界防護），預留未來擴充 `MemoryBackend` 之插槽。
  - **全模組原生檔案存取檢測與遷移**：全面掃描現有模組（`core`、`dev`、`agents-workflow`、`knowledge-db`）程式碼中散落的原生檔案讀寫操作（`open()`, `os.path`, `pathlib`），建立清單並遷移至 `core.vfs`。
- **邊界排除 (Explicitly Excluded)**：
  - **記憶體後端暫緩**：`MemoryBackend` 本次明確排除，留待未來專題添加。
  - **重構凍結鐵律**：本子計畫執行期間，絕對禁止本地 `@build` 直裝與自部署，待整體架構重構與遷移完成後統一發布至 `v1.1.0`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 物理封裝與唯一微內核原則**：
  - 決策：VFS 絕對不獨立為外部模組，完整封裝於 `core/core/vfs/`，由 `core.vfs` 導出 `VirtualPath` 與 `vfs` 統一中樞。維持 `core` 作為生態系唯一微內核。
- **[P00:DR-02] VFS 與 URI 單向依賴解耦**：
  - 決策：`core.uri` 維持獨立、純粹之語意字串協議定址層；`core.vfs` 單向相依於 `core.uri`（透過 `uri.resolve` 解析實體掛載目標）。`core.uri` 不反向依賴 `vfs`，維護架構階層純淨。
- **[P00:DR-03] Backend 插槽化架構 (OSBackend First)**：
  - 決策：定義抽象介面 `VFSBackend`。第一期專注落地跨平台強化的 `OSBackend`（消除 Windows/Linux 斜線差異、長路徑前綴處理、同分區原子寫入 `os.replace`、安全備份回滾）；預留未來 `MemoryBackend` 介面，本次不實作。
- **[P00:DR-04] 工作區邊界安全防護 (Anti-Escape)**：
  - 決策：`vfs` 與 `OSBackend` 內建路徑邊界防護 (`is_safe_path` / `assert_safe_path`)，預防路徑穿越（Path Traversal / `..`）逃逸出專案根目錄或授權空間。
- **[P00:DR-05] 全生態系模組原生檔案讀寫盤點與平滑遷移**：
  - 決策：建立 AST / 正則掃描腳本檢測全庫業務代碼之 `open()` 與檔案讀寫點，優先完成 `core` 自舉遷移，並將 `dev`、`agents-workflow`、`knowledge-db` 的核心檔案讀寫點平滑切換至 `core.vfs`。
- **[P00:DR-06] 重構期自部署管制遵循**：
  - 決策：本子計畫代碼改動僅在 `source/` 與沙盒中驗證，嚴格禁止執行 `@build` 直裝或部署至 `.modules/` 運行端。

---

## 3. 開放議題與確認紀錄

- [x] 確定 VFS 歸屬於 `core.vfs`，維持唯一微內核定位。
- [x] 確定 VFS 單向依賴 URI，解耦反向依賴。
- [x] 確定第一階段僅實作 `OSBackend`，`MemoryBackend` 延後。
- [x] 確定納入全模組原生檔案存取檢測與遷移。
- [x] 確定嚴格遵循重構期 `@build` 凍結與禁止自部署管制。
