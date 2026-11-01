# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：knowledge-db 檢索精準度、拓撲消歧、Watcher 時序、空間權重與 C#/C++ 解析強化  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `SpaceDef.weight` 宣告式檢索權重與乘算 | `knowledge-db/contributes/_format.json` 的 `spaces` Schema 新增選填 `"weight": "float?"`（預設 `1.0`）；`SpaceDef` 保存 `weight` 並校驗 `weight > 0`；`HybridSearchEngine` 彙整檢索結果分數時乘以所屬 Space 的 `weight`；`agents-workflow/contributes/knowledge-db.json` 設定 `docs` `weight: 1.2`、`plans` `weight: 0.85`。 | P0 | [P00:DR-01] |
| **FR-02** | `TopologyLinker` 三處靜態消歧邏輯加固 | (1) `if prefix` 分支當型別未知時不再回退 `caller_class` 自綁定；(2) `len(candidates) == 1` 且帶有未知 `prefix` 時，僅在 `_score_candidates > 0` 或候選與呼叫端位於同檔案時才建立呼叫邊；(3) `_score_candidates` 的變數名子字串匹配強制要求 `len(prefix_tail) >= 3`。 | P0 | [P00:DR-02] |
| **FR-03** | `.watcher_active` 寫入時序、異常清理與 `.watcher_dirty` 檢核 | (1) `service.py` 將 `.watcher_active` 寫入移至 `observer.start()` 成功啟動之後；(2) 被動模式 `except Exception:` 分支清理殘留之 `.watcher_active`；(3) `pipeline.py` 的 `_is_watcher_active` 若發現 `.watcher_dirty` 存在則返回 `False`，觸發前台增量同步。 | P0 | 核心目標 2 |
| **FR-04** | 多語言 AST `visibility` 修飾詞解析與 C# `partial class` 跨檔聚合 | (1) `parsers/treesitter.py` 針對 C#、C++、Java、TS 等具顯式存取修飾詞語言從 AST 節點提取 `public`/`private`/`protected`/`internal` 決定 `visibility`（C# 類別成員預設 `private`、頂層型別預設 `internal`），僅對 Python/JS 回退底線 `_` 規則；(2) 同 Space 與同 Namespace 下之 C# `partial class` 跨檔案符號與成員能正確聚合與解析呼叫關係。 | P0 | [P00:DR-03] |
| **FR-05** | 未安裝 `agents-workflow` 時隱藏 Agent 專屬提示 | `knowledge-db` CLI (`scripts/cli.py` 或格式化輸出) 輸出截斷提示或尾端導引時，檢查 `module://agents-workflow` 是否已安裝；若未安裝則省略專供 AI Agent 閱讀之工作流提示文字。 | P0 | 核心目標 5 |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `SpaceDef` 配置 `weight <= 0` 或非數值 | 於 `SpaceDef` 解析時拋出明確 `ValueError` 或回退預設值 `1.0` 並告警，防止負分或零分破壞排序。 |
| **EC-02** | 單一字母或兩字母變數（如 `e.Save()`、`s.Run()`）且無明確型別宣告 | `len(prefix_tail) < 3` 不觸發子字串啟發式加分，且若候選不在同檔案則不建立跨模組幽靈呼叫邊。 |
| **EC-03** | `observer.start()` 拋出例外或被動模式中途崩潰 | `.watcher_active` 不會提前殘留，或在 `except` 分支被安全移除 (`unlink(missing_ok=True)`)，前台後續呼叫不會誤判 Watcher 存活而跳過同步。 |
| **EC-04** | C# 跨多檔宣告 `partial class Foo` 且各自包含欄位與方法 | 各分片檔的方法可解析定義於另一分片檔的成員與方法呼叫，不會因跨檔拆分而遺失類別成員歸屬。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 相容性與效能 | 不引入新第三方套件；既有 `knowledge-db` 測試集 100% 通過，且 `contributes check` 與 `dev check knowledge-db` 零錯誤。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `[DN-04]` 規定背景 Watcher 異常時透過 `.watcher_dirty` 標記通知前台，前台 `pipeline._is_watcher_active` 必須檢查 `.watcher_dirty` 以確保自癒閉環。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[contributes/_format.json & agents-workflow/contributes/knowledge-db.json]
       │ (weight: float?)
       ▼
[space.py: SpaceDef] ──► [hybrid.py: HybridSearchEngine] (score *= space.weight)

[parsers/treesitter.py & queries/c_sharp.scm]
       │ (AST modifiers -> visibility; partial class aggregation)
       ▼
[linker.py: TopologyLinker] (strict prefix disambiguation & partial class member merging)

[service.py: Watcher] ──(.watcher_active after start / cleanup on error / .watcher_dirty)──► [pipeline.py: _is_watcher_active]

[scripts/cli.py] ──(check module://agents-workflow installed)──► Conditional Agent Hints
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/contributes/_format.json` | Modify | 於 `SpaceDef` Schema 定義新增 `"weight": "float?"` |
| `ys_codebase/source/agents-workflow/contributes/knowledge-db.json` | Modify | 為 `docs` 設定 `"weight": 1.2`、為 `plans` 設定 `"weight": 0.85` |
| `ys_codebase/source/knowledge-db/knowledge_db/schema.py` | Modify | `SpaceConfig` (`SpaceDef` 別名) 新增 `weight: float = 1.0` 屬性與 `weight > 0` 剛性校驗 |
| `ys_codebase/source/knowledge-db/knowledge_db/space.py` | Modify | 導出 `SpaceDef` 別名並支援空間權重組態聚合 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | `status()` 輸出空間詳情補充 `weight` 欄位 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | `QueryFilter` 新增 `space_weights`，`BM25Engine._score_candidate_documents` 支援空間權重乘算，`InvertedIndex.build` 整合 C# partial 符號聚合 |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | `HybridSearchEngine` 支援 `space_weights` 並對 RRF / BM25 候選分數乘算所屬 Space 權重 |
| `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` | Modify | 新增 `aggregate_partial_symbols()` 跨檔案合併同 Space、同 FQN 之 C# `partial class` 成員、基底型別與欄位型別 |
| `ys_codebase/source/knowledge-db/knowledge_db/linker.py` | Modify | 移除 `if prefix` 對 `caller_class` 的錯誤回退、加固 `len(candidates) == 1` 門檻、`len(prefix_tail) >= 3` 及欄位型別消歧 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 將 `.watcher_active` 寫入移至 `self._observer.start()` 成功啟動之後並強化異常分支清理 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | `_is_watcher_active` 新增 `.watcher_dirty` 存在性檢核；檢索準備階段自動載入 `space_weights` |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py` | Modify | 多語言 AST 存取修飾詞 `_extract_visibility` 解析與 C# `partial` / `field_types` 萃取 |
| `ys_codebase/source/knowledge-db/assets/queries/c_sharp.scm` | Modify | 補充 C# `field_declaration` 節點與型別捕獲支援 |
| `ys_codebase/source/knowledge-db/knowledge_db/config.py` | Modify | 新增 `is_agents_workflow_installed()` 探針函式 |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 僅於 `is_agents_workflow_installed()` 為真時輸出 AI Agent `[GUARD]` 提示 |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | `_cap_json_snippet` 檢測 `is_agents_workflow_installed()` 決定是否輸出 Agent 工具提示 |
| `ys_codebase/source/knowledge-db/tests/{test_space,test_retrieval,test_service_worker,test_graph,test_parsers,test_cli}.py` | Modify | 新增涵蓋 `TODO-04`, `TODO-08`, `TODO-09`, `TODO-14`, `TODO-15` 之單元與邊界測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** **Space 權重乘算點**：於 `HybridSearchEngine.search` 計算完 RRF / 混合分數後，依結果所屬 `space` 乘上 `space_def.weight` 再執行最終全域排序，確保跨 Space 排序直接反映宣告權重。
- **[P02:DR-02]** **C# `partial class` 跨檔聚合機制**：在 `TreeSitterParser` 解析出類別限定名（含 namespace）與 `TopologyLinker` 建立類別成員映射時，對同 Space 同限定名之類別節點合併成員與方法映射，使跨檔案的 `this.Method()` 或欄位型別推導無縫連通。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# space.py
@dataclass(frozen=True)
class SpaceDef:
    name: str
    path: str
    description: str = ""
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    weight: float = 1.0

# linker.py
class TopologyLinker:
    def _score_candidates(
        self,
        candidates: list[dict[str, Any]],
        caller_file: str,
        caller_space: str,
        imported_symbols: set[str],
        prefix: str | None = None,
    ) -> list[tuple[int, dict[str, Any]]]: ...

# pipeline.py
class IndexingPipeline:
    def _is_watcher_active(self) -> bool: ...

# parsers/treesitter.py
class TreeSitterParser:
    def _extract_visibility(self, node: Any, name: str, lang: str) -> str: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `SpaceDef` 若接收到 `weight <= 0` 拋出 `ValueError("Space weight must be positive")`。
  - `service.py` Watcher 啟動或運行失敗時安全移除 `.watcher_active`，不向上洩漏未處理之檔案系統例外。
- **階段決策紀錄**：`[P03:DR-01]` 維持所有既有公開 CLI 與 Python API 簽名向後相容，`SpaceDef.weight` 具預設值 `1.0`。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：若無 `prefix` 的同名方法呼叫（如裸呼叫 ` helper()`）且全專案僅有 1 個候選，是否仍能正常連線？*
  - *答*：是。`len(candidates) == 1` 的嚴格門檻僅針對「帶有明確接收者 `prefix`（非 `self`/`this`/`cls`/`super`）卻無法解析出 `target_class`」的情境，避免 `unknown_obj.Save()` 誤連至毫不相干的唯一 `Save` 方法；無 `prefix` 的函式呼叫維持既有連線行為。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | N/A | 由 Umbrella 主計畫或 Phase 7 統一檢視 |
| **專題手冊** | `docs/knowledge-db/architecture.md` | N/A | 由 Phase 7 統一同步 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | N/A | 對齊既有 `[DN-04]` 契約 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `space.py`, `linker.py`, `pipeline.py`, `treesitter.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | N/A | 於 Phase 7 結案時更新 |

- **決策定稿**：**[P04:DR-01]** 確認修改邊界嚴格限制於 `ys_codebase/source/knowledge-db/` 與 `ys_codebase/source/agents-workflow/contributes/knowledge-db.json`。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `TODO-14` (`contributes/_format.json`, `schema.py`, `space.py`, `retrieval.py`, `hybrid.py`, `pipeline.py`, `agents-workflow/contributes/knowledge-db.json` Space 檢索權重支援)
- [x] **TASK-02**：實作 `TODO-08` (`linker.py` 三處靜態消歧邏輯漏洞修復)
- [x] **TASK-03**：實作 `TODO-09` (`service.py` `.watcher_active` 時序與清理、`pipeline.py` `.watcher_dirty` 檢核)
- [x] **TASK-04**：實作 `TODO-15` (`parsers/treesitter.py`, `assets/queries/c_sharp.scm`, `bundler.py`, `linker.py` C#/C++/TS AST `visibility` 解析與 C# `partial class` 跨檔聚合)
- [x] **TASK-05**：實作 `TODO-04` (`config.py`, `embedding.py`, `scripts/cli.py` 未安裝 `agents-workflow` 時隱藏 Agent 專屬提示)
- [x] **TASK-06**：編寫與執行單元測試，並通過 `contributes check`、`dev check knowledge-db`、`dev test knowledge-db` 與 `install knowledge-db@build --force`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
