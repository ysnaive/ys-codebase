# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：AST 與 Knowledge-DB 增量更新一致性與鎖競爭修復  
> 建立日期：2026-11-10  
> 所屬主計畫：2026_11_10_1425_cli_worker_resilience_and_incremental_index_fix  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `SpaceScanner.diff` 刪檔保全與 `GrammarProvisioner` 鎖修復 | `SpaceScanner.diff` 在 `config_hash` 變更時正確輸出新排除之 `deleted` 檔案；`GrammarProvisioner._provision_lock` 以 `timeout_sec=60.0` 正確互斥並持久化離線失敗負快取 | P0 | [P00:DR-01] |
| **FR-02** | `ASTEngine` 水合圖譜落盤、CoW 快照與快取指紋 | `get_workspace_graph` 水合後持久化至 `unified.graph.bin.gz`；`hot_patch_index` 採 CoW 替換 `_snapshot` 並擴大 `.ast_index.lock` 防撕裂；新增 `ast_config_hash` 失效、受限空間刪檔偵測與刪檔防模糊誤連 | P0 | [P00:DR-02] |
| **FR-03** | `Knowledge-DB` 向量內容雜湊追蹤與倒排世代一致性 | `VectorIndex` 記錄 `doc_text_hashes` 根治同行號改內文舊向量殘留並支援行號平移重用舊向量；`_align_index_symbols_with_ast_snapshot` 嚴格比對世代且 `InvertedIndex.patch_incremental` 精確清除舊詞與扣減舊長度 | P0 | [P00:DR-03] |
| **FR-04** | `Knowledge-DB` 鎖外推論、禮讓降級與規範路徑/組態隔離 | `reconfigure_model` 無變更免鎖返回且嚴守 `local_files_only=True`；ONNX 推論移出 `_index_lock`；`yielded_to_foreground` 有向量缺口時降級純 BM25；專案內絕對髒路徑正規化為相對路徑防跨空間誤刪；補齊 `kdb_config_hash` 與無鎖查詢快照參數 | P0 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 載入舊版無 `doc_text_hashes`、`ast_config_hash` 或 `kdb_config_hash` 之二進位快取檔 | 自動識別指紋缺失並平滑升級重算補齊，絕不拋出 `KeyError` 或反序列化崩潰 |
| **EC-02** | 多執行緒同時執行 `ast status --space` / `kdb search` 與背景增量熱修補 | CoW 快照與區域參數傳遞確保零 `RuntimeError: dictionary changed size` 與零空指標競態 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 增量效率與零洩漏 | 頂部插入空行平移未改函式時重用既有向量（0 次重算該函式 ONNX），獨立 CLI 第 2 次 `ast callers` 免重跑 4-Pass 全量連結，全測試 `0 ResourceWarning` |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `is_dirty_file_match` 在單元測試中涵蓋沙盒外合成絕對路徑匹配，因此須在 `bundle_dirty_files` 與 `_collect_all_dirty_files` 針對真實落於 `project_root` 內之絕對路徑先轉為專案相對路徑，兼顧跨模組隔離與合成路徑相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

打通 `core.space` 組態變更刪除信號 -> `ASTEngine` CoW 增量修補與 4-Pass 圖譜持久化 -> `Knowledge-DB` 基於內容雜湊之雙索引精準增刪與鎖外非阻塞檢索閉環。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/space/scanner.py` | Modify | 修正 `SpaceScanner.diff()` 於 `config_hash` 變更時保留刪除清單 |
| `ys_codebase/source/ast/ast_engine/provisioner.py` | Modify | 修正 `InterProcessLock.acquire` `timeout_sec` 參數與取鎖檢核、縮短 `pip` 逾時並持久化負快取 |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | `ASTSnapshot` 新增 `schema_version` 與 `config_hash` 序列化欄位 |
| `ys_codebase/source/ast/ast_engine/graph.py` | Modify | `CallGraphIndex.clone_shallow()` 支援增量修補 CoW 淺拷貝隔離 |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | `bundle_dirty_files` 將專案內絕對路徑收斂為專案相對路徑避免跨空間後綴污染 |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 水合 `workspace_graph` 落盤、CoW 快照更新、RMW `.ast_index.lock` 與雙檔世代校驗、`ast_config_hash` 失效、受限空間刪檔偵測與防模糊誤連 |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | `VectorIndex` 新增 `doc_text_hashes`、`reconfigure_model` 免鎖短路與嚴守 `local_files_only=True` |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `InvertedIndex` 新增 `config_hash` 欄位並以歷史 `doc_lengths` 精確扣減欄位長度 |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | `HybridSearchEngine.search()` 支援顯式傳入區域索引與權重快照，消除跨執行緒共享欄位無鎖突變 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 向量雜湊差集與行號平移重用、倒排世代校驗、鎖外 ONNX 推論、`yielded_to_foreground` 殘缺向量降級與 `kdb_config_hash` 失效 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `get_engine()` 依 `mtime_ns` 動態刷新 `contribute.json` 之 `space_weights` |
| `ys_codebase/source/core/tests/test_space.py` | Modify | 新增空間組態 `exclude` 變更時 `diff()` 正確回傳 `deleted` 檔案測試 |
| `ys_codebase/source/ast/tests/test_provisioner_and_jit.py` | Modify | 新增 `_provision_lock` 真實跨進程鎖阻塞驗證、水合圖譜落盤、`ast_config_hash` 失效與並發 CoW 測試 |
| `ys_codebase/source/knowledge-db/tests/test_self_healing.py` | Modify | 新增同行號改內文向量更新、行號平移向量重用、倒排舊詞清除與 `yielded_to_foreground` 降級測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 以 `(normalized_file_path, sym.name, sym.kind, text_hash)` 建立單檔舊向量暫存映射，使檔案上方增刪行造成行號位移但符號內文未變時直接零成本繼承舊特徵向量。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

- `ast_engine.graph.CallGraphIndex.clone_shallow(self) -> CallGraphIndex`
- `knowledge_db.retrieval.InvertedIndex.clone_shallow(self) -> InvertedIndex`
- `knowledge_db.embedding.VectorIndex.cloned_with_patch(self, removed_doc_ids: Set[str], new_doc_ids: List[str], new_vectors: Optional[np.ndarray], new_text_hashes: Optional[Dict[str, str]] = None) -> VectorIndex`
- `knowledge_db.embedding.compute_embedding_text_hash(text: str) -> str`
- `knowledge_db.embedding.VectorIndex.patch_incremental(self, removed_doc_ids: Set[str], new_doc_ids: List[str], new_vectors: Optional[np.ndarray] = None, new_text_hashes: Optional[Dict[str, str]] = None) -> None`
- `knowledge_db.hybrid.HybridSearchEngine.search(self, query: str, ..., inverted_index: Optional[InvertedIndex] = None, vector_index: Optional[VectorIndex] = None, space_weights: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]`
- **錯誤與例外契約 (Error & Exception Contracts)**：`.ast_index.lock` 或 `.kdb_index.lock` 取鎖失敗維持既有 `LockAcquisitionError` / 降級契約；舊版快取反序列化缺新欄位時自動以空預設值觸發平滑補齊。
- **階段決策紀錄**：[P03:DR-01] 所有擴充參數均為具預設值之選配參數，維持 100% 公開 SDK 相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-02 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：若同檔存在兩個同名同類型重載函式且內文完全一致，共享相同 `text_hash` 對應之單位向量在數學上完全等價，重用安全無損。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/ast/README.md` | Modify | 補充 `ast_config_hash` 自動快取失效與 4-Pass 圖譜水合持久化行為 |
| **專題手冊** | `docs/knowledge-db/incremental_hot_reload.md` | Modify | 對齊 `scripts/hook.core.py` 真實路徑、`400` 字元截斷常數、向量內容雜湊與前景禮讓降級機制 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記向量 `doc_text_hashes` 與行號位移零推論遷移設計筆記 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `core.space`、`ast` 與 `knowledge-db` 增量一致性修復摘要 |

- **決策定稿**：**[P04:DR-01]** 確認同步修正歷史漂移文檔常數與路徑。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：修復 `SpaceScanner.diff()` 組態變更刪檔保留與 `GrammarProvisioner._provision_lock()` 跨進程鎖及負快取持久化
- [x] **TASK-02**：實作 `ASTEngine` 水合 `workspace_graph` 落盤、CoW 快照替換、`.ast_index.lock` 交易擴展、`ast_config_hash` 失效與刪檔防模糊誤連
- [x] **TASK-03**：實作 `Knowledge-DB` `doc_text_hashes` 向量雜湊追蹤與行號平移重用、倒排世代對齊與舊詞/長度精確扣減
- [x] **TASK-04**：實作 `Knowledge-DB` `reconfigure_model` 免鎖短路、鎖外 ONNX 推論、`yielded_to_foreground` 降級、規範路徑收斂與 `HybridSearchEngine` 無鎖區域參數化，並補齊單元測試
- [x] **TASK-DOC**：同步更新 `docs/ast/`、`docs/knowledge-db/` 手冊與代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
