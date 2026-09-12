# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_09_architecture_debt_remediation  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `AtomicEngine.act_lock` 獲取鎖與衝突時拋出 `BlockingIOError`，以及 `act_unlock` 正常釋放 | FR-01 | `python yscb.py dev test core` |
| **FT-02** | 單元測試 | 驗證 `is_path_watched` 對 `.cache/foo.json` 或 `.git/config` 返回 False，對空間 include 目錄返回 True | FR-02 | `python yscb.py dev test knowledge-db` |
| **FT-03** | 單元測試 | 驗證 `core.platform.ensure_private_venv` 正確將 site-packages 與 `.pth` 路徑加入 `sys.path` | FR-03 | `python yscb.py dev test core` |
| **FT-04** | 單元測試 | 驗證 `MasterSupervisor._write_state` 透過 VFS 原子寫入 `daemon.json` 且內容符合 dataclass 結構 | FR-04 | `python yscb.py dev test server` |
| **FT-05** | 單元測試 | 驗證 `yscb.py` 模組快取有效性與 `_is_modules_dirty` 正常讀取且關閉 FD | FR-05, FR-06 | `python yscb.py dev test core` |
| **FT-06** | 單元測試 | 驗證 `get_engine()` 返回唯一實例，且 `KnowledgeDBServiceWorker` 複用該單例 | FR-07 | `python yscb.py dev test knowledge-db` |
| **FT-07** | 單元測試 | 驗證 `VFS.copy()` / `move()` 在跨不同 backend 時拋出 `NotImplementedError` | FR-14 | `python yscb.py dev test core` |
| **FT-08** | 單元測試 | 驗證 `_GLOBAL_INDEX_CACHE` 並發加鎖保護在多線程讀寫下無異常 | FR-09 | `python yscb.py dev test knowledge-db` |
| **RT-01** | 回歸測試 | Core 全套既有單元與整合測試 100% 通過 | 全局回歸 | `python yscb.py dev test core` |
| **RT-02** | 回歸測試 | Server 全套既有單元與整合測試 100% 通過 | 全局回歸 | `python yscb.py dev test server` |
| **RT-03** | 回歸測試 | Knowledge-DB 全套既有單元與整合測試 100% 通過 | 全局回歸 | `python yscb.py dev test knowledge-db` |
| **RT-04** | 全庫回歸 | dev 與 agents-workflow 全套測試通過 | 全局回歸 | `python yscb.py dev test dev && python yscb.py dev test agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `AtomicEngine.act_lock/act_unlock` 透過 InterProcessLock 通過互斥與超時測試 | 2026-09-07 07:49 |
| **FT-02** | `Passed` | `test_is_path_watched_strict_filtering` 驗證非空間目錄與 .cache 嚴格返回 False | 2026-09-07 07:46 |
| **FT-03** | `Passed` | `test_ensure_private_venv` 驗證 site-packages 與 host_venv.pth 正確解析並注入 | 2026-09-07 07:49 |
| **FT-04** | `Passed` | `TestServerModule` 驗證 MasterSupervisor 狀態原子寫入與生命週期健康 | 2026-09-07 07:45 |
| **FT-05** | `Passed` | `_MODULE_CACHE` 與 `_is_modules_dirty` 安全 helper with open 正常運作 | 2026-09-07 07:49 |
| **FT-06** | `Passed` | `test_worker_shares_engine_pipeline` 驗證 Worker 與 CLI 共享唯一 Engine 單例 | 2026-09-07 07:46 |
| **FT-07** | `Passed` | `test_cross_backend_protection` 驗證跨後端 copy/move 拋出 NotImplementedError | 2026-09-07 07:49 |
| **FT-08** | `Passed` | `_GLOBAL_INDEX_CACHE` 具備 _CACHE_LOCK 保護，144 項測試並發讀寫 0 異常 | 2026-09-07 07:46 |
| **RT-01** | `Passed` | Core 全模組 142/142 測試 100% 通過 (17.67s) | 2026-09-07 07:49 |
| **RT-02** | `Passed` | Server 全模組 20/20 測試 100% 通過 (1.27s) | 2026-09-07 07:45 |
| **RT-03** | `Passed` | Knowledge-DB 全模組 144/144 測試 100% 通過 (8.57s) | 2026-09-07 07:46 |
| **RT-04** | `Passed` | Dev (83/83) 與 Agents-Workflow (74/74) 全套回歸 100% 通過 | 2026-09-07 07:50 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py server status` 驗證 Master/Worker 與 Watcher 背景狀態正常且原子落檔可讀 | `[跳過/免測]` | 開發者指示免測 (2026-09-07) |
| **UX-02** | 執行 `python yscb.py knowledge-db search "InterProcessLock" --preview` 驗證單例檢索秒級加速與預熱狀態正常 | `[跳過/免測]` | 開發者指示免測 (2026-09-07) |
