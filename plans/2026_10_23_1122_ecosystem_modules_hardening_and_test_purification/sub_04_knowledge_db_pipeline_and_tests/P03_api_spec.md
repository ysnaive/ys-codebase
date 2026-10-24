# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_04_knowledge_db_pipeline_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `CallGraphIndex.get_external_incoming_edges` | `knowledge_db/graph.py` | Public | 提取指定符號集合之外界入度調用邊三元組 `(caller_id, old_callee_id, site)` |
| `KnowledgePipeline.search` | `knowledge_db/pipeline.py` | Public | 複合語意搜尋主入口，分離載入條件，修復冷啟動向量死鎖與多副檔名過濾 |
| `KnowledgePipeline.hot_patch_unified_index` | `knowledge_db/pipeline.py` | Public | 增量熱修補主流程，落實同檔案身分重映與次選消歧之雙階保真重連 |
| `KnowledgeEngine` SDK 方法別名 | `knowledge_db/engine.py` | Public | 提供對齊 `README.md` 的 `callers()`、`callees()`、`impact()` 公開 API |
| `KnowledgeDBConfig.load` | `knowledge_db/config.py` | Public | 優先自 `core.config` 載入設定，支援常駐 Worker 熱刷新 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class CallGraphIndex:
    def get_external_incoming_edges(
        self, target_symbol_ids: Set[str]
    ) -> List[Tuple[str, str, SymbolCallSite]]:
        """
        Extracts all incoming edges from symbols outside target_symbol_ids to symbols inside target_symbol_ids.

        Returns:
            List of (caller_id, old_callee_id, symbol_call_site)
        """
        ...

class KnowledgePipeline:
    def search(
        self,
        query: str,
        space: Optional[str] = None,
        top_k: int = 20,
        lexical_only: bool = False,
        ftypes: Optional[Union[str, List[str]]] = None,
        auto_rebuild: bool = True,
        verbose: bool = False,
        **kwargs: Any,
    ) -> List[SearchResult]:
        """
        Executes hybrid semantic search. Separates pre-load demand calculation from post-load availability probe.
        """
        ...

    def hot_patch_unified_index(
        self,
        dirty_files: List[str],
        deleted_files: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes incremental hot-patching with dual-stage incoming edge reconnection:
        Stage 1: Identity Remap (O(1) in-file matching)
        Stage 2: Fallback TopologyLinker disambiguation
        """
        ...

class KnowledgeEngine:
    def callers(self, target_query: str, space: Optional[str] = None, file_types: Optional[Union[str, List[str]]] = None, **kwargs) -> Dict[str, Any]:
        """SDK Alias for act_callers matching README.md documentation."""
        ...

    def callees(self, target_query: str, space: Optional[str] = None, file_types: Optional[Union[str, List[str]]] = None, **kwargs) -> Dict[str, Any]:
        """SDK Alias for act_callees matching README.md documentation."""
        ...

    def impact(self, target_query: str, space: Optional[str] = None, max_depth: int = 3, **kwargs) -> Dict[str, Any]:
        """SDK Alias for act_impact matching README.md documentation."""
        ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 向量模型無法載入或損毀時，`want_vectors=True` 經 `_ensure_jit_index_ready` 嘗試後，若失敗則 `is_vector_available` 保持 `False`，平滑回退純 BM25，絕不拋出未捕獲例外。
  - 當調用之符號在熱修補中被徹底刪除時，雙階重連均失敗，該邊自動清退不留孤兒邊。
- **階段決策紀錄**：`[P03:DR-01]` 外部調用者若無前綴裸調用，第一階以同檔案 `(norm_file_path, name)` 身分優先完成對齊，避免無 `file_imports` 誤殺。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 核心資料結構與死代碼清理]
  - 刪除 knowledge_db/protocol.py 與 schema.py:CallGraphNode
  - 清理 contributes/ 與 Python 檔案中殘留的 thesaurus / aliases / related

[Step 2: 檢索管線與調用圖譜增量修復]
  - 於 knowledge_db/graph.py 增加 get_external_incoming_edges()
  - 於 knowledge_db/pipeline.py 修復 search() 前置載入條件與 hot_patch 雙階重連
  - 於 knowledge_db/hybrid.py 修復多副檔名過濾

[Step 3: 運行時空間與常駐服務單一託管]
  - 純化 scripts/hook.server.py，移除私自啟動 Watcher
  - 清理 knowledge_db/service.py 之 source/server 注入與 engine.py 之 events 呼叫
  - 修復 knowledge_db/config.py 優先級

[Step 4: CLI 契約、SDK 別名與三層文檔對齊]
  - 補齊 contributes/core.json 選項與 hooks 宣告
  - 修復 scripts/cli.py -d 切片與 JSON 欄位
  - 於 knowledge_db/engine.py 補齊 SDK 別名並同步文檔

[Step 5: 測試套件純化收斂 14 檔 -> 12 檔與高風險補盲]
  - 刪除 test_benchmark_perf_and_memory.py 與 test_cli_ux.py
  - 重寫 5 處虛假測試與墓碑測試
  - 補齊冷啟動向量載入、熱修補入度邊保真等四大漏測路徑
```

