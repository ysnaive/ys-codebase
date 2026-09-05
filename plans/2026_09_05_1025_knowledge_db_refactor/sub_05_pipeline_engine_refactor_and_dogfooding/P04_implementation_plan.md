# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 API 規格書皆有明確類別與函式對應（`ResultFormatter`, `IndexingPipeline`, `KnowledgeEngine`, `UniversalRedundancyFilter`）
- [x] **邊界防護**：EC-01 ~ EC-05 具備空值、未找到符號、8,000 字元截斷與切片保底防禦
- [x] **依賴純淨**：符合 NFR-01（行數 $\le 450$ 行）、NFR-02（121 測試 100% 通過）、NFR-03（軌道 A 守門）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 更新解耦後 Pipeline 與 Formatter 架構說明、全域切片去重與 Milestone 5 結案 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `[DN-12]`：Pipeline 解耦、全域重複資訊剔除與 8,000 字元極致資訊密度 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 sub_05 流水線解耦、切片純化與主計畫結案變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：`engine.py` 瘦身後，外部依賴或測試是否可能因導入路徑變更而引發 `ImportError`？  
> 💡 **防護解法**：`KnowledgeEngine` 及常見輔助常數（`AUTO_BUDGET_CHARS`、`compute_dynamic_snippet_lines`）於 `engine.py` 保留向後相容轉發匯出，所有既有 `from .engine import ...` 或 `from knowledge_db import KnowledgeEngine` 100% 保持相容。

> ❓ **尖銳問題 2**：`UniversalRedundancyFilter` 智慧剔除是否可能過度積極，誤刪短函式中的可執行代碼或導致切片空白？  
> 💡 **防護解法**：嚴格依據語法特徵（成對三引號、區塊註解、Markdown `#` 開頭、License 關鍵字）匹配，絕不誤刪常規陳述式；並實作 EC-05 殘缺防禦：永遠保護目標焦點行（`target_line`），確保切片絕對不會回傳無效空區塊。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：實作 `formatter.py`（含 `UniversalRedundancyFilter`、8,000 字元動態衰減計算器、`ResultFormatter`），自 `engine.py` 完整抽離 CLI/Markdown 呈現邏輯
- [ ] **TASK-02**：實作 `pipeline.py`（含 `IndexingPipeline`），自 `engine.py` 完整抽離多空間倒排與向量索引建置、JIT 增量熱補丁修復與快取管理
- [ ] **TASK-03**：重構 `engine.py` 瘦身為輕量 Facade（目標 $\le 450$ 行），注入 `pipeline` 與 `formatter`，維持 100% 既有 Public API 簽名
- [ ] **TASK-04**：擴充 `tests/test_engine.py` 單元測試（涵蓋全域去重、8,000 字元衰減與 Pipeline），執行 `python yscb.py dev test knowledge-db --quiet` 驗證 121 測試 100% 通過、0 Unknown
- [ ] **TASK-05**：實機核驗 CLI 契約（`search`、`callers`、`callees`、`impact`、`status`）純文字與 `--json` 格式
- [ ] **TASK-06**：執行 `python yscb.py install knowledge-db@build --force` 完成本地物化更新與真實代碼庫檢索端到端閉環
- [ ] **TASK-DOC**：更新 `docs/knowledge-db/README.md`、登記 `docs/knowledge-db/DESIGN_NOTES.md` (DN-12) 與全域 `CHANGELOG.md`

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零破壞漸進式重構**：遵循 4 步拓撲順序（Formatter ➔ Pipeline ➔ Engine Facade ➔ Test & Dogfooding），確保每一步皆可在乾淨狀態編譯與回歸測試。
