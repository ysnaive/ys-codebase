# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：core_vfs_unified_virtual_file_system  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書 (`P03_api_spec.md`) 中具備 1:1 對應之類別、函式與簽名。
- [x] **邊界防護**：EC-01 ~ EC-06（跨平台路徑、逃逸阻斷、原子失敗清理、父目錄自動遞迴、編碼防護）在 OSBackend 與 VFS 中皆有具體錯誤處理與防護機制。
- [x] **依賴純淨**：100% Python 標準庫，零第三方外部套件依賴，嚴格遵守 NFR-01 ~ NFR-03。
- [x] **重構管制遵從**：嚴禁執行 `@build` 自部署，全數於 `source/` 與沙盒中驗收。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/vfs.md` | New | VFS 統一虛擬檔案系統架構、OSBackend、VirtualPath 與用法指南 |
| **模組手冊** | `docs/core/uri.md` | Modify | 標註 URI 與 VFS 解耦職責，更新語意協議說明 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 記錄 DN-08 (VFS 微內核與 URI 單向依賴、同目錄原子寫入防護) |
| **發布日誌** | `CHANGELOG.md` | Modify | 登記子計畫成果與 VFS 微內核落地 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1 (循環引用風險)**：若 `core.uri` 底層相容 helpers 轉發至 `core.vfs`，而 `core.vfs` 內部調用 `core.uri.resolve`，是否引發 Python 循環引用 (Circular Import) 導致導入失敗？  
> 💡 **防護解法**：`core.uri` 保持為純協議層，模組載入階段不載入 `core.vfs`；其底層 IO helpers 採延遲載入 (Lazy import)；`core.vfs.vfs.py` 亦於解析時調用 `core.uri.resolve`，徹底切斷頂層模組載入期的循環依賴鏈。

> ❓ **尖銳問題 2 (同目錄原子寫入衝突與垃圾檔殘留)**：多程序/執行緒同時寫入同一檔案，或寫入中斷電/異常時，是否會造成暫存檔衝突或磁碟垃圾？  
> 💡 **防護解法**：暫存檔命名採隱藏唯一命名規範：`.<basename>.tmp.<pid>_<tid>_<uuid4[:8]>`；contextmanager 在任何未正常 commit 的退出情境下（無論異常或 KeyboardInterrupt），`finally` 區塊保證 100% 呼叫 `os.remove` 清理暫存檔，確保零垃圾殘留。

> ❓ **尖銳問題 3 (跨生態系模組原生 open 遷移風險)**：生態系模組若貿然全面替換 `open`，若有未覆蓋邊界可能引發不可預期的退化？  
> 💡 **防護解法**：研發 AST 靜態檢測工具提取全模組直接調用清冊；嚴格執行平滑漸進遷移策略：先遷移 `core` 模組內部原生讀寫並達成 100% 測試守門，再分模組平滑遷移並在沙盒中執行全量回歸。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實作 `core/core/vfs/base.py`（定義 `VFSBackend` 抽象基類）
- [ ] **TASK-02**：實作 `core/core/vfs/os_backend.py`（實作 `OSBackend`、`atomic_write`、`assert_safe_path`）
- [ ] **TASK-03**：實作 `core/core/vfs/vfs.py`（實作 `VFS` 核心中樞、單向整合 `core.uri.resolve`）
- [ ] **TASK-04**：實作 `core/core/vfs/path.py`（實作 `VirtualPath` 物件導向介面）與 `core/core/vfs/__init__.py`
- [ ] **TASK-05**：更新 `core/core/uri.py`（將舊 IO helpers 轉發至 `core.vfs`）與 `core/core/__init__.py`
- [ ] **TASK-06**：編寫單元測試 `source/core/tests/test_vfs.py`，覆蓋 FT-01~05 與 ET-01~03
- [ ] **TASK-07**：研發全生態系原生檔案讀寫 AST 檢測工具 `scripts/scan_native_io.py`
- [ ] **TASK-08**：遷移 `core` 模組內部原生讀寫點至 `core.vfs`，驗證全庫回歸測試 RT-01~02

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 延遲載入防循環依賴**：`core.uri` 相容轉發與 `core.vfs` 協議解析均使用內部函式延遲載入，架構層面消除循環導入。
- **[P04:DR-02] 暫存檔命名與安全掃除鐵律**：同目錄原子寫入強制採唯一後綴，並在 `finally` 區塊無條件自我清理。
- **[P04:DR-03] AST 靜態檢測作為遷移驗證基準**：全生態系原生檔案讀寫檢測以 AST 提取作為 SSOT 報告。
