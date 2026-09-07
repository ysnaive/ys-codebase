# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_09_architecture_debt_remediation  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-14 在 P03 API 規格書與受影響檔案中均有 1:1 對應介面與簽名。
- [x] **邊界防護**：EC-01 (鎖逾時拋 BlockingIOError)、EC-02 (非空間目錄過濾)、EC-03 (manifest FD 安全釋放)、EC-04 (跨 backend 拋 NotImplementedError) 均已定義具體防護。
- [x] **依賴純淨**：嚴守重構凍結條款，零本地 `@build` 自部署，全數依賴標準 Python 與專案既有 Core/VFS/Platform 模組。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **內核手冊** | `source/core/core/guard.py` | Modify | 補齊 Guard Token 安全邊界 Docstring |
| **守護手冊** | `source/server/server/service.py` | Modify | 補齊 BaseServiceWorker context 契約 Docstring |
| **微觀日誌** | `plans/.../sub_09.../changelog.md` | Modify | 微觀紀錄各 Phase 轉換與實作修復進展 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當多個 CLI 進程同時觸發 `AtomicEngine.act_lock` 時，`InterProcessLock` 是否會殘留殭屍鎖導致永久阻塞？  
> 💡 **防護解法**：`InterProcessLock` 基於作業系統檔案描述符（POSIX `flock` / Windows `msvcrt.locking`）。當持有鎖的進程意外崩潰或退出時，作業系統核心會強制自動關閉 fd 並釋放檔案鎖，絕不殘留殭屍鎖；同時 `act_lock` 設置了 `timeout_sec` 超時參數，保證在有限時間內失敗返回 `BlockingIOError`。

> ❓ **尖銳問題 2**：`KnowledgeEngine` 單例化後，多個模組調用 `get_engine()` 是否會因線程並發導致快取損毀？  
> 💡 **防護解法**：單例實例內部之 `_GLOBAL_INDEX_CACHE` 已引入 `threading.RLock()` 進行保護，讀取與熱修補均在鎖保護下執行。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (Tier 1 關鍵穩定性修復)**：
  - 修復 `core.engine.AtomicEngine.act_lock/act_unlock` 改用 `InterProcessLock` (H-01)。
  - 修復 `knowledge_db.service.KnowledgeDBServiceWorker.is_path_watched` 移除 L159~163 兜底 (H-02)。
- [ ] **TASK-02 (Tier 2 下沉統一與狀態原子化)**：
  - 新增 `core.platform.venv.ensure_private_venv` 並由 `core.platform` 導出 (M-01)。
  - 重構 `server.master` 與 `server.worker` 複用 `ensure_private_venv` (M-01)。
  - 重構 `server.master._write_state` 改採 `vfs.write_json(..., atomic=True)` (M-02)。
- [ ] **TASK-03 (Tier 2 宿主入口快取與安全修復)**：
  - `yscb.py` 加入 `_MODULE_CACHE` (M-03)。
  - `yscb.py` 重構 `_is_modules_dirty` helper 解決裸 open FD 洩漏 (M-04)。
- [ ] **TASK-04 (Tier 2 Engine 單例全域共享)**：
  - `knowledge_db.engine` 提供並導出 `get_engine()` 單例工廠 (M-05)。
  - `knowledge_db.service` 改為透過 `get_engine().pipeline` 共享 (M-05)。
  - `scripts/cli.py` 轉接引用 `knowledge_db.engine.get_engine` (M-05)。
- [ ] **TASK-05 (Tier 3 低風險代碼清理、並發保護與契約完善)**：
  - `core.guard` 補齊 Token 安全邊界 Docstring (L-01)。
  - `knowledge_db.pipeline` 為 `_GLOBAL_INDEX_CACHE` 增加 `_CACHE_LOCK = threading.RLock()` (L-02)。
  - `yscb.py` 支援 `YSCB_DISPATCH_TIMEOUT` 動態逾時 (L-03)。
  - `knowledge_db.engine` 移除未用 7 個 Formatter 內部常數 (L-04)。
  - `yscb.py.main()` 拆解四層三元運算符嵌套 (L-05)。
  - `server.service.BaseServiceWorker.start` 補齊 context 契約 Docstring (D-01)。
  - `core.vfs.VFS.copy/move` 補齊跨 Backend 檢查拋出 NotImplementedError (D-02)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 確立 5 階段拓撲實作計畫**：TASK-01 ~ TASK-05 依據風險等級與依賴拓撲依序實作，每組任務完成後即刻執行單元跑測驗證。
