# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_03_knowledge_db_and_workflow_engine_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-09 在 API 規格書與架構設計書中均有具體實作路徑
- [x] **邊界防護**：EC-01 ~ EC-04 涵蓋純檔名相容退化、向量不可用平滑降級、空目錄雜湊容錯與 2 層計畫層級限制
- [x] **依賴純淨**：圖譜與向量徹底正交解耦，滿足 NFR-01 毫秒級查詢延遲要求

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `[DN-KDB-08]` 增量同名檔防護、複合檢索前置過濾與 JIT 解耦 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 登記 `[DN-AWF-07]` 目錄遞迴指紋、Stage 2 尾斜線與計畫狀態對齊 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當修補同名檔案（如 `source/core/tests/test_cli.py`）時，若專案中另有 `source/dev/tests/test_cli.py`，如何保證只清除與重建目標檔案之符號？  
> [*] **防護解法**：在 `retrieval.py` 與 `pipeline.py` 中，只有當 dirty path 不含路徑分隔符時才允許以 basename 退化比對；若含有路徑分隔符，必須要求 `sym_path_norm == p` 或具備標準目錄前綴之完整後綴匹配，徹底隔離不同目錄下的同名檔案。

> [?] **尖銳問題 2**：在進行 `knowledge-db callers/callees/impact` 圖譜查詢時，過去為何會產生數百毫秒的延遲甚至拋出向量加載警告？  
> [*] **防護解法**：過去實作借道調用 `self.search()` 確保 JIT 索引就緒，進而引發了昂貴的 `embed_query()` 向量推論。本次抽出純淨之 `_ensure_jit_index_ready(require_vectors=False)`，在圖譜查詢時直接略過向量推論，將回應時間縮減至純圖譜檢索等級（$< 50\text{ms}$）。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01 (Knowledge-DB 增量修補同名檔防護與 JIT 解耦)**：修改 `retrieval.py` 與 `pipeline.py`，修復路徑比對消除同名檔連坐誤刪；提取 `_ensure_jit_index_ready` 移除圖譜操作中之向量調用。
- [x] **TASK-02 (Knowledge-DB 複合檢索多維前置過濾與向量推論守門)**：修改 `hybrid.py` 支援 `spaces`/`kinds`/`languages` 前置過濾；修改 `embedding.py` 非 mock 模式失敗回傳空陣列；修改 `pipeline.clean` 補齊向量清理。
- [x] **TASK-03 (Knowledge-DB 切片重複輸出與 Watcher 競爭修復)**：修改 `formatter.py` 移除 `callees -d` 重複切片代碼；修改 `service.py` 調整 `.watcher_dirty` 清理時機。
- [x] **TASK-04 (Agents-Workflow Stage 0 遞迴雜湊與 Stage 2 連結修復)**：修改 `publisher.py` 支援目錄遞迴 SHA-1；修改 `compiler.py` 支援 Markdown 括號內反引號剝除與保留尾斜線；修改 `cli.py` 解開 `list` 描述標籤。
- [x] **TASK-05 (Agents-Workflow Plan 稽核枚舉與 Session-Analysis 路徑)**：修改 `verifier.py` 擴充 `VALID_STATUSES` 並對齊 2 層限制；修改 `analyzer.py` 支援 Antigravity transcript 路徑。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零回歸驗收承諾**：
  修復完成後必須保持 `knowledge-db` (134 tests) 與 `agents-workflow` (137 tests) 全量單元測試 100% 通過，全生態系 550 測試 100% 通過。

