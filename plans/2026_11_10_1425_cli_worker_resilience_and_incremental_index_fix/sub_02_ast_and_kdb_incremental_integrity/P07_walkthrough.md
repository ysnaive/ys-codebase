# 成果展示與結案報告 (Walkthrough)

> 功能名稱：AST 與 Knowledge-DB 增量更新一致性與鎖競爭修復  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **空間掃描刪檔保全與語法供應器跨進程互斥**：修復 `SpaceScanner.diff()` 於 `config_hash` 變更重置 `from_gen` 時保留 `orig_from_gen` 刪除墓碑清單；修復 `GrammarProvisioner._provision_lock()` 之 `InterProcessLock.acquire(timeout_sec=...)` 呼叫並在鎖內二次重檢磁碟負快取 `provision_failed.json`。
  2. **AST CoW 快照隔離、水合圖譜防撕裂落盤與多空間保護**：`CallGraphIndex.clone_shallow()` 深拷貝邊屬性 `call_sites` 串列並持久化 `ast_generation` 雙檔世代校驗；`get_workspace_graph()` 於跨進程鎖下核驗雙檔 `st_mtime` 未變後原子持久化水合圖譜與 `unified.meta.json`；`ensure_jit_synced(spaces=...)` 以全量配置空間判定過期鍵，防止單一 `--space` 查詢覆寫破壞全域統一索引；`_resolve_entry_dirty_candidate` 消除雙前綴並防跨空間後綴誤殺。
  3. **Knowledge-DB 向量內容雜湊、`_InternTables` 零洩漏 CoW 與鎖外推論原子發佈**：`VectorIndex` 導入 `doc_text_hashes` 支援行號平移零推論重用舊向量與同行號改內文淘汰重算（含探針逾時熔斷與異常路徑強制淘汰舊向量，且舊快取雜湊回填不污染 `_vector_index_dirty`）；`Posting` 改持輕量 `_InternTables` 解除對歷史 `InvertedIndex` 的強引用；`_hot_patch_unified_index_locked` 於 `_index_lock` 外執行 ONNX 推論並於完成後將 `working_idx` 與新向量原子發佈落盤。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | `diff()` 於 `config_hash` 變更時以 `orig_from_gen` 精確保留新排除之刪除檔案 |
| `ys_codebase/source/ast/ast_engine/provisioner.py` | Modify | 修正 `InterProcessLock` `timeout_sec` 取鎖、鎖內重檢磁碟負快取並縮短離線 `pip` 逾時 |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | `ASTSnapshot` 新增 `schema_version` 與 `config_hash` 欄位 |
| `ys_codebase/source/ast/ast_engine/graph.py` | Modify | `CallGraphIndex.clone_shallow()` 深拷貝邊 `call_sites` 串列並序列化 `ast_generation` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | `_resolve_entry_dirty_candidate` 防重複前綴並將專案內髒路徑收斂為專案相對路徑 |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 水合圖譜 `st_mtime` 守衛落盤與更新 `meta`、雙檔世代校驗、多空間 `--space` 查詢保護、CoW 快照與刪檔防誤連 |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | `VectorIndex` 新增 `doc_text_hashes` 與 `cloned_with_patch`、`reconfigure_model` 免鎖短路與離線守門 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `Posting` 解耦 `_tables_ref` 根除歷史 `InvertedIndex` 駐留、`clone_shallow()` 與歷史欄位長度精確扣減 |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | `HybridSearchEngine.search()` 改採顯式區域索引與權重參數，消除跨執行緒共享欄位突變 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 向量雜湊差集與行號平移重用、熔斷/異常舊向量淘汰、鎖外推論與 `working_idx` 原子發佈、`yielded_to_foreground` 降級 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `get_engine()` 依 `mtime_ns` 動態刷新 `contribute.json` 空間與權重 |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 新增空間組態變更保留刪除清單單元測試 |
| `ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 新增跨進程鎖與隔離負快取、水合圖譜落盤、`--space` 多空間保全、CoW 併發與刪檔防誤連測試 |
| `ys_codebase/source/knowledge-db/tests/test_self_healing.py` | Modify | 新增鎖外推論並發檢索落盤驗證、`weakref` 零殘留回收、熔斷淘汰舊向量、行號平移重用與跨空間隔離測試 |
| `ys_codebase/source/ast/README.md` | Modify | 補充增量熱修補 `.ast_index.lock`、`ast_config_hash` 與 CoW 快照說明 |
| `ys_codebase/source/knowledge-db/README.md` | Modify | 補充 `doc_text_hashes` 行號平移重用與鎖外推論說明 |
| `docs/ast/README.md` | Modify | 新增增量索引一致性、CoW 快照與水合圖譜落盤小節 |
| `docs/ast/DESIGN_NOTES.md` | Modify | 新增 `[DN-AST-07]` 水合圖譜落盤、CoW 快照與組態指紋設計筆記 |
| `docs/knowledge-db/incremental_hot_reload.md` | Modify | 修正歷史漂移路徑與常數，更新向量內容雜湊、鎖外推論與前景禮讓降級架構 |
| `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 新增 `[DN-32]` `doc_text_hashes` 行號位移零推論遷移與鎖外推論設計筆記 |
| `CHANGELOG.md` | Modify | 登記 `core.space`、`ast` 與 `knowledge-db` 增量一致性修復紀錄 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：全倉 9 大模組共 `896/896` 測試案例 `100.0% PASSED`（`core` 303/303、`ast` 57/57、`knowledge-db` 124/124，全程 `-W error::ResourceWarning` 達成 `0 ResourceWarning`）；`dev check --all` `9/9 PASS`（`0 Warnings, 0 Failed`）；`contributes check` `28/28 PASS`；完成三輪 Pre-UX 雙盲冷眼審查並將檢出之確定性項目 100% 根治驗證閉環。
- **實機 UX / 人工驗證**：於 VM 完成全新空白部署環境冷熱派發與外部檔案 `ast outline` / `knowledge-db status` 煙霧實測通過；`UX-01` 標記為 `[跳過/免測]` 交由本地端 `gdrive pull` 發布前驗收。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已完成 | 同步記錄 `core.space`、`ast` 與 `knowledge-db` 增量一致性修復摘要 |
| **中觀 (Meso)** | `docs/ast/README.md` | 已完成 | 補充 `ast_config_hash`、CoW 快照與水合圖譜落盤說明 |
| **中觀 (Meso)** | `docs/knowledge-db/incremental_hot_reload.md` | 已完成 | 修正 `scripts/hook.core.py` 與 `400` 截斷常數，對齊向量雜湊與鎖外推論流程 |
| **中觀 (Meso)** | `docs/ast/DESIGN_NOTES.md`、`docs/knowledge-db/DESIGN_NOTES.md` | 已完成 | 登記 `[DN-AST-07]` 與 `[DN-32]` 核心架構決策與並發設計妥協 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 維護關鍵類別與方法 Docstring 且零工單標籤殘留 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(space,ast,kdb): enforce cow index snapshots, content-hashed vector reuse, unlocked inference, and multi-space jit integrity
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix/sub_02_ast_and_kdb_incremental_integrity` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
