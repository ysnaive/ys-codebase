# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_04_knowledge_db_pipeline_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **冷啟動向量載入死鎖解除與多副檔名正規化 (`K-01`, `K-04`, `FR-01`, `FR-04`, `EC-01`, `EC-04`)**：
     - 分離 `pipeline.search()` 載入前需求判定（`want_vectors = enable_vec and not degraded and not lexical_only`）與載入後可用判定（`can_use_vector`），徹底解除冷啟動進程因記憶體狀態未就緒導致跳過磁碟向量載入之死鎖。
     - 於 `pipeline.search()` 呼叫 `_normalize_ftypes()` 拆解 `--ftype=c,cpp,py` 逗號與空格複合字串，並於 `hybrid.py` 補齊多副檔名 BM25 與向量候選集正交過濾。
     - `find_target_symbol()` 改用 `_ensure_jit_index_ready(require_vectors=False)` 記憶體快取重用，大幅消除磁碟反序列化開銷。
     - 登錄 `[DN-07]`。
  2. **調用圖譜熱修補跨檔入度邊雙階保真 (`K-02`, `FR-02`, `EC-02`, `EC-03`)**：
     - 於 `CallGraphIndex` 實作外部入度調用邊提取方法 `get_external_incoming_edges()`，排除目標集合內部自我邊。
     - 於 `hot_patch_unified_index` 實作「第一階同檔案路徑與符號名稱對映 (`Identity Remap`) ＋ 第二階 `TopologyLinker` 跨檔消歧」雙階重連，保證單檔修改後外部未修改檔案之類別方法與無前綴裸函式調用（如 `from a import bar; bar()`）100% 不掉邊，符號徹底刪除時自然斷開不留幽靈邊。
     - 登錄 `[DN-08]`。
  3. **常駐背景服務單一託管、路徑純化與組態優先級 (`K-03`, `K-07`, `K-08`, `FR-03`, `FR-07`, `EC-05`)**：
     - 純化 `scripts/hook.server.py`，拔除私有 `_watcher_instance` 與重複啟動的 `KnowledgeDBServiceWorker`，背景監聽與熱自癒 100% 由 `server.ServiceManager` 透過 `contributes/server.json` 單一託管。
     - 移除 `service.py` 內部 `sys.path.insert` 注入 `source/server` 路徑與 `engine.py` 之無效 events 呼叫，嚴守 `.modules/` 運行時空間隔離。
     - 修正 `KnowledgeDBConfig.load()` 以 `core.config` 為最高優先級；於 `get_engine()` 同步熱刷新組態。
     - 於 `KnowledgeEngine` 補齊 `callers/callees/impact` 公開 SDK 別名並同步 `README.md`。
  4. **核心結構純化、同義詞死代碼移除與 CLI 契約對齊 (`K-05`, `K-06`, `FR-05`, `FR-06`)**：
     - 自 `contributes/`、`schema.py`、`space.py`、`bundler.py`、`retrieval.py`、`linker.py`、`engine.py`、`cli.py` 與 `SKILL.md` 徹底清理 `thesaurus / aliases / related` 欄位與結構。
     - 物理刪除 0 引用之 `knowledge_db/protocol.py` 與 `schema.py:CallGraphNode`。
     - 於 `contributes/core.json` 補齊 `kind`, `lang`, `limit` 等選項；修復 `scripts/cli.py` 使 `-d` 模式必然包含程式碼切片，且 `search -d --json` 輸出補齊 `id`、`matched_terms` 與 `spaces`。
  5. **測試套件純化收斂 14 檔 $\to$ 12 檔與高風險路徑補盲 (`KT-01` ~ `KT-05`, `FR-08`, `FR-09`, `NFR-01`, `NFR-02`)**：
     - 物理刪除 `test_benchmark_perf_and_memory.py` 與 `test_cli_ux.py` 2 個碎片檔並無損整併至子系統測試集。
     - 徹底重寫 `test_cli.py` 中 `if "#01" in out:` 等條件放行之虛假斷言，改為 `setUp()` 預置已知符號進行剛性非空斷言；重寫 `test_space.py` Provider 實質表格斷言。
     - 補齊冷啟動向量載入、熱修補入度保真、多副檔名過濾與單例隔離測試。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 區隔 `want_vectors` 與 `can_use_vector` 解除冷啟動死鎖；實作雙階入度重連；`find_target_symbol` 快取重用；支援多副檔名 |
| `ys_codebase/source/knowledge-db/knowledge_db/graph.py` | Modify | 實作 `get_external_incoming_edges()` 提取外部入度邊 |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | 支援多副檔名過濾（逗號分隔或串列），BM25 與向量候選集正交過濾 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 移除 `sys.path.insert` 注入 `source/server` 路徑，退回乾淨 ABC 抽象基類 |
| `ys_codebase/source/knowledge-db/scripts/hook.server.py` | Modify | 拔除私有 `_watcher_instance` 與第二個 Worker，僅保留 `pre_warm()`，由 `server` 統籌託管 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 移除 `thesaurus` 引用與 `core.events` 呼叫；新增 `callers/callees/impact` SDK 別名；`get_engine()` 熱刷新組態 |
| `ys_codebase/source/knowledge-db/knowledge_db/config.py` | Modify | 修復載入優先順序：`core.config` 為最高優先級 |
| `ys_codebase/source/knowledge-db/knowledge_db/space.py` | Modify | 徹底清除 `thesaurus / aliases / related` 欄位與已廢棄工廠方法 |
| `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` | Modify | 移除 `SemanticBundle` 與打包流程中之 `thesaurus` |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | 移除 `BM25Engine` 之 `thesaurus` 參數與查詢展開分支 |
| `ys_codebase/source/knowledge-db/knowledge_db/linker.py` | Modify | 移除 `TopologyLinker` 之 `thesaurus` 參數 |
| `ys_codebase/source/knowledge-db/knowledge_db/schema.py` | Modify | 刪除 `ThesaurusConfig`, `ThesaurusGroup`, `CallGraphNode` 資料類別 |
| `ys_codebase/source/knowledge-db/knowledge_db/protocol.py` | Delete | 物理刪除 0 引用之歷史代碼檔 |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 移除 `thesaurus_groups` 字串；修復 `-d` 模式必然擷取切片；`search -d --json` 輸出補齊 `id`、`matched_terms`、`spaces` |
| `ys_codebase/source/knowledge-db/contributes/_format.json` | Modify | 移除 `thesaurus` 等過期定義 |
| `ys_codebase/source/knowledge-db/contributes/knowledge-db.json` | Modify | 移除所有同義詞與別名清單，保留純淨語言與 AST 宣告 |
| `ys_codebase/source/knowledge-db/contributes/_manifest.md` | Modify | 同步更新 CLI 指令樹、Hooks 與 Ingress/Egress 宣告 |
| `ys_codebase/config/knowledge-db/contribute.json` | Modify | 移除殘留的專案覆蓋 `thesaurus`，消除 Contributes 驗證警告 |
| `ys_codebase/source/knowledge-db/tests/test_benchmark_perf_and_memory.py` | Delete | 物理刪除歷史碎片測試檔，測試整併至 `test_retrieval.py` 與 `test_bundler.py` |
| `ys_codebase/source/knowledge-db/tests/test_cli_ux.py` | Delete | 物理刪除歷史碎片測試檔，測試整併至 `test_cli.py` |
| `ys_codebase/source/knowledge-db/tests/test_graph.py` | Modify | 移除 dead protocol 測試，補齊外部入度提取與雙階保真測試 |
| `ys_codebase/source/knowledge-db/tests/test_hot_reload.py` | Modify | 補齊冷啟動向量載入解除死鎖之回歸測試 |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 補齊 SDK 公開別名與組態載入優先級測試 |
| `ys_codebase/source/knowledge-db/tests/test_retrieval.py` | Modify | 補齊多副檔名過濾、Posting slots 與頂層 doc_lengths 測試 |
| `ys_codebase/source/knowledge-db/tests/test_bundler.py` | Modify | 補齊工作者解析任務測試 |
| `ys_codebase/source/knowledge-db/tests/test_space.py` | Modify | 移除 thesaurus 斷言，重構 Provider 實質表格斷言 |
| `ys_codebase/source/knowledge-db/tests/test_schema.py` | Modify | 移除已刪除之 ThesaurusConfig 測試 |
| `ys_codebase/source/knowledge-db/tests/test_cli.py` | Modify | `setUp()` 預置已知符號，消滅 `if "#01" in out:` 等虛假條件放行斷言 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 補齊 `hook.server.py` 無私有 watcher 測試 |
| `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 增補 `[DN-07]` (冷啟動向量死鎖解除) 與 `[DN-08]` (雙階調用圖譜入度保留與服務單一託管) |
| `docs/knowledge-db/README.md` | Modify | 同步架構說明、SDK 呼叫範例，移除已廢棄同義詞擴展敘述 |
| `ys_codebase/source/knowledge-db/README.md` | Modify | 同步 SDK 門面介面、CLI 速查表與組態指南 |
| `ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md` | Modify | 修正速查指令中的搜尋關鍵字範例 |
| `.agents/skills/knowledge-db-search/SKILL.md` | Modify | 同步修正速查指令中的搜尋關鍵字範例 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：
  - `python yscb.py dev check knowledge-db`：`PASSED`（0 Fail, 0 Warn）。
  - `python yscb.py dev test knowledge-db --sync`：**150/150 Passed (100% Ready, 6.69s)**（Contract: 3/3, Custom: 147/147, 0 Failed, 0 Skipped），成功熱部署 `knowledge-db@1.1.0.build`。
  - 全量生態系回歸測試 `python yscb.py dev test -q`：**193/193 Passed (100%)**。
- **Pillar 3 獨立代碼審查**：
  - 於進入 UX 測試前派發 `research` 獨立審查子代理執行無偏見代碼與架構審查。
  - 全面檢核 6 大目標（冷啟動載入、雙階入度保真、服務單一託管、死代碼清理、測試純化與回歸覆蓋），取得 **`REVIEW_STATUS: PASSED`** 認證。
- **實機 UX / 人工驗證**：
  - `UX-01`：`python yscb.py knowledge-db search "PIDController" -d` 輸出完整切片與行號，無同義詞提示。
  - `UX-02`：`python yscb.py knowledge-db callers "verify" --ftype=py` 正確識別 `PlanVerifier.verify` 為 Facade 入口無靜態上游調用者（內部實際調用 `verify_plan`），調用圖譜拓撲消歧 100% 精確。
  - `UX-03`：`python yscb.py knowledge-db status` 顯示 3 空間、全域倒排索引、向量特徵索引與向量模型權重均就緒，無同義詞字串殘留。開發者確認通過。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | [CHANGELOG.md](../../../CHANGELOG.md) | 已完成 | 記錄 `sub_04_knowledge_db_pipeline_and_tests` 向量死鎖解除、圖譜雙階保真、服務託管與測試純化結案摘要 |
| **中觀 (Meso)** | [docs/knowledge-db/README.md](../../../docs/knowledge-db/README.md)、[ys_codebase/source/knowledge-db/README.md](../../../ys_codebase/source/knowledge-db/README.md) | 已完成 | 同步更新 SDK 呼叫範例、移除同義詞庫敘述、更新 CLI 選項與雙軌複合檢索機制 |
| **中觀 (Meso)** | [docs/knowledge-db/DESIGN_NOTES.md](../../../docs/knowledge-db/DESIGN_NOTES.md) | 已完成 | 增補 `[DN-07]`（冷啟動向量載入死鎖解除）與 `[DN-08]`（雙階入度保留與服務單一託管）設計決策 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 完整維護 `pipeline.py`、`graph.py`、`hybrid.py`、`engine.py` 之 Docstring 與型別標註 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：全模組 12 個測試檔案 150/150 測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(knowledge-db): fix vector cold-start, incoming callers retention, and purify test suite (sub_04)

- Resolve vector search cold-start loading deadlock by separating want_vectors from can_use_vector (K-01)
- Implement dual-stage incoming edge retention (Identity Remap + TopologyLinker) in CallGraphIndex (K-02)
- Purify hook.server.py and service.py to enforce single ServiceManager hosting and zero source/ injection (K-03)
- Support comma-separated multi-extension filtering and memory cache reuse in find_target_symbol (K-04)
- Eliminate obsolete thesaurus, aliases, related structures and delete dead protocol.py and CallGraphNode (K-05)
- Align CLI contract options in contributes/core.json and fix -d code snippet JSON output (K-06)
- Align KnowledgeDBConfig priority to core.config and add callers/callees/impact SDK aliases (K-07, K-08)
- Consolidate test suite from 14 files into 12 files, eliminate vacuous assertions, and add regression tests (KT-01~KT-05)
- Update three-tier documentation in docs/knowledge-db, README.md, and DESIGN_NOTES.md (DN-07, DN-08)
```
