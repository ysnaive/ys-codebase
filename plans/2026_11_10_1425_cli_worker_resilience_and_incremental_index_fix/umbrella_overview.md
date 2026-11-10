# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：CLI 觸發鍊、Server/Worker 防卡死韌性加固與 AST/KDB 增量一致性修復 (`2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix`)  
> 建立日期：2026-11-10  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：根治 CLI 冷熱雙管道派發、`MasterSupervisor` 單例 `WarmWorker` 與同進程寄生背景服務（`CoreSpaceWatcher`、`KnowledgeDBServiceWorker`、`GDriveSyncServiceWorker`）在重入呼叫、子進程句柄繼承、`Ctrl+C` 中斷、停機/重載與離線環境下的確定性卡死與阻塞問題；同時修復 `core.space`、`ast` 與 `knowledge-db` 增量索引管線中的刪除清單吞沒、跨進程鎖失效、舊向量殘留、倒排幽靈詞與無鎖狀態競態。
- **架構邊界**：嚴守 100% 對外 CLI / SDK / `contributes` 向下相容（Mode B），所有納入範疇項目皆為 100% 確定性工程缺陷修復；中長期結構演進（如物理拔除啟發式 `TopologyLinker` 並改寫分片索引儲存、背景自動靜默連網下載數百 MB 向量模型）明確列為邊界排除，歸入既有路線圖 `ast_compile_pipeline_and_kdb_doc_governance.md` 演進。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_cli_and_server_worker_resilience` | Full Track | `Completed` | `core`、`server`、`gdrive-support` 與 `knowledge-db` 服務層之重入阻斷、專用 IPC 句柄隔離、兩段式取消強殺、心跳保活、停機閉鎖、背景禮讓與外部 I/O 逾時加固 |
| **sub_02** | `sub_02_ast_and_kdb_incremental_integrity` | Full Track | `Completed` | `core.space`、`ast` 與 `knowledge-db` 之組態變更刪檔修復、`GrammarProvisioner` 鎖修復、CoW 快照與圖譜落盤、向量雜湊追蹤、倒排世代對齊、鎖外推論與規範路徑隔離 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成全倉四軌唯讀源碼審計，固化 `R01_cli_worker_and_incremental_index_audit.md` 調研報告與兩大子計畫規格定案
- [x] **里程碑 2**：完成 `sub_01` CLI 觸發鍊與 `server` / Worker 防卡死韌性加固實作與單元測試驗證
- [x] **里程碑 3**：完成 `sub_02` `core.space` / `ast` / `knowledge-db` 增量更新一致性與鎖競爭修復實作與單元測試驗證
- [x] **里程碑 4**：通過全模組實機跑測（`0 ResourceWarning`）、`dev check --all`、雙盲冷眼審查、模擬新環境全 CLI 驗證、三層文檔對齊與雲端受控 CoW 同步
