# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：`module:knowledge-db` 轉型為 Layer 3 純混合檢索消費者與三階單向 DAG 快照對接  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_1009_ast_topology_engine_modularization](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據規格：[P01-05_auto.md](./P01-05_auto.md)  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 合規與契約測試 | 驗證 `manifest.json`（依賴 `ast>=1.0.0`、移除 `tree-sitter*`/`networkx`）、`contributes/_format.json`（僅保留 `space_weights`）及 `contributes/core.json`（移除 `callers/callees/impact`）符合模組契約 | FR-01, FR-04, NFR-01 | `python yscb.py dev check knowledge-db` & `TestSpaceIntegrationAndWeights.test_sub_06_empty_configurable_contribute_defaults` |
| **FT-02** | 單元測試 | 驗證 `knowledge_db.schema` 重匯出 `ast_engine` 之 `UnifiedSymbol`、`MemberInfo`、`SymbolKind`、`LanguageType`、`SemanticBundle`，且 `KnowledgeDBContributes` 僅管理 `space_weights` | FR-02, FR-04 | `python yscb.py dev test --target=knowledge-db:TestSchema` |
| **FT-03** | 整合測試 | 驗證 Single-Parse Symbol Sharing：當 `ASTEngine` 已同步最新快照時，`KnowledgeEngine.build_unified_index()` 與增量熱修補直接消費 `ASTSnapshot.symbols` 建立/修補 BM25 與向量索引，`parser_registry.parse_file` 重複呼叫次數為 `0`，且 `acked_ast_generation` 對齊 `ast_generation` | FR-02, FR-03, NFR-02 | `python yscb.py dev test --target=knowledge-db:TestJITHotHealing.test_single_parse_symbol_sharing_zero_reparse` |
| **FT-04** | 整合與邊界測試 | 驗證三階 Pull-Based JIT 游標自癒、跨空間同名檔案隔離（`__init__.py`）、Stage 1 向量淘汰與刪除/清空檔案防禦 | FR-03, EC-01, EC-02 | `python yscb.py dev test --target=knowledge-db:TestKnowledgeDBSelfHealing` & `TestIncrementalHotReload` |
| **FT-05** | CLI 與服務測試 | 驗證 `knowledge-db` CLI 5 大子命令（`status`, `index`, `search`, `clean`, `model`）正常運作，已移交之 `callers/callees/impact` 返回非 0 退出碼，且 `KnowledgeDBServiceWorker` 與 `hook.file-space.py` 熱修補正常 | FR-04, EC-03, EC-04 | `python yscb.py dev test --target=knowledge-db:TestCLI` & `TestSpaceEventHookAndCacheSync` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `dev check knowledge-db` `[PASS]`；`Auto-Contract Suite (3/3)` 與 `test_file_space` 全部通過 | 2026-11-02 12:04 |
| **FT-02** | `Passed` | `TestSchema` 4/4 通過，確認與 `ast_engine.schema` 100% 共享型別定義 | 2026-11-02 12:04 |
| **FT-03** | `Passed` | `test_single_parse_symbol_sharing_zero_reparse` 通過：`spy_parse.call_count == 0` 且 `idx.acked_ast_generation == gen1` | 2026-11-02 12:04 |
| **FT-04** | `Passed` | `TestJITHotHealing`、`TestIncrementalHotReload`、`TestKnowledgeDBSelfHealing` 全數通過（含跨空間 `__init__.py` 隔離與單檔增量耗時 < 20ms） | 2026-11-02 12:04 |
| **FT-05** | `Passed` | 全套件 `103 Total, 103 Passed, 0 Failed (11.246s)`；`knowledge-db@1.3.0.build` 打包與安裝成功 | 2026-11-02 12:05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db status` 與跨空間搜尋（`source`、`plans`、`docs`），確認 `knowledge-db` 直接消費 `module:ast` 產出之符號快照並正常顯示檢索結果與 `ast_generation` 同步狀態 | `[測試通過]` | 開發者實機驗收 `status` 與 `source`/`plans`/`docs` 跨空間搜尋通過 |

