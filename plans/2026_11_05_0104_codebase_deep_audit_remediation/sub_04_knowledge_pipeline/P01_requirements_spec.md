# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_04 空間指紋、AST 解析與知識庫檢索深層審計收斂 (Knowledge Pipeline Remediation)  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_05_0104_codebase_deep_audit_remediation  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `module:file-space` 跨空間游標、符號連結走訪與原子寫入加固 (`FS-01`~`06`) | 1. **Watcher 髒標記信標與全域世代對齊 (`FS-01`)**：`FileSpaceWatcherServiceWorker` 於接收未沖刷變更期間建立 `.watcher_dirty` 信標檔並於沖刷完成或關閉時清除；`FingerprintScanner.is_watcher_dirty()` 供跨行程 `consume_diff()` 偵測未沖刷視窗並觸發 `auto_refresh=True`；`ack(space_name=None)` 於 `generation is None` 時與 `_diff_all_spaces()` 對齊採用 `max(u_state.head_generation, sum(space_gens.values()))`。<br/>2. **符號連結邏輯路徑與 Inode=0 防護 (`FS-02`)**：`_walk_root` 於 `follow_symlinks=True` 時僅在 `dir_stat.st_ino != 0` 將 `(st_dev, st_ino)` 納入 `visited_dirs`，且檔案相對路徑基於走訪樹 `entry_path` 計算以保留符號連結子目錄邏輯路徑。<br/>3. **專案組態覆寫保護 (`FS-03`)**：`_apply_project_space_overrides` 加入 `self._explicit_project_root is None` 守衛（同時保留 `has_explicit_project_override` 與 `override_mode == "replace"`），使預設無參 `FileSpaceManager()` 正常合併專案 `contribute.json`，並防止傳入 `project_root=tmp_dir` 之沙盒測試遭宿主組態污染。<br/>4. **Windows 原子替換重試 (`FS-04`)**：`_atomic_write_bytes` 對 `os.replace` 增設 `PermissionError` 有界指數退避重試。<br/>5. **CLI 全空間 `--ack` 世代轉發 (`FS-05`)**：`scripts/cli.py:diff --ack` 將 `space_generations=diff_res.space_generations` 轉發予 `scanner.ack()`。<br/>6. **單檔 `include` 支援 (`FS-06`)**：`resolve_space_include`、`iter_space_files_with_stat` 與 `patch_space_files` 支援指向單一既有檔案之 `include` 項目。 | P0 | [P00:DR-01] |
| **FR-02** | `module:ast` 增量路徑匹配、多核心解析與跨語言拓撲連結 (`AST-01`~`06`) | 1. **根目錄單檔髒路徑匹配與 `best_mtime_ns` 消歧 (`AST-01`)**：`ast_engine/io_utils.py:is_dirty_file_match` 在保留 `"/" in sym_path_norm` 雙向 `.endswith("/" + ...)` 之前提下，允許 `"/" not in sym_path_norm` 根目錄單檔匹配絕對髒路徑 `p.endswith("/" + sym_path_norm)`；`bundler.py:_resolve_dirty_files_only` 對跨空間同名 `clean_p` 套用 `best_mtime_ns` 消歧。<br/>2. **預設語言配置平行解析解鎖 (`AST-02`)**：`bundler.py:bundle_union` 精確判定非內建 `DEFAULT_LANGUAGES` 之自訂解析器配置，避免內建語言表導致 `has_custom_configs` 恆為 `True` 而永久停用 `ProcessPoolExecutor`。<br/>3. **Hook 冷啟動全空間建置與游標防雙重消費 (`AST-03`)**：`scripts/hook.file-space.py` 於 `not has_existing_snapshot` 冷啟動時傳入 `spaces=None` 建置完整快照，並於 `hot_patch_index` 傳入 `_cursor_already_consumed=True`。<br/>4. **C# 檔案級命名空間範圍延伸 (`AST-04`)**：`CSharpDialect.finalize_raw_items` 將 `file_scoped_namespace_declaration` 之 `end_line` 與 `end_byte` 延伸至檔案結尾，確保後續型別正確歸入命名空間 FQN。<br/>5. **符號連結器快取一致性與公開 API 契約 (`AST-05`、`AST-06`)**：`SymbolLinker` 之 `_LAST_LINKER_CACHE` 納入符號內容指紋以防原地熱修補後命中過期快取；`ASTSnapshot.from_dict` 容錯還原序列形式之 `symbols`。 | P0 | [P00:DR-02] |
| **FR-03** | `module:knowledge-db` 雙水位線自癒、跨行程鎖與檢索管線優化 (`KDB-01`~`06`) | 1. **背景 Worker 冷啟動雙水位線自癒 (`KDB-01`)**：`KnowledgeDBServiceWorker._has_pending_space_work` 與 `_sync_stage1_lexical_and_graph` 於讀取 `unified_index` 前先呼叫 `_ensure_indices_loaded(load_vectors=False)`，確保冷啟動時正確觸發 `[DN-30]` 雙水位線比對自癒。<br/>2. **二進位索引持久化跨行程鎖 (`KDB-02`)**：`pipeline.py` 中 `_hot_patch_unified_index_locked` (`skip_vectors=True` 分支) 與 `build_index` 之 `save_binary` 統一包裹 `with self._kdb_index_file_lock():`。<br/>3. **混合檢索副檔名正規化與分數尺度隔離 (`KDB-03`)**：`hybrid.py` 改以 `Path(sym.file_path).suffix.lstrip(".").lower()` 提取副檔名，且嚴禁將 BM25 尺度之 `flt.min_score` 套用於 RRF 融合分數。<br/>4. **多空間 Bundle 匯出路徑防覆蓋 (`KDB-04`)**：`engine.py:bundle()` 於多空間匯出且指定 `export_path` 時自動衍生各空間專屬檔名，防止迴圈覆寫同一檔案。<br/>5. **JIT 索引重建游標防重複消費 (`KDB-05`)**：移除 `_ensure_jit_index_ready_locked` 於 `build_unified_index(force=True)` 後多餘的 `_consume_space_diff`。<br/>6. **倒排索引免重複分部聚合 (`KDB-06`)**：`InvertedIndex.build` 新增 `pre_aggregated: bool = False`，於 `pipeline.py` 單次解析共享路徑傳入 `pre_aggregated=True`。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 測試沙盒傳入 `FileSpaceManager(project_root=tmp_dir)` 且未帶顯式 `config` | 透過 `self._explicit_project_root is None` 守衛阻斷宿主 `config://file-space/contribute.json` 跨界混入測試沙盒，同時確保無參生產實例正常載入專案空間覆寫。 |
| **EC-02** | Windows 或虛擬檔案系統上 `os.stat` 回傳 `st_ino == 0` | `_walk_root` 僅於 `dir_stat.st_ino != 0` 時記錄 `(st_dev, st_ino)`，避免所有目錄因 `(0, 0)` 碰撞而被誤判為符號連結迴圈跳過。 |
| **EC-03** | 根目錄單檔（無 `/`）於多空間同名或以絕對路徑傳入髒清單 | `is_dirty_file_match` 僅允許無 `/` 符號路徑匹配絕對路徑形式之髒項目，且 `_resolve_dirty_files_only` 透過 `best_mtime_ns` 選出最新修改空間，杜絕跨空間同名誤綁定。 |
| **EC-04** | 無副檔名但父目錄含 `.` 之檔案（如 `.agents/skills/Makefile`）進行 `ftypes` 過濾 | `HybridSearchEngine` 使用 `Path(sym.file_path).suffix.lstrip(".").lower()` 提取真實副檔名（空字串），避免 `split(".")[-1]` 截出父目錄路徑片段。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與併發安全 | `ASTSnapshot` 轉交 `InvertedIndex.build(..., pre_aggregated=True)` 免除重複 $O(N)$ 分部類別聚合；所有二進位索引寫入 100% 受跨行程鎖與 `PermissionError` 退避重試保護。 |
| **NFR-02** | 契約相容與靜態合規 | 嚴格遵守防回歸紅線 7 與紅線 8；生產源碼零審計代號殘留；通過 `yscb dev check {file-space,ast,knowledge-db}` 與 `py_compile` 100% 零錯誤。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 防回歸紅線 7 (`file-space` 測試沙盒隔離與 `ast` 路徑對齊)**：`FileSpaceManager._apply_project_space_overrides` 必須加上 `self._explicit_project_root is None` 守衛並保留 `has_explicit_project_override`；`ast_engine/io_utils.py:is_dirty_file_match` 必須保留 `"/" in sym_path_norm` 時的雙向 `.endswith("/" + ...)`，僅修正 `"/" not in sym_path_norm` 根目錄單檔允許匹配絕對路徑 `p`。
- **`[!CAUTION]` 防回歸紅線 8 (`knowledge-db` RRF 分數尺度)**：`HybridSearchEngine` 的 RRF 分數約為 $0.01 \sim 0.033$，與 BM25 分數尺度（$1.0 \sim 20.0+$）完全不同，嚴禁將 `flt.min_score` 套用於 `hybrid_rrf` 融合結果。
