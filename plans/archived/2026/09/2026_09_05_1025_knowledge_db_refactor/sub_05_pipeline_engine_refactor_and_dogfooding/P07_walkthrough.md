# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **管線門面職責三向解耦**：將 1,765 行龐大單體 `engine.py` 拆解為專責呈現排版的 `formatter.py`、專責索引生命週期與查詢編排的 `pipeline.py`，並將 `engine.py` 瘦身 80.8% 至 338 行輕量門面 Facade，100% 委派且 Public API 完全向後相容。
  2. **8,000 字元動態預算與全域通用去重**：CLI 輸出預算由 12,500 收斂至 8,000 字元；實作 4 段階梯平滑衰減曲線；`UniversalRedundancyFilter` 自動過濾程式碼切片已摘要之 Docstring、Markdown 切片重疊之 Heading、License 樣板與連續空白行，資訊密度極致化。
  3. **向量推論防護與系統飢餓阻斷 ([P06:DR-01])**：ONNX Runtime 限制執行緒上限為 `min(2, max(1, cpu//2))`，並以 `batch_size=64` 切片搭配 `time.sleep(0.005)` 讓出 OS 調度時間片，剛性杜絕 CPU 100% 飽和與系統凍結；`VectorIndex.save_binary` 降級為 `compresslevel=1`。
  4. **AST 單次走訪與解析器單例快取**：多進程 Worker 引入 `_get_worker_registry` 單例快取，消滅每檔重複編譯 7 套 `.scm` 之開銷；`extract_call_sites` 重用已解析符號實例，消除調用點提取時的二次 AST 解析，全庫 231 檔索引建置由數分鐘卡死壓降至 **10.4 秒** 平穩完成。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/knowledge_db/formatter.py` | New | 實作 `ResultFormatter`、`UniversalRedundancyFilter`、8,000 字元預算動態衰減計算器與終端排版 |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | New | 實作 `IndexingPipeline`，封裝多空間倒排與向量索引建置、JIT 增量嗅探、熱修復補丁與快取管理 |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 瘦身 80.8% 為 338 行輕量門面中樞，維持 100% 既有 Public API 簽名與常數向後相容 |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 限制 ONNX 執行緒上限、分批推論時間片讓渡，以及 `VectorIndex.save_binary` 寫盤壓縮等級降至 1 |
| `ys_codebase/source/knowledge-db/knowledge_db/bundler.py` | Modify | 實作 Worker 解析器單例快取 `_get_worker_registry`，以及調用點提取傳入 `cached_syms` 避免二次 AST 解析 |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/base.py` | Modify | `BaseParser.extract_call_sites` 簽名擴充 `symbols: Optional[List[UnifiedSymbol]] = None` |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py` | Modify | `ParserRegistry.extract_call_sites` 轉發 `symbols` 參數至底層解析器 |
| `ys_codebase/source/knowledge-db/knowledge_db/parsers/treesitter.py` | Modify | `TreeSitterDriver.extract_call_sites` 支援重用已傳入之 `symbols`，跳過內部重複 `self.parse()` |
| `ys_codebase/source/knowledge-db/tests/test_engine.py` | Modify | 擴充 Formatter、Filter、8,000 字元動態衰減與 IndexingPipeline 單元測試 |
| `ys_codebase/source/knowledge-db/tests/test_retrieval.py` | Modify | 增補 `test_batching_and_thread_capping` 驗證分批推論切片與執行緒上限 |
| `ys_codebase/source/knowledge-db/tests/test_graph.py` | Modify | 增補 `extract_call_sites` 重用 `symbols` 之解析結果一致性斷言 |
| `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `[DN-12]` (管線門面職責分離與去重) 與 `[DN-13]` (向量推論防護與 AST 單次走訪) |
| `docs/knowledge-db/README.md` | Modify | 更新架構全景圖、管線演進與子計畫清冊 |
| `CHANGELOG.md` | Modify | 記錄 sub_05 結案與里程碑 5 達成之高階變更條目 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：全模組 124/124 單元與契約測試 100% 通過（`Pass: 124(100.0%), Fail: 0, Skip: 0, Unknown: 0`）。
- **靜態合規性預檢**：`python yscb.py dev check knowledge-db` 檢核狀態為 `PASSED`。
- **實機 UX / 人工驗證 (UX-01)**：
  - 執行 `python yscb.py install knowledge-db@build --force` 完成本地物化更新。
  - 實機執行 `python yscb.py knowledge-db search KnowledgeEngine -s`：231 檔索引熱建置僅耗時 10.4 秒平穩完成，全系統零卡死、零凍結；熱快取搜尋 sub-2s；輸出總字元數受 8,000 字元預算保護且切片 Docstring 去重純化正常，標定為 `[測試通過]`。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | ✅ 已交付 | 更新解耦後架構全景、子計畫演進清冊與 CLI / SDK 使用說明 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | ✅ 已交付 | 登記 `[DN-12]` (門面解耦與 8,000 字元預算衰減) 與 `[DN-13]` (向量推論防護與 AST 走訪優化) |
| **發布日誌** | `CHANGELOG.md` | ✅ 已交付 | 追加 `sub_05_pipeline_engine_refactor_and_dogfooding` 完整變更條目 |
| **代碼註解契約** | `knowledge_db/` 各源碼檔案 | ✅ 已交付 | Public API 類別與方法具備完整 Google-style Docstring，重要演算法具備動機說明 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(knowledge-db): decouple pipeline engine and safeguard vector inference

- Decouple monolithic engine.py into formatter.py and pipeline.py (down to 338 lines)
- Implement UniversalRedundancyFilter and 8,000-char dynamic budget decay
- Safeguard EmbeddingService with ONNX thread capping and batch sleep-yielding
- Optimize TreeSitterDriver and bundler with worker parser caching and symbol reuse
- Update design notes (DN-12, DN-13) and achieve 100% test pass rate (124/124)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan check 2026_09_05_1025_knowledge_db_refactor/sub_05_pipeline_engine_refactor_and_dogfooding` 驗證 100% PASSED（1 Total, 1 Passed, 0 Warnings, 0 Failed）。
