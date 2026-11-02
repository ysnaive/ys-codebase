# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：全生態系指紋快取與熱自癒機制完善度審視與修復  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `knowledge-db` Stage 1 舊向量剔除自癒 (`[F-01]`) | 於 `hot_patch_unified_index(..., skip_vectors=True)` 中，當 `old_doc_ids` 非空且向量索引檔存在時，主動從 `VectorIndex` 移除 `old_doc_ids` 並儲存，確保起始行號未變但內容已修改之符號在 Stage 2 能被 `sym_ids - vec_ids` 差集自動補齊新向量，且不變動 `UnifiedSymbol.compute_id`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-02** | `knowledge-db` 局部熱修補精確路徑正規化 (`[F-05]`) | 於 `bundler.py` 將空間 `dirty_files` 結合空間 `include` 根目錄正規化為 `project://` 相對路徑，並移除 `io_utils.is_dirty_file_match` 中無 `/` 時僅比對 `sym_filename == p` 的寬鬆條件，避免單一空間頂層檔案（如 `README.md`、`__init__.py`）變更時誤判其他空間同名檔案。 | P0 | [P00:DR-02] |
| **FR-03** | `file-space` 全空間精確世代 Ack 與 `watch=False` 自癒 (`[F-02]`) | `ScanDiffResult` 增設 `space_generations: Dict[str, int] = field(default_factory=dict)`，於 `_diff_all_spaces` 記錄各子空間當下 `to_generation`，並由 `consume_diff(None)` / `ack(None)` 精確寫入各子空間水位；且對 `not cfg.watch` 之空間即使 `is_watcher_active()` 為真仍允許 `auto_refresh=True`。 | P0 | [P00:DR-03] |
| **FR-04** | `file-space` `CursorStore` 多執行緒 RMW 鎖保護 (`[F-07]`) | 於 `CursorStore` 引入進程內 `threading.RLock()`，保護 `set_cursor` 與 `reset_cursor` 的 Read-Modify-Write 區段，杜絕多執行緒同時更新同一 consumer 不同 space 時互相覆蓋。 | P1 | [P00:DR-03] |
| **FR-05** | `core.uri` 重入安全 JIT 髒檢查與 Contributes 追蹤補齊 (`[F-03]`, `[F-06]`) | `core/uri.py` `_get_merged_uri_schemes()` 在具備重入保護旗標（Reentrancy Guard）下查驗 `contributes._is_contributes_dirty()` 並在髒時自動觸發 `contributes.get("core", "uri_schemes")`；`core/contributes.py` `_scan_contributes_inputs()` 補齊追蹤 `module.source://<donor>/contributes/_format.json` 與 `config://core/contribute.json` 宣告之專案級語系實體檔。 | P0 | [P00:DR-04] |
| **FR-06** | `agents-workflow` 目錄 SHA-1 快取複用與 Stage 0 指紋/區塊校驗 (`[F-04]`) | `ReleasePublisher._get_source_file_sha1` 對目錄走訪時逐檔複用 `self._sha1_cache` (`mtime_ns`, `size`)；`compute_source_fingerprint()` 納入 `core.locale.get_active_chain()` 與 `config://core` 關鍵摘要；`_check_short_circuit()` 確認 `agent_rules` 目標檔內存在 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 標記。 | P1 | [P00:DR-05] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `_get_merged_uri_schemes()` 呼叫 `_is_contributes_dirty()` 時內部再次呼叫 `uri.resolve("cache://...")` | 重入保護旗標生效，重入期間 `_get_merged_uri_schemes()` 立即回傳 `{}`，使 `uri.resolve()` 安全退回 `_BOOTSTRAP_FALLBACK_SCHEMES`，絕不發生 `RecursionError`。 |
| **EC-02** | Stage 1 索引期間背景 Watcher 刷新了某子空間的新快照 (`gen + 1`) | `ack(None, space_generations=...)` 僅將各子空間 Cursor 推進至本次 `diff` 實際讀取的世代，保留 `gen + 1` 於下次增量同步消費，不發生 Lost Update。 |
| **EC-03** | 使用者手動誤刪根目錄 `AGENTS.md` 內的 `<!-- YSCB_AGENTS_BEGIN -->` 託管區塊但檔案仍存在 | `_check_short_circuit()` 偵測到託管標記缺失，回傳 `False` 觸發三階段重編譯與自癒覆寫。 |
| **EC-04** | 修改某空間頂層 `README.md`（相對該空間根目錄無 `/`） | `is_dirty_file_match` 透過正規化後的 `project://` 相對路徑精確匹配，不會誤將其他模組下的 `README.md` 標記為 dirty 或剔除符號。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / I/O | `agents-workflow` 目錄 SHA-1 快取命中時免除重讀 Skill 目錄檔案內容（0 額外檔案內容讀取 I/O）。 |
| **NFR-02** | 相容性 | 100% 保持既有 Public API、YFP2 二進位快照格式與 `UnifiedSymbol.compute_id` 雜湊不變。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** `core/uri.py` 與 `core/contributes.py` 存在雙向呼叫鏈：`_is_contributes_dirty()` 會解析 `cache://`、`module://` 與 `config://` URI，故 `uri.py` 觸發 Contributes 髒檢查時必須使用 Thread-Local 重入守衛退回 `_BOOTSTRAP_FALLBACK_SCHEMES`。
- **`[!NOTE]`** `knowledge-db` 的呼叫圖譜 (`pipeline.py:490-528`) 仰賴 `UnifiedSymbol.compute_id` 在函式內容修改但起始行號不變時維持相同 ID 以追蹤 `old_callee_id`，因此嚴禁將函式內容 hash 混入 `compute_id`，而應於 Stage 1 剔除 `vector_index` 舊符號向量。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[core]
  uri._get_merged_uri_schemes() --(Reentrancy Guard)--> contributes._is_contributes_dirty()
  contributes._scan_contributes_inputs() -------------> 納入 module.source:// _format.json & config://core 語系檔

[file-space]
  scanner._diff_all_spaces() ----(記錄 space_generations & watch=False auto_refresh)---> ScanDiffResult
  scanner.consume_diff(None) ----> ack(None, space_generations=...) ---(RLock)---> CursorStore.set_cursor()

[knowledge-db]
  bundler.bundle_dirty_files() --(include root -> project relpath)--> pipeline.hot_patch_unified_index()
  pipeline.hot_patch_unified_index(skip_vectors=True) --(evict old_doc_ids)--> VectorIndex -> Stage 2 Deficit Sync

[agents-workflow]
  publisher._get_source_file_sha1(dir) --(mtime_ns, size)--> _sha1_cache
  publisher.compute_source_fingerprint() ------------------> + locale.get_active_chain() + config://core
  publisher._check_short_circuit() ------------------------> 校驗 AGENTS.md 託管區塊標記
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/uri.py` | Modify | 於 `_get_merged_uri_schemes()` 加入 Thread-Local 重入保護與 Contributes JIT 髒檢查自癒 |
| `ys_codebase/source/core/core/contributes.py` | Modify | 於 `_scan_contributes_inputs()` 補齊 `module.source://` `_format.json` 與專案級語系實體檔追蹤 |
| `ys_codebase/source/core/tests/test_contributes.py` | Modify | 新增 URI schemes JIT 自癒無遞迴與 `_format.json`/專案語系檔髒檢查單元測試 |
| `ys_codebase/source/file-space/file_space/schema.py` | Modify | 於 `ScanDiffResult` 正式定義 `space_generations: Dict[str, int]` 欄位、建構子參數與 `to_dict()` 序列化 |
| `ys_codebase/source/file-space/file_space/scanner.py` | Modify | `_diff_all_spaces` 填充 `space_generations`、`ack(None)` 支援精確世代映射、`watch=False` 空間允許 `auto_refresh`、`CursorStore` 加入 `threading.RLock()` |
| `ys_codebase/source/file-space/tests/test_fingerprint_scanner.py` | Modify | 新增 `ack(None)` 跨世代防 Lost Update、`watch=False` 自動刷新與 `CursorStore` 併發安全測試 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | `hot_patch_unified_index(skip_vectors=True)` 主動從 `vector_index` 剔除 `old_doc_ids` 並儲存 |
| `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` | Modify | 將 `dirty_files` 結合空間 `include` 根目錄正規化為 `project://` 相對路徑 |
| `ys_codebase/source/knowledge-db/knowledge_db/io_utils.py` | Modify | 移除 `is_dirty_file_match` 中無 `/` 時單純比對 `sym_filename == p` 的寬鬆條件 |
| `ys_codebase/source/knowledge-db/tests/test_self_healing.py` | Modify | 新增符號行號不變修改之 Stage 1 向量剔除與同名頂層檔案（如 `README.md`）跨空間隔離測試 |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 目錄 SHA-1 逐檔複用 `_sha1_cache`、`compute_source_fingerprint` 納入語系鏈與 `config://core`、`_check_short_circuit` 校驗 `AGENTS.md` 託管區塊標記 |
| `ys_codebase/source/agents-workflow/tests/test_publisher_self_healing.py` | New | 新增目錄 SHA-1 快取命中、語系變更指紋失效與 `AGENTS.md` 託管區塊損壞自癒測試 |
| `docs/file-space/README.md` | Modify | 補充 `ScanDiffResult.space_generations` 與 `watch=False` 空間 JIT 刷新說明 |
| `CHANGELOG.md` | Modify | 記錄 `sub_06` 四大模組指紋與熱自癒邊界修復摘要 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 採 Stage 1 剔除 `vector_index` 舊符號 ID 取代變更 `UnifiedSymbol.compute_id`，兼顧 Stage 2 向量差集自癒與呼叫圖譜跨版本 ID 穩定性。
- **[P02:DR-02]** 於 `core/uri.py` 使用 `threading.local()` 重入旗標保護 `_get_merged_uri_schemes()`，確保在重入期間零開銷退回 `_BOOTSTRAP_FALLBACK_SCHEMES`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/file-space/file_space/scanner.py
@dataclass
class ScanDiffResult:
    space_name: Optional[str]
    from_generation: int
    to_generation: int
    added: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    unchanged_count: int = 0
    merkle_root: str = ""
    space_generations: Dict[str, int] = field(default_factory=dict)

class FingerprintScanner:
    def ack(
        self,
        space_name: Optional[str] = None,
        consumer: str = "default",
        generation: Optional[int] = None,
        space_generations: Optional[Dict[str, int]] = None,
    ) -> int: ...

# ys_codebase/source/knowledge-db/knowledge_db/io_utils.py
def is_dirty_file_match(sym_file_path: str, norm_dirty: Set[str]) -> bool: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `uri._get_merged_uri_schemes()` 若在觸發 `contributes` 髒檢查時遭遇任何 I/O 或初始化期異常，靜默捕獲並退回既有快取或 `{}`，絕不阻斷基礎 URI 解析。
  - `hot_patch_unified_index(skip_vectors=True)` 剔除 `old_doc_ids` 時若向量索引檔尚未建立，安全跳過不拋出例外。
- **階段決策紀錄**：`[P03:DR-01]` `FingerprintScanner.ack` 新增選填參數 `space_generations: Optional[Dict[str, int]] = None`，100% 向後相容既有呼叫端。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-06 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束，零新增第三方依賴
- **靈魂拷問與防護解法**：
  - *問：若 `AGENTS.md` 被配置為 `mode: "copy"` 而非 `"inject"`，檢查 `<!-- YSCB_AGENTS_BEGIN -->` 是否會導致永遠不短路？*
  - *答*：於 `_check_short_circuit()` 檢查 `ar.get("mode", "inject") == "inject"` 時才驗證託管區塊標記（或比對 `ar.get("marker", "YSCB_AGENTS")` 對應之 `<!-- {marker}_BEGIN -->` 與 `<!-- {marker}_END -->`），若為 `copy` 模式則僅檢查檔案存在與非空。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/file-space/README.md` | Modify | 補充 `ScanDiffResult.space_generations` 與 `watch=False` 空間 JIT 刷新行為 |
| **專題手冊** | `docs/core/contributes_architecture.md` | N/A | 既有架構描述已涵蓋，無須變更結構 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | N/A | 屬既有雙階自癒契約之邊界修補 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `scanner.py`、`pipeline.py`、`io_utils.py`、`uri.py`、`publisher.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本計畫跨模組指紋與熱自癒修復摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `P01-05_auto.md` 規格鎖定，進入 Pre-Code Analyze Gate 與分區實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core` (`uri.py` 重入安全 JIT 髒檢查、`contributes.py` `_format.json` 與專案語系檔追蹤) 與 `agents-workflow` (`publisher.py` 目錄 SHA-1 快取複用、語系/組態指紋與 `AGENTS.md` 標記校驗) 修復與單元測試
- [x] **TASK-02**：實作 `file-space` (`scanner.py` `space_generations` 精確 Ack、`watch=False` 自動刷新、`CursorStore` `RLock`) 與 `knowledge-db` (`pipeline.py` Stage 1 剔除舊向量、`bundler.py` & `io_utils.py` 精確路徑正規化) 修復與單元測試
- [x] **TASK-DOC**：同步更新 `docs/file-space/README.md`、`CHANGELOG.md` 與源碼 Docstrings，並部署 `@build` 驗證

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

