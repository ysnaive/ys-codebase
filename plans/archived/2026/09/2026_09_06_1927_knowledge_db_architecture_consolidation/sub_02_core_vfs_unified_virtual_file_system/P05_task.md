# 實作任務清單 (Task Breakdown)

> 功能名稱：core_vfs_unified_virtual_file_system  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core/core/vfs/base.py`，定義 `VFSBackend` 抽象基類
- [x] **TASK-02**：實作 `core/core/vfs/os_backend.py`，實作 `OSBackend`、`atomic_write` 與 `assert_safe_path`
- [x] **TASK-03**：實作 `core/core/vfs/vfs.py`，實作 `VFS` 中樞並單向整合 `core.uri.resolve`
- [x] **TASK-04**：實作 `core/core/vfs/path.py`（`VirtualPath`）與 `core/core/vfs/__init__.py` 導出
- [x] **TASK-05**：更新 `core/core/uri.py`（相容轉發至 `core.vfs`）與 `core/core/__init__.py` 導出
- [x] **TASK-06**：編寫單元測試 `source/core/tests/test_vfs.py`（覆蓋 FT-01~05, ET-01~03）
- [x] **TASK-07**：研發全生態系原生檔案讀寫 AST 檢測工具 `scripts/scan_native_io.py`
- [x] **TASK-08**：遷移 `core` 模組內部原生讀寫點至 `core.vfs`，執行全量測試驗證

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 (全面依據 P01~P04 規劃落地，全生態系 445/445 測試通過) | - |
