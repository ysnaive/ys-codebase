# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_knowledge_db_and_workflow_engine_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  依據主計畫與 R01 審計報告對 `knowledge-db` 與 `agents-workflow` 兩大模組進行深度修復：
  1. `knowledge-db`：修復增量熱自愈修補以 `Path(p).name` 誤刪全庫同名檔案符號、複合檢索未預先過濾 `spaces`/`kinds`/`languages`、非 Mock 模式下載失敗產出偽向量污染、`clean()` 遺漏向量快取檔、`act_callers`/`callees`/`impact` 無謂觸發向量推論、`.watcher_dirty` 競態與 `callees -d` 程式碼切片重複輸出。
  2. `agents-workflow`：修復 Stage 0 目錄型 Skill SHA-1 空字串盲區、Stage 2 連結反引號與尾斜線缺陷、`PlanVerifier` 狀態枚舉脫節與 `session-analysis` 之 Antigravity 軌跡路徑。
- **核心目標**：
  - 徹底消除 `knowledge-db` 跨目錄同名檔案索引被誤刪之嚴重數據破壞隱患。
  - 確保複合檢索 `spaces`/`kinds`/`languages` 前置精確過濾，不再因向量 Top-K 截斷導致零結果。
  - 圖譜查詢（callers, callees, impact）與向量推論徹底正交解耦，大幅提升回應速度。
  - `agents-workflow` 靜態發布、模板編譯與合規稽核達到 100% 健壯性。
- **邊界排除 (Explicitly Excluded)**：
  - 保持受單元測試鎖定之 SDK Deprecated 相容方法與 `protocol.py`/`thesaurus` 結構不動。
  - 不更動 `sub_05` 範疇之 Workflow 全面遷移為 Skill 架構（純化在 `sub_05` 獨立進行）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 增量修補同名檔誤刪防護與雙軌比對**：
  在 `pipeline.py` 與 `retrieval.py` 的增量修補比對中，當 `dirty_paths` 包含路徑分隔符時（如 `source/core/tests/test_cli.py`），強制要求完整標準化路徑比對或後綴路徑比對；僅當路徑為純檔案名稱（無斜線，如單元測試傳入之 `test.py`）時方退化為 `sym_fn == p`，杜絕連坐誤刪全庫同名檔。
- **[P00:DR-02] 複合檢索多維前置過濾保證**：
  擴充 `HybridSearchEngine.search()` 簽名以支援 `spaces`、`kinds`、`languages`，在 BM25 檢索與向量檢索候選池評估時進行前置過濾，避免向量 Top-K 截斷後過濾產生空召回。
- **[P00:DR-03] 非 Mock 模式向量推論嚴格守門**：
  當 `mock_mode` 為 False 且向量模型加載失敗或推論異常時，嚴禁偽造隨機向量寫入索引，一律回傳空向量陣列，由外層安全降級純 BM25。
- **[P00:DR-04] 圖譜導向極速 JIT 索引提取**：
  從 `search()` 中抽取 `_ensure_jit_index_ready(require_vectors: bool)`，`act_callers`、`act_callees` 與 `act_impact` 僅請求符號與圖譜索引就緒，不再調用 `self.search()`，杜絕無謂向量推論延遲。
- **[P00:DR-05] Stage 0 目錄型 Skill 遞迴 SHA-1 聚合**：
  在 `publisher._get_source_file_sha1` 檢測到來源為目錄時，遞迴走訪目錄下所有檔案並以相對路徑排序聚合計算 SHA-1，確保目錄內容變更時精確觸發髒狀態。
- **[P00:DR-06] PlanVerifier 狀態枚舉與層級規則對齊**：
  `VALID_STATUSES` 納入 SOP 核心狀態：`discussing`, `planning`, `executing`, `concluded`, `aborted`, `cancelled`；剛性守護兩層計畫層級限制。

---

## 3. 開放議題與確認紀錄

- [x] 所有修復點皆基於真實代碼排查確認，非過往特意設計，方案經評估具備 100% 零回歸可行性。

