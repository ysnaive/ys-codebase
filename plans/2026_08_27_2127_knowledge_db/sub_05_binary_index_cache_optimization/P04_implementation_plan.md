# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 子計畫 05: 符號池去重與二進位 Gzip 倒排索引快取優化 (Symbol Pool Normalization & Binary Gzip Inverted Index Cache Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 依據 P03：[P03_api_spec.md](./P03_api_spec.md)  
> 測試計畫：[P06_test_plan.md](./P06_test_plan.md) (Confirmed)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 `P03_api_spec.md` 中均有對應 API 簽名與資料結構。
- [x] **邊界防護**：EC-01 ~ EC-04 在二進位損毀自癒、快取缺失重構、符號池安全索引中均有完整覆蓋。
- [x] **依賴純淨**：NFR-01 ~ NFR-04 承諾 100% Python 原生標準庫（Zero External Dependency）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **維度 3 (架構)** | `docs/knowledge-db/architecture.md` | **Modify** | 更新倒排索引二進位快取 (`.index.bin.gz`) 與符號池解耦架構圖 |
| **維度 6 (檢索)** | `docs/knowledge-db/retrieval.md` | **Modify** | 補充二進位快取讀寫、符號池去重與效能基準說明 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：跨 Python 小版本時，Pickle 二進位序列化是否會產生相容性問題？**  
> 💡 **防護解法**：`InvertedIndex` 僅使用 Python 標準基本型別（`dict`, `list`, `str`, `int`, `float`, `tuple`），在 Python 3.8 ~ 3.13+ 間 100% 二進位相容。且即便發生異常，`EC-01` 會自動捕獲並透明重建索引，保證 100% 韌性。

> ❓ **尖銳問題 2：現有磁碟上的舊版 `.index.json` (55 MB) 如何處置？**  
> 💡 **防護解法**：在 Phase 5 實作中自動清除舊的 `.index.json`，且 `KnowledgeEngine.clean()` 與 `_get_or_build_index` 全面切換為優先識別 `.index.bin.gz`。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (InvertedIndex 與 Posting 重構)**：重構 `source/knowledge-db/knowledge_db/retrieval.py`，抽離 `symbols` 符號池，實作 `save_binary` 與 `load_binary`，適配 `BM25Engine.search`。
- [ ] **TASK-02 (KnowledgeEngine 快取升級與舊檔清理)**：修改 `source/knowledge-db/knowledge_db/engine.py`，將索引快取路徑更新為 `.index.bin.gz`，升級 `status` 與 `clean`，並清除磁碟上舊的 55 MB `.index.json`。
- [ ] **TASK-03 (單元與效能測試套件更新)**：更新 `test_retrieval.py` 與 `test_engine.py`，驗證 FT-01~06、ET-01 與 RT-01。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿實作計畫與測試清單**：確認 Phase 1~3 規格與依賴拓撲無誤，同步定稿 `P06_test_plan.md` 為 `Confirmed`，進入 Phase 5 編碼實作。
