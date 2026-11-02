# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`knowledge-db` 空間與指紋底座遷移重構（`/code-optimizer` `Mode A` 單一正統入口收斂）  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0339_module_space_feasibility_research / sub_02_knowledge_db_space_migration  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `Mode A` 物理刪除重複底座與正統入口收斂 | 物理刪除 `knowledge_db/space.py`、`knowledge_db/scanner.py`、`knowledge_db/service.py`、`contributes/server.json` 與 `tests/test_scanner.py`；自 `knowledge_db/__init__.py`、`exceptions.py`、`schema.py` 移除舊空間/掃描符號與重複異常，全模組與測試統一改為 `from space import ...` 單一正統入口（零薄轉發包裝層）。 | P0 | [P00:DR-01] |
| **FR-02** | 儲存根 (`storage_dir`) 解耦與 `space_weights` 組態純化 | `KnowledgeEngine.__init__` 將 `self.storage_dir` 獨立解析至 `knowledge.storage://`（`cache://knowledge-db/`），與 `space_manager.storage_dir`（`cache://space/`）徹底分離；`contributes/_format.json` 與 `schema.py` 將 `spaces` 幾何定義替換為 `"space_weights": Dict[str, float]`；新增 `ys_codebase/config/space/contribute.json` 與 `ys_codebase/source/agents-workflow/contributes/space.json` 承接空間幾何宣告。 | P0 | [P00:DR-01] |
| **FR-03** | 游標增量消費 (`consume_diff`) 與 `hook.space.py` 事件驅動熱修補 | `SearchPipeline._ensure_jit_index_ready_locked` 廢除私有 `unified.meta.bin` 與 `.watcher_*` 標記檔，改用 `space.consume_diff(consumer_id="knowledge-db")` 驅動 JIT 增量熱修補；新增 `scripts/hook.space.py` 訂閱 `on_space_changed` 事件執行背景熱更新。 | P0 | [P00:DR-01] |
| **FR-04** | `R01` 處方 3 同構迴圈折疊與封裝違規修復 (`S2/S3/S5`) | ① `bundler.py` 與 `engine.py` 移除對 `scanner._iter_eligible_files` / `_file_belongs_to_space` 的跨物件私有調用，改用 `space_manager` 公開接口；② 於 `io_utils.py` 提煉 `normalize_dirty_paths` 與 `is_dirty_file_match` 折疊 `pipeline.py` 與 `retrieval.py` 重複迴圈；③ 折疊 `bundler.py` 之 `extract_all_call_sites_and_imports` 與 `extract_dirty_call_sites_and_imports`；④ `bundler.export_bundle` 改用 `core.vfs` 原子寫入並修正 `bundles` 路徑；⑤ 移除 `ResultFormatter` 死參數 `space_manager` 與歷史工單註解噪音。 | P1 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 索引檔 (`unified.bm25.json`) 被手動清除但 `space` 游標仍停留在高世代 | `_ensure_jit_index_ready_locked` 偵測到索引檔不存在時，先呼叫 `space.reset_cursor(consumer_id="knowledge-db")` 重置游標並執行全量 `build_unified_index()` 後再 `ack()`，確保索引與游標世代一致。 |
| **EC-02** | 某空間於 `space` 中已註冊，但未在 `knowledge-db` 之 `space_weights` 中宣告權重 | 檢索加權預設回退為 `1.0`；若 `space_weights` 中配置了 `<= 0` 的非法權重，於 `schema.py` 校驗時拋出 `InvalidConfigError`。 |
| **EC-03** | 單測環境直傳 `KnowledgeEngine(project_root=..., custom_spaces=...)` | `KnowledgeEngine` 將 `project_root` 與 `custom_spaces` 轉交 `space.SpaceManager`，並從 `custom_spaces` 中自動提取內嵌之 `weight`（若有）合併至執行期 `space_weights`，確保既有整合測試與沙盒環境平滑運作。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 行為等價與合規 | `search`、`callers`、`callees`、`impact`、`index`、`status`、`clean` 外部查詢與錯誤語意 100% 等價；通過 `dev check knowledge-db` 與全量單元測試。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 遷移 `config/knowledge-db/contribute.json` 與 `agents-workflow/contributes/knowledge-db.json` 之 `spaces` 幾何定義時，必須同步建立 `config/space/contribute.json` 與 `agents-workflow/contributes/space.json`，以確保全倉 `contributes` Schema 校驗 100% 通過。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[module:space] (SpaceManager + YFP2 Snapshot + consume_diff(consumer_id="knowledge-db"))
       │
       ├─── (Event: on_space_changed) ──► [scripts/hook.space.py]
       │                                           │
       ▼                                           ▼
[KnowledgeEngine] ──► [SearchPipeline._ensure_jit_index_ready_locked / hot_patch_unified_index]
       │
       └──► storage_dir: knowledge.storage:// (cache://knowledge-db/{indices,bundles,models})
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/knowledge_db/space.py` | Delete | `Mode A` 物理刪除，由 `space.SpaceManager` 取代 |
| `ys_codebase/source/knowledge-db/knowledge_db/scanner.py` | Delete | `Mode A` 物理刪除，由 `space` 之 `YFP2` 與 `consume_diff` 取代 |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Delete | `Mode A` 物理刪除，由 `space-watcher` + `hook.space.py` 取代 |
| `ys_codebase/source/knowledge-db/contributes/server.json` | Delete | `Mode A` 物理刪除，卸載 `knowledge-db-watcher` |
| `ys_codebase/source/knowledge-db/tests/test_scanner.py` | Delete | `Mode A` 物理刪除（已上移至 `space/tests/`） |
| `ys_codebase/source/knowledge-db/scripts/hook.space.py` | New | 訂閱 `on_space_changed` 事件並觸發增量熱修補 |
| `ys_codebase/source/knowledge-db/manifest.json` | Modify | 版本遞增至 `1.3.0.0`，`dependencies` 新增 `"space": ">=1.0.0"`，移除 `watchdog` pip 依賴 |
| `ys_codebase/source/knowledge-db/contributes/_format.json` | Modify | 將 `spaces` 替換為 `space_weights` |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | 移除 `status` 之 `--scan`/`--diff` 旗標 |
| `ys_codebase/source/knowledge-db/knowledge_db/__init__.py` | Modify | 移除舊空間/掃描匯出別名 |
| `ys_codebase/source/knowledge-db/knowledge_db/exceptions.py` | Modify | 移除空間與指紋異常類別 |
| `ys_codebase/source/knowledge-db/knowledge_db/schema.py` | Modify | 移除幾何 Schema，改為 `space_weights` 校驗 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 解耦 `storage_dir`，接入 `space.SpaceManager` 與 `consume_diff` |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 以 `consume_diff` 取代 `unified.meta.bin` 與 `.watcher_*`，折疊髒路徑匹配 |
| `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` | Modify | 改用 `space` 公開檔案列舉 API、`core.vfs` 寫入，折疊 call sites 提取迴圈 |
| `ys_codebase/source/knowledge-db/knowledge_db/io_utils.py` | Modify | 新增 `normalize_dirty_paths` 與 `is_dirty_file_match` 共用純函式 |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | 復用 `io_utils.is_dirty_file_match` |
| `ys_codebase/source/knowledge-db/knowledge_db/formatter.py` | Modify | 移除未使用之 `space_manager` 參數 |
| `ys_codebase/source/knowledge-db/knowledge_db/providers.py` | Modify | 改從 `space.SpaceManager` 與 `space_weights` 組合空間清單 |
| `ys_codebase/source/knowledge-db/knowledge_db/{graph,embedding}.py` & `parsers/{treesitter,registry}.py` | Modify | 清理歷史工單編號註解噪音 (`P2`) |
| `ys_codebase/source/knowledge-db/scripts/{cli,hook.dev}.py` | Modify | 移除 `mode == "scan"` 分支與冗餘 `spaces` 快取子目錄 |
| `ys_codebase/source/knowledge-db/tests/test_*.py` | Modify | 同步切換至 `from space import ...` 與 `hook.space.py` 測試 |
| `ys_codebase/config/space/contribute.json` | New | 承接宿主 `source` 空間幾何定義 |
| `ys_codebase/config/knowledge-db/contribute.json` | Modify | 改為宣告宿主 `space_weights` |
| `ys_codebase/source/agents-workflow/contributes/space.json` | New | 承接 `docs` 與 `plans` 空間幾何定義（純組態切分，不觸動 `agents-workflow` 程式碼） |
| `ys_codebase/source/agents-workflow/contributes/knowledge-db.json` | Modify | 改為宣告 `docs` 與 `plans` 之 `space_weights` |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 純組態切分與 `sub_03` 邊界保護**：由於 `agents-workflow/contributes/knowledge-db.json` 原本向 `knowledge-db` 註冊了 `docs` 與 `plans` 兩個檢索空間，當 `knowledge-db/contributes/_format.json` 於 `Mode A` 將 `spaces` 改為 `space_weights` 時，為使 `contributes` Schema 校驗與知識庫檢索 `docs`/`plans` 正常運作，僅將該 JSON 組態一分為二（幾何歸 `contributes/space.json`、權重歸 `contributes/knowledge-db.json`），**完全不修改 `agents-workflow` 任何 Python 業務源碼**（`agents-workflow` 業務邏輯接入 `space` 仍嚴格保留在 `sub_03`）。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# knowledge_db/io_utils.py
def normalize_dirty_paths(dirty_file_paths: Iterable[str]) -> Set[str]: ...
def is_dirty_file_match(doc_file_path: str, dirty_paths_norm: Set[str]) -> bool: ...

# scripts/hook.space.py
def on_space_changed(
    context: Any,
    spaces: Optional[List[str]] = None,
    diff_summary: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 空間不存在或配置錯誤統一拋出 `space.SpaceNotFoundError` 與 `space.InvalidSpaceConfigError`。
- **階段決策紀錄**：`[P03:DR-01]` `KnowledgeEngine.get_space_weight(space_name: str) -> float` 統一提供空間檢索權重查詢（優先讀取 `space_weights` 配置，回退至 `SpaceConfig.weight` 或預設值 `1.0`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 與 `R01` 所有 P0/P1/P2 處方皆已完整對齊
- [x] **邊界防護**：EC-01 ~ EC-03 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：`KnowledgeEngine.clean()` 在清除索引快取時，是否應同步重置 `knowledge-db` 在 `module:space` 的消費者游標？*
  - *答*：是！`engine.clean()` 刪除 `cache://knowledge-db/` 下之索引與 bundle 後，必須同步呼叫 `space.reset_cursor(consumer_id="knowledge-db")`，確保下次建立或查詢時不會因游標已在最新世代而誤判為「無變更」跳過建索引。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/knowledge-db/README.md` | Modify | 更新空間配置說明（指向 `space` 模組與 `space_weights`） |
| **專題手冊** | `docs/KnowledgeDB/README.md` | Modify | 於 Phase 7 同步更新 `space` 依賴與增量同步說明 |
| **設計決策** | `docs/KnowledgeDB/DESIGN_NOTES.md` | Modify | 於 Phase 7 記錄 `Mode A` 遷移決策 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 清理歷史工單編號並更新公開 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 記錄 `knowledge-db` v1.3.0.0 變更 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_02` 規格定案，待 `sub_01` 完成後立即推進重構。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：物理刪除 `knowledge_db/{space,scanner,service}.py`、`contributes/server.json`、`tests/test_scanner.py`，並完成 `manifest.json`、`contributes/` 與宿主 `config/` 組態遷移
- [x] **TASK-02**：重構 `knowledge_db/{__init__,exceptions,schema,io_utils,engine,pipeline,bundler,retrieval,formatter,providers}.py` 與 `scripts/{cli,hook.dev,hook.space}.py`，並清理歷史工單註解噪音
- [x] **TASK-03**：同步更新 `ys_codebase/source/knowledge-db/tests/` 測試套件，執行 `dev check knowledge-db`、`dev test knowledge-db` 與 `@build` 整合驗證

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

