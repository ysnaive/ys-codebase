# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：CLI 觸發鍊、Server/Worker 防卡死韌性加固與 AST/KDB 增量一致性修復  
> 建立日期：2026-11-10  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：以當前現況深度調研各指令觸發鍊和 worker 協作邏輯，感覺很容易卡住，還有評估 ast / kdb 的增量更新等邏輯；立項固化報告並進入實作規劃，確認皆為確定性問題修復後立即進入實作。
- **核心目標**：消除 CLI 與常駐 `server` / `WarmWorker` 的所有確定性死鎖、管道阻塞、停機競態與外部無逾時掛起，並根治 `core.space`、`ast`、`knowledge-db` 增量同步中的靜默資料失步與鎖內慢速推論阻塞。
- **既有組件復用與查重 (Reuse Discovery)**：全面復用 `core.context` (`get_env` / `RuntimeContext`)、`core.platform.lock.InterProcessLock`、`core.vfs.write_bytes(atomic=True)`、`core.service_contract` 與 `ast_engine.io_utils.compute_project_relpath`，零新增第三方依賴。
- **邊界排除 (Explicitly Excluded)**：
  1. 不於本計畫物理移除 `ast` 舊軌 `TopologyLinker` 或將 `Pickle+Gzip` 改為 SQLite/分片引擎（屬既有路線圖 `ast_compile_pipeline_and_kdb_doc_governance.md` 範疇）。
  2. 不改變 `UnifiedSymbol.compute_id` 公開 ID 雜湊公式（維持對外相容，改於 `VectorIndex` 內部以內容雜湊追蹤與跨行號重用向量）。
  3. 不開啟背景無授權自動連網下載數百 MB HuggingFace 模型（維持 `STATE_DEGRADED_OFFLINE` 離線安全降級與顯式 `kdb model download`）。
- **架構影響範圍**：`core`、`server`、`ast`、`knowledge-db`、`gdrive-support` 五大模組及對應 `docs/` 與 `CHANGELOG.md`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 100% 確定性工程修復邊界核定**：經逐項審查，納入 `sub_01` 與 `sub_02` 的全部項目皆屬具備唯一標準工程解法的確定性缺陷（重入自死鎖、IPC fd 繼承洩漏、`Ctrl+C` 孤兒佔鎖、參數名 `timeout` vs `timeout_sec` 錯配、`from_gen=0` 吞沒刪除清單、同行號舊向量殘留、倒排新舊符號混用、禮讓假空閒 RRF 污染、無逾時網路/子進程呼叫），零破壞性公開契約變更。
- **[P00:DR-02] 正交雙子計畫切分**：按「執行與通訊控制面 (`sub_01`)」與「空間指紋、語法樹及知識索引資料面 (`sub_02`)」拆分為兩個檔案集合低耦合的子計畫，獨立維護完整追溯鏈與測試矩陣。

---

## 3. 開放議題與確認紀錄

- 已與開發者確認：全部納入實作項目均為確定性問題修復，直接啟動階段 B 自動化實作、測試、雙盲審查與雲端同步閉環。
