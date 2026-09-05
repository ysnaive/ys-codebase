# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_multilingual_tokenizer_and_hybrid_search  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 API 規格書與架構圖中均有對應類別與方法簽名。
- [x] **邊界防護**：EC-01 ~ EC-05 均定義了捕獲降級、截斷保護與安全空傳防護策略。
- [x] **依賴純淨**：採用 Wheel-Only ONNX Runtime，無 PyTorch 沉重負擔，符合 NFR-01~04 約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `source/knowledge-db/README.md` | Modify | 增補多語言 Tokenizer 與 BM25+向量 RRF 複合檢索架構圖與使用說明 |
| **專題手冊** | `docs/knowledge-db/retrieval.md` | Modify | 新增 RRF 倒數排名融合公式、向量快取機制與平滑降級工作流 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 DN-09 (FastEmbed 離線向量推論與雙軌平滑降級) |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 sub_02 發布摘要與對外契約保證 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若宿主完全處於離線環境（Air-gapped）且尚未快取 ONNX 模型時，系統是否會直接死鎖、掛起或向終端傾倒 Traceback？  
> 💡 **防護解法**：`EmbeddingService` 在初始化與模型載入處配置短超時與全域 `try...except Exception` 兜底；若未命中本地快取且下載失敗，立即將 `is_available` 置為 `False`，平滑退化為 100% 純 BM25 檢索，終端僅輸出簡短除錯提示，絕不阻斷 Agent 搜索任務。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/knowledge-db/manifest.json` 宣告 `fastembed` 相依，並安裝至私有微環境
- [ ] **TASK-02**：重構 `knowledge_db/tokenizer.py`，實作 `MultilingualTokenizer`，支援中英混雜與駝峰蛇形拆解
- [ ] **TASK-03**：新建 `knowledge_db/embedding.py`，實作 `EmbeddingService` 與 Mock 機制，支援特徵向量生成與快取
- [ ] **TASK-04**：新建 `knowledge_db/hybrid.py`，實作 `HybridSearchEngine` 與標準 RRF 倒數排名融合演算法
- [ ] **TASK-05**：徹底刪除舊同義詞庫檔案 `knowledge_db/thesaurus.py` 與 `tests/test_thesaurus.py`
- [ ] **TASK-06**：修改 `knowledge_db/engine.py`，整合複合檢索流水線與 `--lexical-only` 命令列旗標
- [ ] **TASK-07**：編寫單元與整合測試 (`test_tokenizer.py`, `test_hybrid.py`)，驗證 RRF 融合與 100% 降級防護
- [ ] **TASK-08**：跑測全套單元測試與生態系回歸測試 (`dev test knowledge-db --quiet`)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：確定採方案 A（標準依賴 + 雙軌剛性降級保證），將 `fastembed` 納入宣告，代碼層實作零崩潰降級。
- **[P04:DR-02]**：RRF 融合演算法標準化，預設常數 $k=60$，$w_{bm25}=0.5, w_{vec}=0.5$，確保關鍵字精準度與語意泛化度平衡。
