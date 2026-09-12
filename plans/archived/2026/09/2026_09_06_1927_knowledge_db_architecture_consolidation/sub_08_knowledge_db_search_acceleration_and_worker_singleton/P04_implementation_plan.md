# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_08_knowledge_db_search_acceleration_and_worker_singleton  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P03 API 規格書中 100% 具有對應之介面與類別簽名
- [x] **邊界防護**：EC-01 ~ EC-04 具備獨立 fallback、異常日誌告警與並行排他鎖保護
- [x] **依賴純淨**：符合 NFR-01~03 約束，Server 模組對領域模組達成 0 硬編碼相依，全量經由 `core.contributes` 與 `core.events` 調度

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/server/README.md` | Modify | 補充 `contributes/server.json` 擴充規範與 Background Services 監控指令 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登記 DN-22: Server 擴充外掛發現架構、Worker 模組快取與事件預熱 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 DN-23: KnowledgeEngine 單例化與 Watcher 事件驅動快取有效性 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 sub_08 高階變更條目 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若 Worker 長時間常駐且加載多個模組，`_module_cache` 是否會造成模組間依賴衝突或記憶體洩漏？  
> 💡 **防護解法**：按需加載（Lazy Load on Demand）；且 Master 具備 15 分鐘空閒自動自毀（Idle TTL）與 `ModulesWatcher` 重啟式熱重載，重啟時整棵進程樹銷毀重建，杜絕長期殘留。

> ❓ **尖銳問題 2**：若某模組在 `contributes/server.json` 聲明了損毀的 ServiceWorker 類別，是否會導致 Server 開機失敗？  
> 💡 **防護解法**：`_discover_service_workers` 採沙盒防禦加載，捕捉個別錯誤並打印清晰的結構化警告日誌，標記該服務為 `FAILED`，保證 Server 主體與其他正常服務順利啟動。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (Server 模組快取與預熱廣播)**：在 `server/worker.py` 實作 `_module_cache` 模組快取，並在 Worker 就緒後非同步調用 `core.events.broadcast("worker_warming", emit_module="server")`。
- [ ] **TASK-02 (Server 動態發現與狀態擴充)**：在 `server/master.py` 透過 `core.contributes.get("server")` 動態載入 services；在 `server/service.py` 擴充元數據並在 `status` 呈現儀表板。
- [ ] **TASK-03 (Knowledge-DB 服務宣告與預熱勾點)**：建立 `source/knowledge-db/contributes/server.json` 與 `source/knowledge-db/scripts/hook.server.py`，串接 `KnowledgeEngine.pre_warm()`。
- [ ] **TASK-04 (Knowledge-DB 單例化與 Dirty Flag 整合)**：在 `scripts/cli.py` 實作 `get_engine()` 單例；在 `pipeline.py` 整合 Watcher 事件驅動變更狀態，未變更 0ms 跳過 stat。
- [ ] **TASK-05 (自動化與回歸測試驗證)**：執行 FT-01 ~ FT-06 單元測試與回歸測試，驗證檢索時間穩定壓在 sub-50ms。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 模組快取與外掛發現全面落地**：確認 TASK-01 ~ TASK-05 拓撲依序實作，滿足所有功能需求與非功能約束。
