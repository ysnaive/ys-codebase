# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：熱路徑效能與增量管線深度優化  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.contributes.get()` 記憶體快取與失效機制 | 新增模組級記憶體快取（以 `(yscb_root, target_module)` 為鍵記錄 `(meta_mtime, merged_mtime, data)`）與短時窗（`100ms` 單調時鐘）免重掃 `_scan_contributes_inputs()` 快取；當 `contributes.meta.json` 與 `contributes.merged.json` 之 mtime 未變且處於免掃視窗內時直接回傳快取資料；`ContributesAggregator.scan_and_inject()` 完成時主動更新/清空快取，並提供 `invalidate_cache()` | P1 | [P00:DR-02] |
| **FR-02** | `FileSpaceManager` 路徑解析與 `load_spaces` 快取 | `project_root` 屬性快取於實例 `_cached_project_root`；`_compute_rel_path` 支援接收預先解析之 `proj_root`；`_walk_root` 於 `not is_symlink and not cfg.follow_symlinks` 時直接使用 `entry_path` 免除逐檔 `resolve()`（`follow_symlinks=True` 時維持 `resolve()`）；`load_spaces(self, force: bool = False)` 於 `self._loaded and not force` 時直接回傳 `dict(self._spaces)`，且將 `ast` / `knowledge-db` 內部唯讀呼叫 `load_spaces()` 改為 `get_all_spaces()` | P1 | [P00:DR-03] |
| **FR-03** | `ast` 單檔增量熱修補 $O(|\text{dirty}|)$ 收斂 | `SemanticBundler` 新增 `_resolve_dirty_files_only(dirty_raw_paths, target_spaces, snap_entries_by_space)` 直接透過 YFP2 快照 `entries` 或空間 `include` 根目錄以 $O(|\text{dirty}|)$ 定位髒檔案，使 `bundle_dirty_files` 與 `extract_dirty_call_sites_and_imports` 不再呼叫 `_collect_space_files` 全倉走訪；`_normalize_space_dirty_paths` 支援傳入預載之 `snap_entries_by_space` 免重複讀盤；`ASTEngine.hot_patch_index` 新增 `_cursor_already_consumed: bool = False`（由 `ensure_jit_synced` 傳入 `True`）消除巢狀 `_consume_space_diff`，並支援以既有 `files_map` + diff 差量（或快照 `active_entries`）更新 `files_map` 免第 4 次全倉掃描 | P1 | [P00:DR-06] |
| **FR-04** | `knowledge-db` 背景向量微批次鎖分離與持久化節流 | `IndexingPipeline.sync_vector_deficit_step(batch_size: int = 32, persist: bool = True)` 將耗時之 `embedding_service.embed_texts()` 移出 `self._index_lock` 外執行，寫回前二次過濾仍存在於 ` self._unified_index.symbols` 之 doc_ids；新增 `flush_vector_index()` 供強制存盤並更新 `_GLOBAL_INDEX_CACHE`；`KnowledgeDBServiceWorker._run_sync_cycle` 每滿 8 批（256 個符號）或距上次存盤 $\ge 2.0$ 秒才傳入 `persist=True`，並於迴圈結束或 `finally` 退出時若有未存盤變更強制呼叫 `flush_vector_index()` | P2 | [P00:DR-04] |
| **FR-05** | `InvertedIndex` 與 `ASTEngine` 增量淘汰索引加速 | `InvertedIndex.patch_incremental` 於移除舊符號分詞迴圈中收集 `removed_terms: Set[str]`，僅針對 `for term in removed_terms:` 過濾 `self.index[term]`（若 `doc_ids_set` 非空但 `removed_terms` 為空則 fallback 全表掃描）；同時於 `InvertedIndex` 與 `ASTEngine._evict_dirty_and_reaggregate_partials` 優先利用 `file_to_symbol_ids` / 髒檔路徑快速定位舊符號 ID | P2 | [P00:DR-07] |
| **FR-06** | `ast` 全量建置單次讀檔與解析快取复用 | `_parse_file_task_worker` 與 `SemanticBundler._parse_and_dedup_file`（或新增輔助方法）於單次讀檔中同時提取 `(symbols, call_sites, imports)` 並緩存於 `SemanticBundler._file_call_sites_cache` 與 `_file_imports_cache`；`extract_all_call_sites_and_imports` 優先消費快取中已提取之呼叫點與匯入，僅對快取未命中之檔案讀檔解析 | P2 | [P00:DR-05] |
| **FR-07** | `dev` 沙盒模組部署消除雙倍 I/O | `SandboxProvisioner._deploy_target_and_dependency_modules` 先掃描 `module.build://` 建立 `build_zip_map: Dict[str, str]`；對存在有效 `.build.zip` 之模組直接解壓至沙盒 `.modules/<mod>`（跳過前置 `shutil.copytree` 與 `shutil.rmtree`），若 `.build.zip` 解壓拋出 `(zipfile.BadZipFile, OSError)` 則自動回退從宿主 `.modules/<mod>` 執行 `shutil.copytree` | P2 | [P00:DR-07] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 同一進程內距上次掃描 $< 100\text{ms}$ 執行 `scan_and_inject()` 或寫入新 `contribute.json` | `scan_and_inject()` 主動呼叫 `invalidate_cache()`；若外部直接改寫磁碟上的 `contributes.meta.json` / `merged.json` 使 mtime 改變，雙 mtime 守衛立即偵測並失效快取 |
| **EC-02** | `FileSpaceConfig.follow_symlinks=True` 且包含 symlink 子目錄 | `_walk_root` 檢測到 `cfg.follow_symlinks=True` 或 `is_symlink=True` 時維持 `entry_path.resolve()`，確保相對路徑計算與舊行為 100% 一致 |
| **EC-03** | 增量熱修補之髒檔案不在 YFP2 快照中（例如手動傳入自訂 `ScanDiffDetail`） | `_resolve_dirty_files_only` 自動回退至各 `target_spaces` 之 `resolve_space_include` 拼接候選路徑並驗證 `exists()` 與 `is_file_included()` |
| **EC-04** | 背景向量推論（鎖外）期間，前景或 Stage 1 插隊刪除／更新了部分符號 | 第二段重新進入 `_index_lock` 後，過濾掉已不在 `idx.symbols` 中之 `sid`，僅寫入仍有效之向量 |
| **EC-05** | 背景 Worker 於未滿 8 批時收到 `_stop_event` 中斷或拋出異常 | `finally` 區塊檢測 `unpersisted_changes > 0` 時強制呼叫 `flush_vector_index()` 落盤，零進度遺失 |
| **EC-06** | 沙盒部署時 `.build.zip` 損壞或解壓失敗 | 捕獲 `(zipfile.BadZipFile, OSError)`，清理殘留空目錄並自動回退至宿主 `.modules/<mod>` `shutil.copytree`，不留下空模組目錄 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 | 單檔增量 `hot_patch_index`（Watcher 活躍或已消費 diff 時）觸發之全倉 `iter_space_files` 次數為 `0`；單次 CLI 內連續呼叫 `contributes.get()` 10 次僅觸發 `1` 次 `_scan_contributes_inputs()` |
| **NFR-02** | 相容性 | 所有公開 API 與 `.bin.gz` 快取格式 100% 向下相容；既有 `core`、`file-space`、`ast`、`knowledge-db`、`dev` 單元測試全數通過 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `docs/knowledge-db/DESIGN_NOTES.md` `[DN-30]`：嚴格遵守 `file-space -> ast -> knowledge-db` 單向依賴與 `acked_ast_generation` 水位線協議；修改 `ASTEngine.hot_patch_index` 時必須維持 `ast_generation += 1` 與 `space_generations` 更新。
- **`[!NOTE]`** `ProcessPoolExecutor` 在 Windows 下採用 `spawn`，`_parse_file_task_worker` 必須保持為模組頂層可 Pickle 函式，回傳值僅含基本型別（`dict` / `list` / `str`）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[T-10] core.contributes.get(target, key)
  └─ check _MERGED_MEM_CACHE[(yscb_root, target)] & _LAST_CLEAN_SCAN_TS[yscb_root] (<100ms + mtimes match)
       ├─ Hit  -> O(1) return cached dict
       └─ Miss -> _is_contributes_dirty() -> read merged.json or scan_and_inject() -> update cache

[T-11] FileSpaceManager
  ├─ project_root -> cached in self._cached_project_root
  ├─ load_spaces(force=False) -> guard `if self._loaded and not force: return dict(self._spaces)`
  └─ iter_space_files -> pass proj_root into _walk_root -> skip resolve() when not is_symlink and not follow_symlinks

[T-09 & T-19] ASTEngine & SemanticBundler
  ├─ bundle_union: single file read -> parse symbols + extract call_sites + extract imports -> cache in bundler
  ├─ extract_all_call_sites_and_imports: hit _file_call_sites_cache / _file_imports_cache (0 disk re-read)
  └─ ensure_jit_synced -> _consume_space_diff -> hot_patch_index(..., _cursor_already_consumed=True)
       ├─ _preload_snap_entries(target_spaces) once
       ├─ bundle_dirty_files -> _resolve_dirty_files_only (O(|dirty|), 0 full tree walk)
       ├─ extract_dirty_call_sites_and_imports -> reuse dirty file resolution + cached symbols
       └─ _ update files_map incrementally & skip inner _consume_space_diff when _cursor_already_consumed=True

[T-17 & T-18] KnowledgeDB Pipeline & InvertedIndex
  ├─ InvertedIndex.patch_incremental: collect removed_terms during token length subtraction -> prune only removed_terms
  └─ sync_vector_deficit_step(batch_size, persist=True):
       ├─ lock: select missing_ids & format texts
       ├─ unlock: embedding_service.embed_texts(batch_texts)
       └─ lock: filter surviving ids -> patch_incremental -> save_binary if persist or remaining==0
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/contributes.py` | Modify | FR-01：新增 `_MERGED_MEMORY_CACHE`、`_LAST_CLEAN_SCAN_TS`、`invalidate_cache()` 與 `get()` 快取快速路徑 |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | FR-02：快取 `_cached_project_root`、`load_spaces(force=False)` 守衛、`_walk_root` 免冗餘 `resolve()` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | FR-02/03/06：`_ preload_snap_entries`、`_resolve_dirty_files_only`、單次讀檔提取 `(symbols, call_sites, imports)` 與快取、`load_spaces()` 改 `get_all_spaces()` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | FR-02/03/05：`hot_patch_index(_cursor_already_consumed=False)`、增量更新 `files_map`、利用 `file_to_symbol_ids` 加速舊符號定位、`load_spaces()` 改 `get_all_spaces()` |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | FR-02：`load_spaces()` 改 `get_all_spaces()` |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | FR-05：`InvertedIndex.patch_incremental` 僅針對 `removed_terms` 修剪 Posting |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | FR-02/04：`sync_vector_deficit_step(batch_size=32, persist=True)` 鎖分離、`flush_vector_index()`、`load_spaces()` 改 `get_all_spaces()` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | FR-04：Stage 2 迴圈每 8 批或 2.0s 存盤一次，退出時 `flush_vector_index()` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | FR-02：`load_spaces()` 改 `get_all_spaces()` |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | FR-07：`_deploy_target_and_dependency_modules` 預建 `build_zip_map` 消除雙倍拷貝並支援壞 zip 回退 |
| `ys_codebase/source/core/tests/test_contributes.py` | Modify | 測試 FR-01 與 EC-01 |
| `ys_codebase/source/file-space/tests/test_file_space_manager.py` | Modify | 測試 FR-02 與 EC-02 |
| `ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 測試 FR-03、FR-05、FR-06 與 EC-03 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 測試 FR-04、FR-05、EC-04、EC-05 |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 測試 FR-07 與 EC-06 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `core.contributes` 快取同時檢查 `contributes.meta.json` 與 `contributes.merged.json` 的實體檔案 mtime，並搭配 `100ms` 單調時鐘視窗略過 `_scan_contributes_inputs()`，在單元測試若直接修改源碼 `contributes/*.json` 並希望立即反映時，可呼叫 `contributes.invalidate_cache()` 或等待 `100ms`。
- **[P02:DR-02]** `ASTEngine.hot_patch_index` 更新 `files_map` 時，若 `self._snapshot.files_map` 已有該空間清單，則直接從 YFP2 快照 `active_entries`（或既有清單加減 `added`/`deleted`）合成，免除重跑 `_iter_space_eligible_files` 全倉走訪。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/contributes.py
def invalidate_cache(target_module: Optional[str] = None) -> None: ...
def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any: ...

# ys_codebase/source/file-space/file_space/manager.py
class FileSpaceManager:
    @property
    def project_root(self) -> Path: ...
    def load_spaces(self, force: bool = False) -> Dict[str, FileSpaceConfig]: ...

# ys_codebase/source/ast/ast_engine/bundler.py
def _parse_file_task_worker(
    task: Tuple[str, str, str, List[str]],
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str], Optional[str]]: ...

class SemanticBundler:
    def _resolve_dirty_files_only(
        self,
        dirty_raw_paths: Iterable[str],
        target_spaces: List[FileSpaceConfig],
        snap_entries_by_space: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Tuple[Path, str, Set[str]]]: ...

# ys_codebase/source/ast/ast_engine/engine.py
class ASTEngine:
    def hot_patch_index(
        self,
        diff_detail: Union[ScanDiffDetail, ScanDiffResult, Dict[str, Any]],
        spaces: Optional[List[str]] = None,
        _cursor_already_consumed: bool = False,
    ) -> ASTSnapshot: ...

# ys_codebase/source/knowledge-db/knowledge_db/pipeline.py
class IndexingPipeline:
    def sync_vector_deficit_step(self, batch_size: int = 32, persist: bool = True) -> Dict[str, int]: ...
    def flush_vector_index(self) -> bool: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：所有新增選配參數均具向下相容預設值；`_parse_file_task_worker` 維持捕獲單檔解析異常並回傳錯誤字串；`sync_vector_deficit_step` 於锁外推論拋出異常時安全返回 `embedded_in_step=0` 且不破壞既有 `vector_index`。
- **階段決策紀錄**：`[P03:DR-01]` `_parse_file_task_worker` 回傳元組擴充為 5 元組 `(c_key, sym_dicts, call_site_dicts, imports_dict, err)`，仅供 `bundle_union` 內部消費，不影響外部公開 API。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-07 皆已於介面簽名與實作規劃中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-06 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束（零新增第三方依賴）
- **靈魂拷問與防護解法**：
  - 若測試在 `< 100ms` 內連續修改模組 `contributes/*.json` 並呼叫 `contributes.get()` 驗證 JIT 自癒怎麼辦？→ 在 `_is_contributes_dirty` 快取視窗設計上，只有當 `contributes.meta.json` 與 `contributes.merged.json` 皆存在且 mtime 未變時才啟用短時窗；為確保既有 JIT 自癒測試（在同一微秒級測試內直接改寫源碼檔並立刻呼叫 `contributes.get()`）不因 100ms 視窗而失敗，我們可以檢查：是什麼讓 `locale.t()` 慢？是每次呼叫都重新 `read_json(merged.json)` 以及掃描！如果我們快取已解析的 `merged.json` 字典（只要 `_is_contributes_dirty` 為 False 就不重讀 `merged.json`），且將免掃視窗設為 `20ms`（足以涵蓋單次 `locale.t()` 內部連續 3~5 次呼叫），並在 `vfs.write_json` / `vfs.write_text` 或 `scan_and_inject` 時自動失效快取，即可同時 100% 通過即時修改測試並消除重複掃描！
  - `InvertedIndex.patch_incremental` 若某個符號包含自訂詞條或 C# partial 重聚合，僅掃 `removed_terms` 是否會漏刪 Posting？→ `add_document` 寫入 `self.index` 的每一個 term 皆來自同一個 `self.tokenizer.tokenize(text)` 對完全相同 4 個欄位的分詞結果；只要使用同一個 `tok` 實例，分詞結果 100% 確定性相等，因此不會漏刪。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/ast/README.md`, `docs/file-space/README.md` | Modify | 更新 `load_spaces(force=False)` 與單次讀檔建置說明 |
| **專題手冊** | `docs/knowledge-db/incremental_hot_reload.md`, `docs/core/contributes_architecture.md` | Modify | 更新 Stage 2 向量微批次鎖分離與檢查點持久化、`contributes.get` 記憶體快取與 `invalidate_cache()` |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | N/A | 既有 DN-10 / DN-30 已涵蓋，直接更新專題手冊免增 DN |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本子計畫版本發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認對齊三層文檔，於 Phase 07 同步更新。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core.contributes` 記憶體快取與 `invalidate_cache()`（FR-01, EC-01）及單元測試
- [x] **TASK-02**：實作 `FileSpaceManager` `project_root` 快取、`_walk_root` 路徑優化與 `load_spaces(force=False)` 守衛（FR-02, EC-02）及單元測試
- [x] **TASK-03**：實作 `ast` `SemanticBundler` 與 `ASTEngine` 單檔增量 $O(|\text{dirty}|)$ 定位、消除巢狀 `_consume_space_diff` 與全量建置單次讀檔快取（FR-03, FR-06, EC-03）及單元測試
- [x] **TASK-04**：實作 `knowledge-db` Stage 2 向量鎖分離與批次持久化節流、`InvertedIndex.patch_incremental` `removed_terms` 精準修剪（FR-04, FR-05, EC-04, EC-05）及單元測試
- [x] **TASK-05**：實作 `dev` `SandboxProvisioner` `.build.zip` 預篩部署與壞包回退（FR-07, EC-06）及單元測試
- [x] **TASK-DOC**：同步更新微觀代碼 Docstrings 與模組檢查

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | Minor | `_CLEAN_SCAN_WINDOW_SEC` 定為 `0.04`（40ms 單調時鐘視窗）並搭配 `meta.json` 與 `merged.json` 雙 mtime 守衛，確保單次 CLI 多語系連發快取命中且不影響既有 JIT 自癒測試 | 已記錄於 `core/contributes.py` |
| **TASK-02~04** | Minor | 單元測試合併寫入各模組既有對應測試檔（`test_file_space_manager.py`、`test_provisioner_and_jit.py`、`test_service_worker.py`）以複用既有 Fixture | 已回寫 §2.2 |

