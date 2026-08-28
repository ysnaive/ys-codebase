# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 子計畫 03: 分詞、同義詞與 BM25 語意檢索引擎 (Tokenizer, Thesaurus & BM25 Retrieval)  
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

- [x] **需求對齊**：FR-01 ~ FR-08 在 `P03_api_spec.md` 中均有對應類別、方法簽名與 CLI 指令。
- [x] **邊界防護**：EC-01 ~ EC-08 在除以零防禦、空字串保護、IDF 平滑截斷與集合擴展中均有剛性設計。
- [x] **依賴純淨**：NFR-01 ~ NFR-04 承諾 100% Python 原生標準庫（Zero External Dependency）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2 (指南)** | `docs/knowledge-db/tokenizer.md` | **New** | 代碼標識符拆解規則、CJK 滑動窗口分詞與自訂停用詞指南 |
| **維度 3 (架構)** | `docs/knowledge-db/retrieval.md` | **New** | 倒排索引格式、BM25 多欄位加權評分公式、QueryFilter 與檢索效能優化 |
| **維度 1 (概覽)** | `docs/knowledge-db/README.md` | **Modify** | 更新 sub_03 演進里程碑為 Completed，補充 CLI `search` 指令用法 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：當多個同義詞組互相包含或存在環狀交叉定義時，查詢擴展是否會造成死迴圈或詞條爆炸？**  
> 💡 **防護解法**：`ThesaurusEngine` 使用 Python 原生 `set` 進行一次性單步展開（1-hop extension），並對單一查詢總詞條數設定上限（最大 50 個 Token），徹底杜絕環狀循環與組合爆炸。

> ❓ **尖銳問題 2：當空間內所有符號的某個欄位皆為空（例如純代碼庫無 docstring），BM25 計算 $\text{avgdl} = 0$ 時是否會導致除以零例外？**  
> 💡 **防護解法**：在 `InvertedIndex` 與 `BM25Engine` 中，所有 $\text{avgdl}$ 與 $\text{dl}$ 均使用 `max(1.0, val)` 做保護底線，分母計算嚴格套用 $\text{avgdl} = \text{total\_length} / \max(1, \text{doc\_count})$，計算 BM25 時分母額外加上 $\epsilon = 1e-9$，100% 杜絕 `ZeroDivisionError`。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (混合分詞器實作)**：實作 `source/knowledge-db/knowledge_db/tokenizer.py` (`CodeTokenizer`)。
- [ ] **TASK-02 (雙層同義詞引擎實作)**：實作 `source/knowledge-db/knowledge_db/thesaurus.py` (`ThesaurusEngine`)。
- [ ] **TASK-03 (倒排索引與 BM25 評分引擎實作)**：實作 `source/knowledge-db/knowledge_db/retrieval.py` (`InvertedIndex`, `BM25Engine`, `QueryFilter`, `SearchResult`)。
- [ ] **TASK-04 (入口與元數據更新)**：更新 `source/knowledge-db/scripts/cli.py`（擴充 `search` 指令）、`manifest.json` 與 `knowledge_db/__init__.py`。
- [ ] **TASK-05 (單元測試套件)**：實作 `tests/test_tokenizer.py`、`tests/test_thesaurus.py` 與 `tests/test_retrieval.py`，驗收 FT-01~07、ET-01 與 RT-01。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿實作計畫與測試清單**：確認 Phase 1~3 規格與依賴拓撲無誤，同步定稿 `P06_test_plan.md` 為 `Confirmed`，進入 Phase 5 編碼實作。
