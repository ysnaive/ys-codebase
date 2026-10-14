# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_03_knowledge_db_and_workflow_engine_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 增量熱修補精確路徑比對 | 在 `pipeline.py` 與 `retrieval.py` 增量修補舊符號清理邏輯中，若路徑含斜線，僅執行精確或後綴匹配，不再單憑 `Path(p).name == sym_fn` 誤刪其他目錄下同名檔案符號。 | P0 | [P00:DR-01] |
| **FR-02** | 複合檢索多維前置過濾 | `HybridSearchEngine.search()` 支援傳入 `spaces`、`kinds`、`languages`，並在 BM25 檢索與向量檢索候選池進行前置過濾，杜絕 Top-K 截斷後過濾導致的空召回。 | P0 | [P00:DR-02] |
| **FR-03** | 向量推論失敗純淨防偽 | 當 `mock_mode` 為 False 且向量服務加載失敗或推論異常時，`embed_texts` 一律回傳 `(0, dim)` 空陣列，嚴禁注入假隨機向量污染索引。 | P0 | [P00:DR-03] |
| **FR-04** | 清理管線向量完整覆蓋 | `pipeline.clean()` 刪除檔案清單中補齊 `unified.vectors.bin.gz`，並清空全域記憶體索引快取池。 | P1 | [P00:DR-04] |
| **FR-05** | JIT 索引檢查與向量解耦 | 抽取 `_ensure_jit_index_ready(require_vectors=False)`；`act_callers`、`act_callees`、`act_impact` 僅確保符號與圖譜就緒，不再調用 `self.search()` 浪費向量推論。 | P0 | [P00:DR-04] |
| **FR-06** | 服務日誌與 CLI 切片修復 | `ServiceWorker` 在修補完成後才清理 `.watcher_dirty` 避免競爭；修復 `formatter.py` 在 `callees -d` 下重複輸出兩次程式碼切片之缺陷。 | P1 | [P00:DR-01] |
| **FR-07** | Skill 目錄遞迴指紋計算 | `publisher._get_source_file_sha1` 檢測到目錄時，遞迴走訪目錄所有檔案並按相對路徑排序計算綜合 SHA-1，確保 Skill 修改時 Stage 0 精確感知。 | P0 | [P00:DR-05] |
| **FR-08** | Stage 2 語意連結與尾斜線 | `compiler.py` 支援 Markdown 連結括號內反引號剝除；解析保留 `tag_uri` 原有尾斜線；CLI `list` 命令輸出解開描述中的佔位符。 | P1 | [P00:DR-05] |
| **FR-09** | Plan 稽核與軌跡路徑對齊 | `PlanVerifier.VALID_STATUSES` 納入 `discussing`、`planning`、`executing`、`concluded` 等狀態；`analyzer.py` 修正 Antigravity 軌跡路徑。 | P1 | [P00:DR-06] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 單元測試傳入無路徑純檔名（如 `dirty_paths={"beta.py"}`） | 若傳入字串不含斜線（`"/" not in p`），平滑退化為比對 `sym_fn == p`，維持現有測試契約。 |
| **EC-02** | 向量模型未下載或環境缺少依賴且 `mock_mode=False` | `embed_texts` 回傳空矩陣，`HybridSearchEngine` 100% 剛性平滑降級為純 BM25 檢索。 |
| **EC-03** | 目錄型 Skill 中包含空目錄、符號連結或不可讀檔案 | 遞迴雜湊跳過不可讀檔案，不中斷發布流水線。 |
| **EC-04** | 計畫文件層級超過 2 層（如 `sub_01/sub_child/`） | `PlanVerifier` 在 Stage 1 剛性回報 FAIL，守護架構扁平度。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 延遲 | 圖譜查詢（`act_callers`/`callees`/`impact`）無向量干擾，冷熱查詢時間顯著降低（$< 50\text{ms}$）。 |
| **NFR-02** | 品質保證 | 全專案全生態系 550 測試 100% 通過，0 失敗、0 警告。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：`knowledge-db` 與 `agents-workflow` 含有多處受既有單元測試鎖定的向後相容邏輯（如 `test_hot_reload.py:390` 與 `test_output_purification.py`），所有修改必須採用高保真雙軌設計，嚴禁破壞既有邊界。

