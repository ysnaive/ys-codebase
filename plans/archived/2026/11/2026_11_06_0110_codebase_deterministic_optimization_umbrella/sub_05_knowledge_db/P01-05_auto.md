# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_05_knowledge_db 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `EmbeddingService`、`VectorIndex` 與 `KnowledgeDBConfig` 重入鎖及邊界防禦 (`OPT-02~04`) | `_init_lock` 升級 `RLock()`、`is_available` 模型缺失重置 `_init_attempted`、`VectorIndex.search` 維度相容守門與 `resolve_threads` 排除 `bool` 誤判。 | P0 | [P00:DR-01] |
| **FR-02** | `BM25Engine`、`InvertedIndex`、`HybridSearchEngine` 與 `SnippetExtractor` 收斂與執行緒安全 (`OPT-05~07, 11`) | 提取 `normalize_ftypes`、`resolve_space_weight`、`format_symbol_summary`，修正同 `doc_id` 重複寫入統計，為 `_file_lines_cache` 加鎖並補齊 `formatter` 預算守門。 | P0 | [P00:DR-01] |
| **FR-03** | `Pipeline`、`ServiceWorker`、`KnowledgeDBEngine` 與 `scripts/` 併發鎖及頂層零賦值 (`OPT-01, 08~10, 12`) | `clean()`/`start()`/`get_engine()` 全程加鎖、磁碟索引缺失同步清空 `_GLOBAL_INDEX_CACHE`、`read_worker_state` 死進程回退同進程狀態、移除 `hook.*.py` 與 `cli.py` 頂層賦值。 | P0 | [P00:DR-02] |
| **FR-04** | `tests/test_*.py` 10 檔測試套件純化與 `0 time.sleep` / `0 ResourceWarning` (`AUD-01~24`) | 以 `write_text_and_advance_mtime` 取代 15 處 `time.sleep`，清零工單編號並補齊遷移腳本與自癒邊界驗證。 | P0 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `EmbeddingService.download_model()` 於持有 `_init_lock` 期間間接呼叫模型載入 | 使用 `threading.RLock()` 並抽取 `_load_fastembed_instance` 避免重入死鎖與重複實例化。 |
| **EC-02** | 磁碟 `unified.index.bin.gz` 被外部刪除但記憶體 `_GLOBAL_INDEX_CACHE` 仍殘留舊索引 | `_ensure_indices_loaded` 偵測磁碟索引缺失時同步清空 `_GLOBAL_INDEX_CACHE['unified_index']` 並觸發重建。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態規範與向後相容 | `Checker().check_module('knowledge-db')` 達成 `0 FAIL, 0 WARN`，4 支腳本頂層 `0 ast.Assign`，公開 SDK/CLI 100% 向後相容。 |
| **NFR-02** | 測試純淨度與執行效能 | 112 項單元測試於 `python3 -W error::ResourceWarning` 下 100% 通過（耗時 `2.27s`，`0 ResourceWarning`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開契約相容與鎖可重入性**：所有內部鎖升級與快取深拷貝均須維持公開方法簽名與單元測試 Mock 攔截點 100% 相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `knowledge-db` 現有公開模組拓撲，透過內部純函式提煉、可重入鎖保護、原子寫入回滾與測試沙盒隔離消除競態與結構膨脹。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/knowledge-db/knowledge_db/__init__.py` | Modify | 落實 `OPT-10`（`__dir__()` 集合去重） |
| `ys_codebase/source/knowledge-db/knowledge_db/config.py` | Modify | 落實 `OPT-03`（`resolve_threads` 排除 `bool` 與 `_extract_config_section` 統一解析） |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 落實 `OPT-02, OPT-04`（`RLock` 防重入死鎖、模型缺失重置與維度守門） |
| `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Modify | 落實 `OPT-09, OPT-10`（`_ENGINE_LOCK` 與 `_build_unified_semantic_bundle`） |
| `ys_codebase/source/knowledge-db/knowledge_db/formatter.py` | Modify | 落實 `OPT-02, OPT-11`（字元預算守門與渲染輔助抽取） |
| `ys_codebase/source/knowledge-db/knowledge_db/hybrid.py` | Modify | 落實 `OPT-05`（共用 `normalize_ftypes`、`resolve_space_weight` 與 `_build_bm25_results`） |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | 落實 `OPT-05, OPT-07, OPT-08, OPT-09`（`_GLOBAL_INDEX_CACHE` 失效同步與 `clean()` 加鎖） |
| `ys_codebase/source/knowledge-db/knowledge_db/retrieval.py` | Modify | 落實 `OPT-05, OPT-06, OPT-07`（BM25 單趟計分、`_cache_lock` 與同 `doc_id` 去重） |
| `ys_codebase/source/knowledge-db/knowledge_db/selector.py` | Modify | 落實 `OPT-02`（型別匯入清理） |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 落實 `OPT-09`（`_WORKER_LOCK` 與過期死進程狀態檔回退） |
| `ys_codebase/source/knowledge-db/scripts/cli.py` | Modify | 落實 `OPT-02, OPT-12`（頂層零常數賦值與 `--opt val` 雙 token 解析） |
| `ys_codebase/source/knowledge-db/scripts/hook.dev.py` | Modify | 落實 `OPT-01`（移除頂層 `logger` 執行語句） |
| `ys_codebase/source/knowledge-db/scripts/hook.file-space.py` | Modify | 落實 `OPT-01, OPT-12`（移除頂層執行語句並優先檢查 `get_active_worker()`） |
| `ys_codebase/source/knowledge-db/scripts/hook.server.py` | Modify | 落實 `OPT-01`（移除頂層 `logger` 執行語句） |
| `ys_codebase/source/knowledge-db/tests/__init__.py` & `tests/test_*.py` (10 檔) | Modify | 落實 `AUD-01 ~ AUD-24`（移除 15 處 `time.sleep`、清零工單編號並補齊 112 項測試） |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 受控 CoW 雲端同步與零工單殘留**：全部 24 個修改檔案皆以受控 CoW（舊檔移入 `repo/.trash/` 後上傳原格式新檔）同步至 Google Drive，且源碼與測試內達成 0 工單編號殘留。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

維持 `knowledge-db` 對外公開 SDK 與 `scripts/cli.py` 所有子指令、選項及回傳碼契約 100% 向後相容（`Mode B`），內部私有輔助函式採單一正統入口（`Mode A`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] 已通過 Step 2 魔鬼代言人（Devil's Advocate B1/B2）反向查驗、Step 4 盲測驗收（Subagent D `PASS`）與 Step 5 零錨定二次審計（Subagent E `P0=0, P1=0, P2=0` 融斷通過）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | Modify | 於專案根目錄 `CHANGELOG.md` 登記 `sub_05_knowledge_db` 優化與修復摘要 |
| **中觀 (Meso)** | `docs/knowledge-db/README.md` | 免更 | 屬內部確定性重構與併發/邊界防禦強化，無公開架構或 CLI 語法變更 |
| **微觀 (Micro)** | `ys_codebase/source/knowledge-db/` | Modify | 清理工單編號註解並同步維護公開與內部輔助函式 Docstring |

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲測子代理 A1/A2 初審與 B1/B2 反向驗證（定案 `OPT-01 ~ OPT-12` 與 `AUD-01 ~ AUD-24`）
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C1/C2 沙盒實作、測試純化與雲端受控 CoW 同步（共 24 檔）
- [x] **TASK-03**：完成 Loop 1 Step 4 盲測子代理 D 驗收（`PASS`）與 Step 5 盲測子代理 E 零錨定融斷判定（`P0=0, P1=0, P2=0`）
- [x] **TASK-04**：完成 Phase 07 SOP Review Gate 冷眼靜態審查、三層文檔對齊與 `P07_walkthrough.md` 結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
