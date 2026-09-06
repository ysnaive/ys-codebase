# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge_db_service_worker_and_pipeline  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 API 規格書均具備明確簽名與責任類別
- [x] **邊界防護**：EC-01 ~ EC-05 涵蓋原子寫入防損毀、500ms 防抖防風暴與依賴異常降級
- [x] **依賴純淨**：嚴格遵循微內核規範，依賴僅限 `core` 與 `server`，符合 NFR-01~03

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 移除 `knowledge-db daemon` 說明，更新為常駐 Server ServiceWorker 架構 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 DN-05 (移除自製守護進程，全面轉向 Server ServiceWorker 與 mtime 比對熱刷新) |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 sub_04 變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當 Service Worker 在背景進行 500ms 防抖熱修補時，若使用者同時發起 CLI 查詢，是否會讀取到半寫入的二進位損毀快照？  
> 💡 **防護解法**：快照更新調用 `core.vfs.atomic_write`，先寫入同目錄暫存檔、呼叫 `fsync` 後調用 `os.replace` 原子覆蓋，作業系統層級保證讀取端永遠看見完整 snapshot。

> ❓ **尖銳問題 2**：若使用者系統未安裝 FastEmbed 或向量模型損毀，常駐 Worker 是否會崩潰？  
> 💡 **防護解法**：`KnowledgeEngine` 與 `EmbeddingService` 具備安全降級回退機制，拋出警告並透明切換為純文字 Lexical-only (BM25) 檢索，主流程永不崩潰。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：建立 `source/knowledge-db/knowledge_db/service.py`，實作 `KnowledgeDBServiceWorker` (FR-01, FT-01, FT-02)
- [ ] **TASK-02**：改裝 `source/knowledge-db/knowledge_db/engine.py`，實作記憶體單例快取、`pre_warm()` 與 mtime 微秒級熱刷新 (FR-03, FR-04, FT-04, FT-05)
- [ ] **TASK-03**：精簡 `source/knowledge-db/knowledge_db/daemon.py`，廢棄 `HotReloadServer`、PID 鎖檔、Console 視窗與自製進程邏輯 (FR-02)
- [ ] **TASK-04**：改裝 `source/knowledge-db/scripts/cli.py`，拔除 `daemon` 子命令及其分支 (FR-02, FT-03)
- [ ] **TASK-05**：全面對齊 `core.platform.lock.InterProcessLock` 與 `core.vfs` 原子操作 (FR-05, FT-06)
- [ ] **TASK-06**：編寫 `source/knowledge-db/tests/test_service_worker.py` 單元與整合測試套件 (FT-01~06)
- [ ] **TASK-07**：全生態系測試回歸與合規檢核 (FT-07)
- [ ] **TASK-08**：文檔同步交付 (`docs/knowledge-db/`, `DESIGN_NOTES.md`, `CHANGELOG.md`)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 徹底完成微內核統一與常駐架構遷移**：本實作標誌著知識庫系統徹底告別自製常駐進程時代，全面納入 `server` 模組與 `core.platform/vfs` 統一管理。
