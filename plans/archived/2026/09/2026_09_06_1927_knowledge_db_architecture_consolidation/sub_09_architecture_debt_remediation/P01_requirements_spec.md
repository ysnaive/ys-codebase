# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_09_architecture_debt_remediation  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Core 進程鎖統一 | `AtomicEngine.act_lock/act_unlock` 廢除自製 JSON 鎖，全面改用 `core.platform.InterProcessLock`，獲取逾時拋出 `BlockingIOError` | P0 | [P00:DR-01] H-01 |
| **FR-02** | Watcher 嚴格空間過濾 | `KnowledgeDBServiceWorker.is_path_watched` 徹底移除 L159~163 `workspace_root` 寬鬆兜底，非註冊空間路徑一律返回 `False` | P0 | [P00:DR-01] H-02 |
| **FR-03** | 虛擬環境路徑解析下沉 | `core.platform` 新增 `ensure_private_venv`，統一支援 Windows/POSIX 與 `host_venv.pth` 解析，並由 master/worker 複用 | P1 | [P00:DR-01] M-01 |
| **FR-04** | Master 狀態原子落檔 | `MasterSupervisor._write_state` 改用 `core.vfs.write_json(..., atomic=True)`，確保 `daemon.json` 原子替換 | P1 | [P00:DR-01] M-02 |
| **FR-05** | yscb 冷啟動模組快取 | `yscb.py.dispatch_module` 引入 `_MODULE_CACHE`，避免重複 `spec.loader.exec_module` | P1 | [P00:DR-01] M-03 |
| **FR-06** | yscb 檔案描述符洩漏修復 | `_is_modules_dirty` 中讀取 `manifest.json` 抽取為安全 helper 函式，確保 `with open` 關閉 FD | P1 | [P00:DR-01] M-04 |
| **FR-07** | Engine 進程單例共享 | `knowledge_db.engine` 導出 `get_engine()`，ServiceWorker 與 CLI 共享同一單例實例，避免同進程記憶體重複 | P1 | [P00:DR-01] M-05 |
| **FR-08** | Guard 安全邊界文件 | `core.guard` 補齊 Docstring，明確 Guard Token 為防止 CLI 繞道之防呆標識而非對抗逆向工程之密鑰 | P2 | [P00:DR-01] L-01 |
| **FR-09** | 索引記憶體快取加鎖 | `pipeline._GLOBAL_INDEX_CACHE` 存取加入 `_CACHE_LOCK = threading.RLock()`，防範 CLI 與 Watcher 線程競態 | P2 | [P00:DR-01] L-02 |
| **FR-10** | 派發 HTTP 逾時動態調優 | `_try_hot_dispatch` 支援透過 `os.environ.get("YSCB_DISPATCH_TIMEOUT", "120.0")` 自訂逾時時間 | P2 | [P00:DR-01] L-03 |
| **FR-11** | Engine 內部常數導入清理 | `knowledge_db.engine` 移除 L17~28 未使用的 7 個 Formatter 內部常數導入（`AUTO_BUDGET_CHARS` 等） | P2 | [P00:DR-01] L-04 |
| **FR-12** | yscb 主入口邏輯解構 | `yscb.py.main()` 拆解四層嵌套三元表達式，改以清晰之 `if/elif/else` 條件分流 | P2 | [P00:DR-01] L-05 |
| **FR-13** | ServiceWorker Context 契約 | `BaseServiceWorker.start` 補齊 `context` 欄位契約規格說明（`yscb_root`, `workspace_root`, `config` 等） | P2 | [P00:DR-01] D-01 |
| **FR-14** | VFS 跨後端操作防護 | `VFS.copy()` 與 `VFS.move()` 檢查 `src_backend` 與 `dst_backend`，跨後端時拋出明確 `NotImplementedError` | P2 | [P00:DR-01] D-02 |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 進程鎖在逾時時間內未被釋放 | `InterProcessLock.acquire` 返回 `False`，`act_lock` 拋出 `BlockingIOError`，避免無限死鎖 |
| **EC-02** | 檔案變更事件發生在 `.cache` 或 `.git` 目錄下 | `is_path_watched` 立即返回 `False`，不觸發 debounce 與 `.watcher_dirty` 檔案標記 |
| **EC-03** | `manifest.json` 損毀或不存在 | `_is_modules_dirty` helper 補捉 `OSError` 與 `json.JSONDecodeError`，安全視為 dirty 並確保關閉檔案 |
| **EC-04** | VFS 調用跨不同 backend 之 copy/move | 拋出 `NotImplementedError`，避免調用來源 backend 的 copy 導致不可預期損毀 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 記憶體保護 | Worker 進程中僅存在單一 `KnowledgeEngine` 實例，消弭雙重快取記憶體開銷 |
| **NFR-02** | 線程安全 | `_GLOBAL_INDEX_CACHE` 並發讀寫具備 RLock 保護，在高頻 Watcher 熱修補時 0 死鎖 0 崩潰 |
| **NFR-03** | 重構凍結遵循 | 實作全過程絕不執行本地 `@build` 自部署，遵守 `AGENTS.md` 全域管制紀律 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `AtomicEngine` 中的 `act_unlock` 需妥善處理持有鎖進程非同步或跨方法釋放時的字典清理。
- **`[!CAUTION]`** `core.platform.InterProcessLock` 使用平台特定底層原語（POSIX `fcntl.flock`、Windows `msvcrt.locking`），釋放時必須確保留存之 fd 正確關閉。
