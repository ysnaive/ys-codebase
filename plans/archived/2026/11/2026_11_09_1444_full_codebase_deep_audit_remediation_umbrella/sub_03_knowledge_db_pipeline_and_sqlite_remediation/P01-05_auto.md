# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_03_knowledge_db_pipeline_and_sqlite_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `hot_patch_unified_index` C# `partial class` 跨檔閉包收集與多世代跳號防護 (`KDB-AUD-01`, `KDB-AUD-04`) | 1. [`pipeline.py`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) 將 `dirty_keys` 擴展與 `dirty_symbols` 收集拆為兩步：先對命中 `dirty_keys` 的符號將其 `sym.file_path` 及 `partial_files` 全數併入 `dirty_keys`，再遍歷 `snapshot.symbols.values()` 收集所有匹配擴展後 `dirty_keys` 的符號，確保主檔案非 partial 符號 100% 保留。<br>2. 檢查 `snapshot.ast_generation` 與索引內 `acked_ast_generation`：若世代跨距 $> 1$，自動比對新舊快照符號差異並將受影響檔案納入 `dirty_keys`。 | P0 | [P00:DR-01] |
| **FR-02** | 常駐空閒 JIT 增量同步與 `build_unified_index(force=False)` 完整性守門 (`KDB-AUD-02`, `KDB-AUD-03`) | 1. [`pipeline.py`](https://drive.google.com/file/d/1nySfKwl5clHi3wj2E_3fYQ_BQBcs3iJd/view?usp=drivesdk) 當 `worker_active and not worker_busy` 且非 `degraded_offline` 時，檢查空間游標是否落後（`_has_pending_space_changes`），若落後則執行輕量增量同步而非直接返回陳舊索引。<br>2. `build_unified_index(force=False)` 若發現磁碟已有 `unified.index.bin.gz`，先檢驗是否有未同步空間變更與向量缺口，並同步更新 `_GLOBAL_INDEX_CACHE`。 | P0 | [P00:DR-01] |
| **FR-03** | `hook.ast.py` 多來源貢獻聚合、切片 `/*` 詞法防護與混合檢索預過濾/雙詞選擇器修正 (`KDB-AUD-05` ~ `KDB-AUD-07`) | 1. [`scripts/hook.ast.py`](https://drive.google.com/file/d/1ntSU_gIwR8f5ZM_VOqg2db8FBAi-ziLr/view?usp=drivesdk) 同時支援 `core.contributes.get("knowledge-db")` 回傳 `list` 或 `dict`，並納管專案級 `config://knowledge-db/contribute.json`。<br>2. [`formatter.py`](https://drive.google.com/file/d/1Mmm6ktWLTFobKxE4h__Ds6zDSIlP0_sV/view?usp=drivesdk) `purify_lines` 忽略字串常數內的 `"/*"` 並處理同列 `"*/"` 閉合。<br>3. [`hybrid.py`](https://drive.google.com/file/d/1LDMLddPaUzIYWDCXfcGJzs6N4Pt-xvXi/view?usp=drivesdk) 與 [`embedding.py`](https://drive.google.com/file/d/1uzribxfnZsrfupWHqnOnkR-SHj8W0jWh/view?usp=drivesdk) 支援 `allowed_doc_ids` 遮罩與全池檢索過濾早退；[`selector.py`](https://drive.google.com/file/d/148p_sUneWNWzkpkr51aNwwS7POjYe45Y/view?usp=drivesdk) 僅當首詞匹配 `KIND_PREFIX_MAP` 時才剝離為 `target_kinds`。 | P1 | [P00:DR-02] |
| **FR-04** | 組態互斥鍵與權重校驗、清理鎖與狀態鍵對齊、空向量還原、BM25 完整排序截斷、macOS 路徑解析與 P3 效能優化 (`KDB-AUD-08` ~ `KDB-AUD-14`) | 1. [`config.py`](https://drive.google.com/file/d/111Qj35vYsej9Zd0JrLkEgdkfG6QmmLAX/view?usp=drivesdk) 與 [`schema.py`](https://drive.google.com/file/d/1NQhH7d0ndfViI-pk6oj-wbJw7wzXQ-uK/view?usp=drivesdk) 處理 `jit_vector_timeout_ms` / `jit_vector_timeout_seconds` 互斥覆寫並攔截 `NaN`/`Inf` 權重。<br>2. `_clean_locked` 加 `_kdb_index_file_lock` 並對齊 [`service.py`](https://drive.google.com/file/d/1-d5Z8_Ejlus4zHLSMGWxH8jKMGPFft1r/view?usp=drivesdk) 的 `"kdb.worker_state"`。<br>3. 修復 `VectorIndex.load_binary` 空向量時 `model_name`/`dim` 還原、`BM25Engine.search_aggregated` 過早截斷與 `ResultFormatter` `Path(workspace_root).resolve()`。<br>4. 落實 `_filter_symbol_for_indexed_spaces` 早退與 `status`/`model_status` 零模型載入維度查表。 | P2 | [P00:DR-01], [P00:DR-02] |
| **FR-05** | Mode A 手術 `S2`：解除前景/背景「互讓死鎖悖論」、收斂單一增量同步入口與 `.tmp` 原子清理 (`ARCH-KDB-01` ~ `ARCH-KDB-11`) | 1. [`service.py`](https://drive.google.com/file/d/1-d5Z8_Ejlus4zHLSMGWxH8jKMGPFft1r/view?usp=drivesdk) Stage 2 禮讓 `foreground_active` 時先 `flush_vector_index()` 並標記 `phase="yielded_to_foreground"`；`_ensure_indices_loaded` 不以舊磁碟向量覆寫記憶體中較新的髒向量 (`ARCH-KDB-01`)。<br>2. 於 `IndexingPipeline` 實作 `sync_incremental_changes`（別名 `sync_lexical_index`），統一 `pipeline.py`、`service.py` 與 `scripts/hook.core.py` 的增量同步迴圈 (`ARCH-KDB-02`)。<br>3. [`io_utils.py`](https://drive.google.com/file/d/1ZzJ0Zs0MLyDI20pe6KECkSBngXV1nHnd/view?usp=drivesdk) `atomic_save_gzip_pickle` 於 `finally` 區塊清理殘留 `.tmp` 暫存檔；[`retrieval.py`](https://drive.google.com/file/d/1VoC02aZmq3DrQFFdseFBefAi3IO4hDd_/view?usp=drivesdk) 抽離 `aggregate_ranked_symbol_hits` 並優化 BM25 計分迴圈 (`ARCH-KDB-05` ~ `08`)。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | C# 主檔 `Player.cs` 含 `PlayerService` 與 `HelperStruct`，開發者新增副檔 `Player.Combat.cs` 後觸發 `hot_patch_unified_index` | `Player.cs` 被納入擴展後之 `dirty_keys`，第二階段遍歷將 `Player.cs` 內的 `HelperStruct` 一併納入 `all_new_symbols`，修補後 `HelperStruct` 100% 存在於索引中。 |
| **EC-02** | 被切片之 Python/TypeScript 程式碼行包含 `pattern = "src/*"` 或單行 `/* inline comment */` | `UniversalRedundancyFilter.purify_lines` 正確識別字串邊界與單行閉合，不將後續實作程式碼誤判為未閉合多行註解。 |
| **EC-03** | 使用者輸入雙詞一般關鍵字查詢（如 `"user profile"`）且指定特定 `--space` 過濾 | `SymbolSelector` 不誤吞首詞 `"user"`；向量檢索在目標空間內取 Top-K，不因全域前 30 名落於其他空間而回傳 0 筆。 |
| **EC-04** | 背景 `KnowledgeDBServiceWorker` 執行 Stage 2 微批次嵌入期間，前景發起 `search` 觸發 `foreground_active=True` | 背景先持久化已算完之向量並標記 `phase="yielded_to_foreground"`，前景 `_ensure_indices_loaded` 絕不以舊磁碟向量洗掉記憶體內已完成的向量進度。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 狀態查詢零副作用與檢索加速 | `kdb status` 與 `kdb model status` 在模型尚未載入記憶體時 0 次呼叫 `_ensure_model()`；BM25 與 Hybrid 檢索延遲較基線下降 $\ge 15\%$。 |
| **NFR-02** | 靜態守門與回歸測試 | `python3 yscb.py dev check` 0 違規，`python3 yscb.py dev test --m knowledge-db` 100% 通過（116/116）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 在 macOS 上 `tempfile.mkdtemp()` 產生之 `/var/folders/...` 與 `Path.resolve()` 後之 `/private/var/folders/...` 字串前綴不同，`ResultFormatter` 計算相對路徑前必須對 `workspace_root` 與目標路徑雙邊統一 `.resolve()`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

- **單一增量同步入口 (`IndexingPipeline.sync_incremental_changes`)**：統一處理單空間與多空間游標消費、`hot_patch_unified_index` 增量修補、水位線檢查與失敗回退 `build_unified_index`，供 `pipeline.py`、`service.py` 與 `scripts/hook.core.py` 共用。
- **兩階段髒檔閉包收集 (`IndexingPipeline._collect_all_dirty_files`)**：Pass 1 擴展 `dirty_keys` 至所有 `partial_files` 關聯檔案及跨世代差異檔案；Pass 2 依據最終 `dirty_keys` 收集完整 `all_new_symbols`，再交由 `_evict_dirty_file_artifacts` 與 `patch_incremental` 原子替換。
- **過濾條件下推與共用聚合 (`HybridSearchEngine` / `VectorIndex` / `aggregate_ranked_symbol_hits`)**：消除 Top-30 後置過濾飢餓，並合併 `pipeline.py` 與 `retrieval.py` 的檔案級分數聚合邏輯。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 實作 `sync_incremental_changes`、修復 `partial class` 跨檔閉包收集、常駐空閒 JIT 同步、`build_unified_index(force=False)` 短路、多世代跳號、互讓悖論防禦、`_clean_locked` 檔案鎖與維度查表 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 對齊 `WORKER_CELL_STATE_KEY = "kdb.worker_state"`、Stage 2 禮讓前景時 `flush_vector_index()` 並標記 `yielded_to_foreground`、委派 `sync_incremental_changes` |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `status`/`model_status` 改用不觸發模型載入之靜態維度查表，`get_engine()` 僅於模型變更時重置 `_model` |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | 帶過濾條件時擴大向量檢索池並於集滿 `fetch_limit` 時早退，消除篩選飢餓與多餘矩陣拷貝 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | 移除 `BM25Engine.search_aggregated` 未排序前之過早截斷、抽離 `aggregate_ranked_symbol_hits` 並優化 `_score_candidate_documents` 計分迴圈 |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 修復 `VectorIndex.load_binary` 空向量時 `model_name`/`dim` 還原，支援 `allowed_doc_ids` 過濾與 `check_availability` |
| `ys_codebase/source/knowledge-db/knowledge_db/formatter.py` | Modify | 修復 `purify_lines` 字串內 `"/*"` 誤判與 `workspace_root` `.resolve()` 正規化 |
| `ys_codebase/source/knowledge-db/knowledge_db/selector.py` | Modify | 嚴格化雙詞查詢首詞 `KIND_PREFIX_MAP` 判定 |
| `ys_codebase/source/knowledge-db/knowledge_db/config.py` | Modify | 處理 `jit_vector_timeout_ms` 與 `jit_vector_timeout_seconds` 互斥覆寫與非有限浮點數防禦 |
| `ys_codebase/source/knowledge-db/knowledge_db/schema.py` | Modify | `validate_space_weights` 攔截 `NaN` / `Inf` 與 `OverflowError` |
| `ys_codebase/source/knowledge-db/knowledge_db/io_utils.py` | Modify | `atomic_save_gzip_pickle` 實作 `finally` 區塊 `.tmp` 暫存檔清理 |
| `ys_codebase/source/knowledge-db/scripts/hook.ast.py` | Modify | 支援 `list` 型態貢獻與專案級 `config://knowledge-db/contribute.json` |
| `ys_codebase/source/knowledge-db/scripts/hook.core.py` | Modify | 委派至 `engine.pipeline.sync_incremental_changes` 統一增量同步邏輯 |
| `ys_codebase/source/knowledge-db/tests/test_service_worker.py` | Modify | 新增 C# `partial class` 閉包、多世代跳號、互讓悖論防禦、空閒 Worker JIT 同步、切片 `"src/*"` 防護與雙詞查詢回歸測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 向量檢索遮罩與全池早退 (`KDB-AUD-07`)**：在 `VectorIndex.search` 支援 `allowed_doc_ids`，並在 `HybridSearchEngine.search` 有過濾條件時於單次 `np.dot` 排序結果上流式過濾至 `fetch_limit` 早退，兼顧 100% 召回率與零矩陣拷貝。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/knowledge-db/knowledge_db/pipeline.py
class IndexingPipeline:
    def sync_incremental_changes(
        self,
        *,
        space_name: Optional[str] = None,
        target_spaces: Optional[List[str]] = None,
        auto_refresh: Optional[bool] = None,
        skip_vectors: bool = False,
        allow_parallel: bool = True,
        require_vectors: bool = False,
        verbose: bool = False,
        consume_fn: Optional[Callable[..., Any]] = None,
    ) -> Dict[str, Any]: ...
    def hot_patch_unified_index(
        self,
        diff_detail: ScanDiffDetail,
        full_files_map: Optional[Dict[str, Tuple[float, int]]] = None,
        timeout_seconds: Optional[float] = None,
        skip_vectors: bool = False,
    ) -> HotPatchResult: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `schema.validate_space_weights` 遇到 `float("nan")`、`float("inf")` 或無法轉為有限正浮點數之權重時拋出 `InvalidConfigError`。
- **階段決策紀錄**：[P03:DR-01] 對外公開檢索與建置 API 簽名維持 100% 向下相容（Mode B Public Compatibility）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-05 完整覆蓋 `KDB-AUD-01` ~ `KDB-AUD-14` 及 `ARCH-KDB-01` ~ `ARCH-KDB-11`（含手術 `S2`）。
- **邊界防護**：EC-01 ~ EC-04 皆已實作防禦並納入自動化回歸測試。
- **依賴純淨**：100% 符合 NFR-01 與 NFR-02。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/knowledge-db/README.md` | N/A | 公開 CLI 與檢索語法維持不變 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 更新 `pipeline.py`、`service.py`、`hybrid.py`、`retrieval.py`、`formatter.py` Docstrings（零審計單號殘留） |
| **發布日誌** | `changelog.md` | Modify | 記錄 `sub_03` 實作與驗證閉環摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_03` 規格定稿並完成實作與驗證。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `FR-01` 與 `FR-02`（`pipeline.py` 修復 C# `partial class` 兩階段 `dirty_keys` 閉包收集、多世代跳號防護、常駐空閒 Worker 增量同步與 `build_unified_index(force=False)` 短路，`KDB-AUD-01` ~ `KDB-AUD-04`）
- [x] **TASK-02**：實作 `FR-03`（`hook.ast.py` 支援 `list` 貢獻與專案級 `contribute.json`、`formatter.py:purify_lines` 忽略字串內 `"/*"`、`hybrid.py` 向量檢索預過濾與 `selector.py` 雙詞查詢保護，`KDB-AUD-05` ~ `KDB-AUD-07`）
- [x] **TASK-03**：實作 `FR-04`（`config.py`/`schema.py` 互斥鍵與 `isfinite` 校驗、`_clean_locked` 鎖與 `service.py` 狀態鍵對齊、`embedding.py` 空向量還原、`retrieval.py` BM25 完整排序截斷、`formatter.py` `.resolve()` 與 P3 優化，`KDB-AUD-08` ~ `KDB-AUD-14`）
- [x] **TASK-04**：實作 `FR-05` Mode A 手術 `S2`（解除 `service.py` / `pipeline.py` 互讓死鎖悖論、抽離 `IndexingPipeline.sync_incremental_changes` 收斂三處增量迴圈、`io_utils.py` `finally` `.tmp` 清理與 `retrieval.py` 聚合/計分優化，`ARCH-KDB-01` ~ `ARCH-KDB-11`）
- [x] **TASK-05**：補齊 `knowledge-db/tests/test_service_worker.py` 單元測試，同步至 `.modules/knowledge-db` 並重建建置/發布包，執行 `python3 yscb.py dev check` 與 `python3 yscb.py dev test --m knowledge-db` 驗證 100% 通過（116/116）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-04** | `Minor` | 為維持 Mode B 對既有單元測試（如 `test_service_worker.py` 與 `test_selector.py`）之 100% 向下相容性，保留 `wait_until_worker_idle`、`read_worker_state` 與 `SymbolSelector.find_matches` 公開入口，並透過 `flush_vector_index()` + `phase="yielded_to_foreground"` 及 `_ensure_indices_loaded` 髒向量保護根除互讓死鎖悖論。 | 已完整驗證 116 項測試 100% 通過 |
