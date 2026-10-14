# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_03_knowledge_db_and_workflow_engine_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `KnowledgePipeline._ensure_jit_index_ready` | `source/knowledge-db/knowledge_db/pipeline.py` | Internal | JIT 變更感知與索引熱載入/修補，支援按需跳過向量資料 |
| `InvertedIndex.patch_incremental` | `source/knowledge-db/knowledge_db/retrieval.py` | Public | 差量熱修補倒排索引，剛性防止跨目錄同名檔案連坐誤刪 |
| `HybridSearchEngine.search` | `source/knowledge-db/knowledge_db/hybrid.py` | Public | 複合檢索，支援 `spaces`、`kinds`、`languages` 前置過濾 |
| `EmbeddingService.embed_texts` | `source/knowledge-db/knowledge_db/embedding.py` | Public | 批次特徵推論，非 mock 模式失敗時回傳純淨空矩陣 |
| `ArtifactPublisher._get_source_file_sha1` | `source/agents-workflow/agents_workflow/publisher.py` | Internal | 檔案與目錄型資產遞迴指紋計算 |
| `ArtifactCompiler.resolve_stage2_uris` | `source/agents-workflow/agents_workflow/compiler.py` | Public | Stage 2 語意標籤解算，支援 Markdown 括號反引號剝除與尾斜線保留 |
| `PlanVerifier.VALID_STATUSES` | `source/agents-workflow/agents_workflow/plans/verifier.py` | Public | 驗證合約支援之合法計畫狀態枚舉集合 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. Pipeline JIT 索引就緒保證
def _ensure_jit_index_ready(
    self,
    require_vectors: bool = False,
    auto_rebuild: bool = True,
    verbose: bool = False,
) -> None:
    """確保記憶體倒排索引與調用圖譜就緒。若 require_vectors=False，跳過向量推論。"""

# 2. InvertedIndex 精確路徑差量修補
def patch_incremental(
    self,
    dirty_file_paths: Set[str],
    new_symbols: List[UnifiedSymbol],
    tokenizer: Optional[CodeTokenizer] = None,
) -> None:
    """差量修補倒排索引。對於包含 '/' 之路徑嚴格比對完整或後綴路徑，杜絕同名檔誤刪。"""

# 3. HybridSearchEngine 多維前置過濾
def search(
    self,
    query: str,
    limit: int = 10,
    file_types: Optional[List[str]] = None,
    spaces: Optional[List[str]] = None,
    kinds: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    lexical_only: bool = False,
) -> List[Dict[str, Any]]:
    """執行 BM25 + 向量 RRF 複合檢索，候選集全流程前置滿足多維約束。"""

# 4. Publisher 目錄型遞迴雜湊
def _get_source_file_sha1(self, path_or_uri: str) -> str:
    """計算來源檔案或目錄之 SHA-1。若是目錄，遞迴走訪內部所有檔案計算組合摘要。"""
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: knowledge-db 核心檢索與圖譜]
  ├── retrieval.py & pipeline.py (同名檔防護與 _ensure_jit_index_ready 抽取)
  ├── hybrid.py & embedding.py (前置過濾與向量推論守門)
  └── formatter.py, service.py & pipeline.clean (切片重複修復與向量清理)

[Step 2: agents-workflow 靜態發布與稽核]
  ├── publisher.py (目錄型遞迴指紋計算)
  ├── compiler.py (Stage 2 尾斜線與括號反引號修復)
  ├── verifier.py (合法狀態枚舉擴充與歸檔目錄回退)
  └── analyzer.py & cli.py (Antigravity 路徑對齊與描述佔位符解開)

[Step 3: 驗收與知識庫回寫]
  ├── knowledge-db 單元測試 (test_hot_reload.py, test_retrieval.py, test_graph.py)
  ├── agents-workflow 單元測試 (test_publisher.py, test_compiler.py, test_verifier.py)
  └── DESIGN_NOTES.md 決策登記
```

