# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_04_knowledge_db_pipeline_and_tests  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：合併落實 `knowledge_db_retrieval_pipeline_and_purity_roadmap.md`（`K-01` ～ `K-08`）與 `knowledge_db_test_suite_purification_roadmap.md`（`KT-01` ～ `KT-05`），解除冷啟動向量檢索死鎖、修復調用圖譜熱修補掉邊問題，並純化移除同義詞與死代碼遺留。
- **核心目標**：
  1. 解除 `pipeline.search()` 在載入索引前檢查 `is_vector_available` 造成的冷啟動向量死鎖（`K-01`），並修復 `--ftype=c,cpp,py` 逗號拆解、`act_callers/callees/impact` 之 `ftypes` 傳遞與 `find_target_symbol()` 快取重用（`K-04`）。
  2. 於 `CallGraphIndex` 與 `hot_patch_unified_index()` 實作外部入度調用邊提取與「第一階同檔案身分對映 (`Identity Remap`) ＋ 第二階 `TopologyLinker` 消歧」雙階重連，確保熱修補後跨檔 `Callers`（含類別方法與無前綴裸函式調用）100% 不掉邊（`K-02`）。
  3. 純化 `scripts/hook.server.py`（移除私自啟動之 `_watcher_instance`，交由已在 `sub_03` 修復之 `server.ServiceManager` 單一託管），移除 `service.py` 之 `source/server` 路徑注入與 `engine.py` 無效事件呼叫（`K-03`）。
  4. 徹底純化移除已淘汰之 `thesaurus / aliases / related` 結構與死代碼 `knowledge_db/protocol.py`、`schema.py:CallGraphNode`，並對齊 `contributes/core.json`、`scripts/cli.py` `-d` 切片、`KnowledgeDBConfig` 優先級與 SDK 別名（`K-05` ～ `K-08`）。
  5. 裁撤 2 個歷史任務碎片檔（`test_benchmark_perf_and_memory.py`、`test_cli_ux.py`），將 `knowledge-db/tests/` 由 14 檔收斂為 12 檔，消除雙胞胎重複測試、修復 `test_cli.py` 空索引 `if "#01" in out:` 寬容放行與 `test_space.py` 空殼測試，並補齊冷啟動向量與熱修補入度邊回歸測試（`KT-01` ～ `KT-05`）。
- **邊界排除 (Explicitly Excluded)**：不改變現有二進位索引檔案命名與 RRF 融合權重公式。
- **架構影響範圍**：`ys_codebase/source/knowledge-db/knowledge_db/`、`contributes/`、`scripts/{cli.py,hook.server.py}`、`assets/skills/knowledge-db-search/SKILL.md`、`README.md` 與 `tests/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **雙階入度邊重連防裸調用丟邊 (`K-02`, `KT-05`)**：熱修補拔除 `old_doc_ids` 前先快照舊符號 `(norm_file_path, name, lower_fqn, kind)`，優先執行 O(1) 同檔案新符號 `Identity Remap`，保護 `from a import fn; fn()` 無前綴裸調用入度邊不被 `linker.py` L341 攔截。
- **[P00:DR-02]** **依賴 `sub_03` (`server`) 先行落地 (`K-03`)**：本子計畫排於 `sub_03` 之後執行，確保移除 `hook.server.py` 私自啟動邏輯時，`server.ServiceManager` 已能穩定託管 `knowledge-db-watcher`。

---

## 3. 開放議題與確認紀錄

- 規格與防呆邊界已於前置路線圖審查中 100% 確認收斂，狀態標記為 `Confirmed`。

