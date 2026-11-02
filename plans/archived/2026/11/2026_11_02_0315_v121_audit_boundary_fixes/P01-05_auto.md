# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：YS-Codebase v1.2.1 二輪審計 5 項邊界條件與相容性隱患修復  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0315_v121_audit_boundary_fixes  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `LEGACY_PROVIDER_URLS` 補齊舊倉庫名 `ysnaive/agent.workflow` | 於 `yscb.py` 與 `core/engine.py` 將 `https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release`（含尾部 `/` 變體）納入 `LEGACY_PROVIDER_URLS`，使 `normalize_legacy_provider_url()` 與 `AtomicEngine._get_config()` 自動將其正規化為 `DEFAULT_PROVIDER_URL` | P0 | [P00:DR-01] |
| **FR-02** | C# `partial class` 消除 $N^2$ 倒排索引膨脹與 `patch_incremental` 增量重聚合 | `aggregate_partial_symbols` 保留各分部自身原始定義之 `own_members` / `own_base_types` / `own_field_types`，`InvertedIndex` 對每個分部符號僅索引其自身定義之成員（消除 $N$ 個分部重複索引全量成員之 $N^2$ 膨脹），同時於 `InvertedIndex.patch_incremental` 自動重聚合受影響之同 FQN C# 分部符號群組 | P0 | [P00:DR-02] |
| **FR-03** | `PlanScanner.build_recovery_capsule` 精確提取 `§2.2` 異動檔案 | 掃描 `P02`（含 `P{XX}-05_auto.md`）提取 `impacted_files` 時，遇到 `## 3.` 或 `## 4.` 章節即停止掃描，並過濾無路徑特徵（不含 `/` 與 `.`）或粗體維度名稱（如 `**模組手冊**`） | P0 | [P00:DR-03] |
| **FR-04** | `PlanVerifier` 支援 `P{XX}-05_auto.md` 單檔合併模式之 `BACKPROP` 檢核 | 當 `p05_path` 記載 `Major` 或 `Critical` 偏差且處於單檔模式（`p02_path == p05_path`）時，檢查偏差列處置欄是否明確標註已回寫（如 `§2`/`§3`/`P02`/`P03`/`已回寫`/`已同步`）或 `changelog.md` 是否已記錄 `REVISION`，若無則發出 `BACKPROP` Warning | P0 | [P00:DR-03] |
| **FR-05** | `compiler.py` 獨立行內代碼塊根路徑 `` `__${project://}__` `` 防空反引號保護 | `_replace_in_code_span` 在無 `anchor` 且 `_resolve_project_uri_tag` 回傳空字串 `""` 時，回退渲染為 `` `./` `` 而非空雙反引號 `` `` `` | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | C# `partial class` 其中一個分部檔於 `patch_incremental` 被修改（新增/修改欄位或方法），而主分部檔未修改 | 存量主分部檔與被修改分部檔於 `patch_incremental` 共同重新聚合，雙向保留主分部檔之 `base_types`/`field_types` 與新分部檔之最新成員 |
| **EC-02** | `P01-05_auto.md` 之 `§2.2` 異動檔案少於 8 個且下方 `§4.2` 存在 `Modify` 列 | `build_recovery_capsule` 於進入 `## 3.` 時即停止，絕不將 `§4.2` 的維度名稱混入 `impacted_files` |
| **EC-03** | `P01-05_auto.md` 之 `§5.2` 登記 `Major` 偏差且已在處置欄註明「已回寫 §2.2 與 §3.1」 | `PlanVerifier` 識別已回寫標記，合法放行不誤報 `BACKPROP` Warning |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 索引複雜度與體積 | $N$ 個分部檔組成的 C# `partial class`，其單一方法名在 `InvertedIndex.index[term]` 中僅產生 1 筆對應該類別分部的 Posting（而非 $N$ 筆重複 Posting） |
| **NFR-02** | 零回歸與相容性 | `core`、`knowledge-db`、`agents-workflow` 全量單元與邊界測試 100% 通過 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 在 `InvertedIndex.patch_incremental` 重新聚合存量分部符號時，必須先將受影響存量分部符號的舊 Posting 與 `field_total_lengths` 從倒排表中乾淨扣除，再以各分部之原始 `own_members` / `own_base_types` / `own_field_types` 為基底重新聚合並呼叫 `add_symbol`，防止殘留舊欄位或重複累加詞頻。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
1. [core / yscb.py] LEGACY_PROVIDER_URLS (4 variants) -> normalize_legacy_provider_url() -> DEFAULT_PROVIDER_URL
2. [knowledge-db] aggregate_partial_symbols()
     ├── Preserve metadata["_own_members" / "_own_base_types" / "_own_field_types"]
     ├── sym.members & sym.children = tuple(merged_members) (for TopologyLinker & binary serialization)
     ├── InvertedIndex._extract_symbol_members_text() -> indexes _own_members (1x indexing without N^2 bloat)
     └── InvertedIndex.patch_incremental() -> regroup affected C# partial symbols -> re-aggregate & re-index
3. [agents-workflow]
     ├── PlanScanner.build_recovery_capsule() -> section-bounded table extraction (§2 only)
     ├── PlanVerifier._verify_full_track()    -> single-file P{XX}-05_auto.md BACKPROP check
     └── compiler._replace_in_code_span()     -> f"`{resolved or './'}`"
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 於 `LEGACY_PROVIDER_URLS` 補入 `ysnaive/agent.workflow` 舊倉庫網址變體 |
| `ys_codebase/source/core/core/engine.py` | Modify | 於 `LEGACY_PROVIDER_URLS` 補入 `ysnaive/agent.workflow` 舊倉庫網址變體 |
| `ys_codebase/source/core/tests/test_installer.py` | Modify | 擴充舊倉庫名 `ysnaive/agent.workflow` 正規化與遷移測試斷言 |
| `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` | Modify | 於 `aggregate_partial_symbols` 保存 `_own_*` 原始分部屬性並提供 `restore_unaggregated_partial_symbol` |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | 新增 `_extract_symbol_members_text` 消除 $N^2$ 倒排膨脹，並於 `InvertedIndex.patch_incremental` 支援同 FQN C# 分部符號群組之局部重聚合 |
| `ys_codebase/source/knowledge-db/tests/test_graph.py` | Modify | 新增 C# `partial class` 增量 `patch_incremental` 保活與無 $N^2$ 重複倒排 Posting 測試 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py` | Modify | 限制 `build_recovery_capsule` 於 `## 3.` 前提取異動檔案並過濾非路徑維度名稱 |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Modify | 擴充 `BACKPROP` 檢核支援單檔 `P{XX}-05_auto.md` 模式 |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | 修正 `_replace_in_code_span` 對空字串根路徑回退渲染為 `` `./` `` |
| `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Modify | 新增 `` `__${project://}__` `` 根路徑渲染為 `` `./` `` 測試 |
| `ys_codebase/source/agents-workflow/tests/test_plans_toolchain.py` | Modify | 新增 `build_recovery_capsule` 排除 `§4.2` 與單檔 `BACKPROP` 檢核測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 在 `UnifiedSymbol` 中，`sym.members` 與 `sym.children` 維持跨分部合併後的 `tuple(merged_members)`（確保 `UnifiedSymbol.to_dict()` / `from_dict()` 二進位快取反序列化與 `TopologyLinker` 成員完整無損），而於 `sym.metadata` 保存 `_own_members`、`_own_base_types`、`_own_field_types`，由 `InvertedIndex._extract_symbol_members_text()` 優先讀取 `_own_members` 建立倒排詞頻（徹底消除 $N^2$ 重複索引），並供 `patch_incremental` 熱修補時透過 `restore_unaggregated_partial_symbol` 無損還原單檔原始狀態再重聚合。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/engine.py & yscb.py
LEGACY_PROVIDER_URLS: Tuple[str, ...] = (
    "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release",
    "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release/",
    "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release",
    "https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release/",
)

# ys_codebase/source/knowledge-db/knowledge_db/bundler.py
def aggregate_partial_symbols(symbols: List[UnifiedSymbol]) -> List[UnifiedSymbol]: ...

# ys_codebase/source/knowledge-db/knowledge_db/retrieval.py
class InvertedIndex:
    def patch_incremental(
        self,
        dirty_file_paths: Set[str],
        new_symbols: List[UnifiedSymbol],
        tokenizer: Optional[MultilingualTokenizer] = None,
    ) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：所有公開方法簽名與例外型別維持 100% 向後相容。
- **階段決策紀錄**：`[P03:DR-01]` 零公開 API 簽名破壞，純內部邊界行為加固。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-03 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若某個 `partial class` 原本有 2 個分部檔（FileA 與 FileB），在 `patch_incremental` 時 FileB 被刪除（或不再包含該類別），僅剩 FileA 1 個分部檔時，`aggregate_partial_symbols` 因 `len(indices) <= 1` 跳過，FileA 會不會殘留已被刪除之 FileB 的成員與欄位？*
  - *答*：在 `patch_incremental` 撈出受影響存量分部符號（如 FileA）時，**先利用其 `metadata` 中保存的 `_own_members`、`_own_base_types`、`_own_field_types`、`_own_docstring` 將 FileA 還原為純單檔狀態**，再送入 `aggregate_partial_symbols`。如此就算只剩 FileA 單一檔案，也能乾淨退回 FileA 自身定義，絕不殘留 FileB 的幽靈成員！

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | N/A | 無 CLI 語法變更 |
| **專題手冊** | `docs/knowledge-db/README.md` | N/A | 無架構拓撲變更 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | N/A | 無新增反直覺妥協 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `aggregate_partial_symbols` 與 `patch_incremental` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本計畫 5 項邊界隱患修復摘要 |

- **決策定稿**：**[P04:DR-01]** 確認透過 `_restore_unaggregated_partial_symbol` 先還原存量分部符號再重聚合，根除分部刪減時之幽靈殘留。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `yscb.py` 與 `ys_codebase/source/core/core/engine.py` 之 `LEGACY_PROVIDER_URLS` 並補充 `core` 單元測試（`FR-01`）
- [x] **TASK-02**：重構 `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` 與 `retrieval.py` 實現 C# `partial class` 零 $N^2$ 倒排索引與 `patch_incremental` 增量重聚合，並補充 `knowledge-db` 測試（`FR-02`, `EC-01`, `NFR-01`）
- [x] **TASK-03**：更新 `ys_codebase/source/agents-workflow/agents_workflow/{plans/scanner.py,plans/verifier.py,compiler.py}` 修復 `build_recovery_capsule`、`BACKPROP` 單檔模式與根路徑 `` `./` `` 渲染，並補充 `agents-workflow` 測試（`FR-03` ~ `FR-05`, `EC-02` ~ `EC-03`）
- [x] **TASK-DOC**：更新相關源碼 Docstrings 與驗證三模組 `dev check` / `dev test` 100% 通過

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
