# 成果展示與結案報告 (Walkthrough)

> 功能名稱：全生態系指紋快取與熱自癒機制完善度審視與修復  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **雙階段盲眼審計 (`R01`) 與 Devil's Advocate 反向事實查驗**：先以原型 ① 盲眼探索盤點五大模組指紋與自癒閉環，再以原型 ③ Devil's Advocate 反向查驗 `[F-01]` ~ `[F-07]` 真實性與修復副作用，排除 `core.locale._MODULE_BASE_DIR_CACHE` 假陽性，並成功攔截修改 `UnifiedSymbol.compute_id` 破壞呼叫圖譜追蹤及 `core/uri.py` 無防護呼叫 `_is_contributes_dirty()` 引發無窮遞迴兩大副作用。
  2. **`knowledge-db` Stage 1 舊向量剔除與跨空間精確路徑正規化 (`FR-01`, `FR-02`)**：於 `hot_patch_unified_index(skip_vectors=True)` 在 `old_doc_ids` 非空時主動從 `VectorIndex` 剔除舊符號 ID 並持久化，使起始行號未變但內容已修改之符號在 Stage 2 能被 `sym_ids - vec_ids` 差集自動重算向量；於 `SemanticBundler._normalize_space_dirty_paths` 結合空間快照 `source_root` 與 `include` 根目錄將髒檔案路徑正規化為 `project://` 相對路徑，並於 `io_utils.is_dirty_file_match` 移除無 `/` 單純比對檔名之寬鬆條件。
  3. **`file-space` 全空間 `space_generations` 精確 Ack、`watch=False` 自動刷新與 `CursorStore` 執行緒鎖 (`FR-03`, `FR-04`)**：於 `ScanDiffResult` 新增 `space_generations: Dict[str, int]`，由 `consume_diff(None)` / `ack(None)` 按當次實際讀取之子空間世代精確推進游標（消除跨執行緒/進程 Lost Update）；針對 `watch=False` 空間在 Watcher 運行時維持 `auto_refresh=True`；於 `CursorStore` 引入 `threading.RLock()` 保護 RMW 區段。
  4. **`core.uri` 重入安全 JIT 髒檢查、Contributes 追蹤補齊與 `agents-workflow` 目錄 SHA-1 快取複用及 Stage 0 校驗 (`FR-05`, `FR-06`)**：於 `core/uri.py` 與 `core/contributes.py` 建立 `_URI_REENTRANCY` (`threading.local()`) 重入保護與 `(merged_mtime, cfg_mtime)` 快取短路，並補齊 `module.source://` `_format.json`（強制 `interactive=False`）與專案級語系實體檔追蹤；於 `agents_workflow/publisher.py` 實作目錄走訪逐檔複用 `_sha1_cache`、`compute_source_fingerprint` 納入語系鏈與 `config://core`、以及 `_check_short_circuit` 校驗 `AGENTS.md` 託管區塊標記。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/uri.py` | Modify | 新增 `_URI_REENTRANCY` 重入守衛與 `(merged_mtime, cfg_mtime)` 快取短路，安全觸發 Contributes JIT 自癒 |
| `ys_codebase/source/core/core/contributes.py` | Modify | `_is_contributes_dirty` 加入重入守衛；`_scan_contributes_inputs` 補齊 `module.source://` `_format.json` 與專案級語系實體檔追蹤 |
| `ys_codebase/source/core/tests/test_contributes.py` | Modify | 新增 `test_uri_schemes_reentrancy_and_jit_self_healing` 與 `test_project_locale_and_source_format_tracked_in_inputs` 測試 |
| `ys_codebase/source/file-space/file_space/schema.py` | Modify | 於 `ScanDiffResult` 正式定義 `space_generations: Dict[str, int]` 欄位、建構子參數與 `to_dict()` 序列化 |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | `_diff_all_spaces` 填充 `space_generations`、`ack(None)` 支援精確世代映射、`watch=False` 空間允許 `auto_refresh`、`CursorStore` 加入 `threading.RLock()` |
| `ys_codebase/source/file-space/tests/test_fingerprint_scanner.py` | Modify | 新增 `space_generations` 防 Lost Update、`watch=False` 自動刷新與 `CursorStore` 併發 RMW 單元測試 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | `hot_patch_unified_index(skip_vectors=True)` 主動從 `VectorIndex` 剔除 `old_doc_ids` 並儲存 |
| `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` | Modify | 新增 `_normalize_space_dirty_paths` 將空間相對路徑正規化為 `project://` 相對路徑與絕對路徑 |
| `ys_codebase/source/knowledge-db/knowledge_db/io_utils.py` | Modify | 收斂 `is_dirty_file_match`，限制無 `/` 時僅精確匹配 `sym_path_norm == p` |
| `ys_codebase/source/knowledge-db/tests/test_self_healing.py` | Modify | 新增 `TestKnowledgeDBSelfHealing` 驗證同名行號修改之向量剔除自癒與跨空間同名頂層檔隔離 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 目錄 SHA-1 逐檔複用 `_sha1_cache`、`compute_source_fingerprint` 納入語系鏈與 `config://core`、`_check_short_circuit` 校驗 `AGENTS.md` 託管標記 |
| `ys_codebase/source/agents-workflow/tests/test_publisher_self_healing.py` | New | 新增 `TestPublisherSelfHealing` 驗證目錄 SHA-1 快取命中、語系變更指紋失效與託管區塊損壞自癒 |
| `docs/file-space/README.md` | Modify | 補充 `ScanDiffResult.space_generations`、`watch=False` 自動刷新與 `CursorStore` 執行緒安全說明 |
| `CHANGELOG.md` | Modify | 記錄 `sub_06` 調研審視與四大模組熱自癒邊界修復摘要 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：四大模組 `dev check` 100% `PASSED`；單元與整合測試總計 **534/534 (100.0%)** 通過（`core`: 221/221、`file-space`: 15/15、`knowledge-db`: 157/157、`agents-workflow`: 141/141），並完成 `@build` 熱部署與 `agents-workflow release` 驗證。
- **實機 UX / 人工驗證**：`UX-01` 經開發者確認 `[跳過/免測]`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 完整記錄 `sub_06` 審視與四大模組指紋/自癒修復摘要 |
| **中觀 (Meso)** | `docs/file-space/README.md` | 已更新 | 補充 `ScanDiffResult.space_generations`、`watch=False` 刷新與 `CursorStore` 鎖說明 |
| **中觀 (Meso)** | `docs/core/contributes_architecture.md` | 免更 | 既有架構描述已涵蓋 JIT 髒檢查機制 |
| **中觀 (Meso)** | `docs/file-space/DESIGN_NOTES.md` | 免更 | 屬既有設計契約之邊界修補，無新增反直覺妥協 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已更新 | 同步維護 `schema.py`、`scanner.py`、`pipeline.py`、`bundler.py`、`io_utils.py`、`uri.py`、`publisher.py` Docstring |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack（經 `Pre-UX Blind Reviewer R2` 審查 `REVIEW_STATUS: PASSED`）。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(ecosystem): resolve fingerprint and self-healing edge cases across core, file-space, knowledge-db, and agents-workflow

- knowledge-db: evict old_doc_ids from VectorIndex during Stage 1 skip_vectors hot-patch and normalize space-relative dirty paths
- file-space: track per-space generations in ScanDiffResult for exact ack(None), allow auto_refresh for unwatched spaces, and guard CursorStore with RLock
- core: add thread-local reentrancy guard for URI scheme JIT dirty checks and track module.source _format.json & project locale files
- agents-workflow: reuse _sha1_cache for directory walks, include active locale chain in source fingerprint, and verify AGENTS.md managed markers in Stage 0
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_02_0339_module_space_feasibility_research/sub_06_fingerprint_and_self_healing_audit` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

