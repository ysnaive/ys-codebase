# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_04_knowledge_pipeline  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Unknown  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：執行全倉深度審計分類型主計畫（`2026_11_05_0104_codebase_deep_audit_remediation`）之子計畫 `sub_04_knowledge_pipeline`（三階知識檢索管線 file-space、ast 與 knowledge-db 審計問題修復與平行加速恢復）。
- **核心目標**：依據主計畫 `R01_codebase_deep_audit.md` 經盲眼反向查驗確認之問題清單與防回歸紅線，完成 `ys_codebase/source/file-space/、ys_codebase/source/ast/ 與 ys_codebase/source/knowledge-db/` 範圍內所有確認缺陷之無損修復與單元測試驗證。
- **既有組件復用與查重 (Reuse Discovery)**：復用目標模組既有鎖機制、快取結構與 `YSCBTestCase` 隔離沙盒測試框架。
- **邊界排除 (Explicitly Excluded)**：嚴格限制寫入範圍於 `ys_codebase/source/file-space/、ys_codebase/source/ast/ 與 ys_codebase/source/knowledge-db/`，不觸碰其他子計畫負責之模組目錄，且不修改 `R01_codebase_deep_audit.md` 已駁回之偽陽性項目。
- **架構影響範圍**：`ys_codebase/source/file-space/、ys_codebase/source/ast/ 與 ys_codebase/source/knowledge-db/` 及對應 `tests/` 測試案例。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `module:file-space` Watcher 髒信標、Symlink 邏輯路徑與沙盒安全空間覆寫（`FS-01`~`06`）**：於 `file_space/scanner.py` 與 `service.py` 補齊 `is_watcher_dirty` 判斷與 `_diff_all_spaces` 世代聚合；於 `manager.py:_walk_root` 使用走訪樹之 `entry_path` 計算相對路徑且僅在 `st_ino != 0` 時記錄 `visited_dirs`；遵守紅線 7，於 `_apply_project_space_overrides` 加上 `self._explicit_project_root is None` 守衛防止宿主配置污染沙盒測試；為 `_atomic_write_bytes` 補齊 Windows `PermissionError` 退避重試，並補齊 `cli.py:diff --ack` 之 `space_generations` 傳遞與單檔 `include` 支援。
- **[P00:DR-02] `module:ast` 髒檔匹配精確化、恢復多進程平行解析與單空間冷啟動防護（`AST-01`~`06`）**：遵守紅線 7 與 `[DN-06]`，於 `ast_engine/io_utils.py:is_dirty_file_match` 保留帶 `/` 相對路徑之雙向後綴匹配，針對根目錄單檔（`'/' not in sym_path_norm`）開放匹配絕對髒路徑，並於 `_resolve_dirty_files_only` 套用 `best_mtime_ns` 快照消歧；於 `bundler.py:L886` 修正 `has_custom_configs` 判定（僅排除非內建之自訂解析器），恢復 `ProcessPoolExecutor` 多進程平行 AST 解析；於 `ast/scripts/hook.file-space.py` 冷啟動無快照時強制以 `spaces=None` 建立全空間快照並補傳 `_cursor_already_consumed=True`；延伸 C# `file_scoped_namespace_declaration` 之 `end_byte` 至檔案末尾，並將 `ast_generation` 納入 `_LAST_LINKER_CACHE` 快取鍵。
- **[P00:DR-03] `module:knowledge-db` 冷啟動雙水位線自癒、跨進程向量鎖與檢索細節收斂（`KDB-01`~`06`）**：於 `knowledge_db/service.py` 之 `_has_pending_space_work` 與 `_sync_stage1_lexical_and_graph` 檢查 `acked_ast_generation` 前先呼叫 `engine.pipeline._ensure_indices_loaded(load_vectors=False)`，恢復 `[DN-30]` 冷啟動雙水位線自癒；於 `pipeline.py:L715, L989` 補齊 `_kdb_index_file_lock`；遵守紅線 8，於 `hybrid.py` 統一使用 `Path(sym.file_path).suffix` 提取副檔名且不將 BM25 尺度之 `min_score` 套用於 RRF 分數；修正 `engine.py:bundle` 多空間匯出檔名碰撞、移除 `_ensure_jit_index_ready_locked` 重複消費游標並為 `InvertedIndex.build` 增設 `pre_aggregated=True`。

---

## 3. 開放議題與確認紀錄

- **已確認事項**：子計畫範疇、防回歸紅線與修復方案已由主計畫 `R01_codebase_deep_audit.md` 定錨確認，可隨時啟動 Phase 01～07（或 `/auto`）推進實作。
