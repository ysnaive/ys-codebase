# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_three_tier_weighted_expansion  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 `P03_api_spec.md` 中均有具體型別與函式簽名承接。
- [x] **邊界防護**：EC-01 (循環展開)、EC-02 (權重衝突)、EC-03 (畸形字串)、EC-04 (截斷保護) 均已定義具體防禦。
- [x] **依賴純淨**：100% Python 標準庫，零外部套件引入 (NFR-01)；Public API 完全向後相容 (NFR-02)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- :--- | :--- | :---: | :--- |
| **維度 2** | `docs/knowledge-db/tokenizer.md` | Modify | 更新分詞與同義詞說明，新增三階加權展開 (Weighted Token) 與單向別名/關聯詞說明。 |
| **維度 3** | `docs/knowledge-db/retrieval.md` | Modify | 更新檢索引擎說明，加入加權 BM25 計分公式與衰減係數定義。 |
| **維度 4** | `docs/knowledge-db/contributes.format.md` | Modify | 補充 `thesaurus`、`aliases`、`related` 宣告式格式範例。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若查詢詞既出現在使用者的輸入（Tier 1，權重 1.0），又被某個詞展開為同義詞（Tier 2，權重 0.6）與關聯詞（Tier 3，權重 0.25），是否會導致權重被降級覆蓋或重複計分？  
> 💡 **防護解法**：展開器內部使用字典 `best_tokens: Dict[str, WeightedToken]` 進行維護。新展開的候選詞僅在 `new_weight > best_tokens[term].weight` 時更新權重，確保原始詞 1.0 的最高權重絕不被次級展開覆蓋，且每個詞在 `BM25Engine` 中僅出現一次、不重複累加。

> ❓ **尖銳問題 2**：若存在單向別名互相指向（如 A => B, B => A）或自環（A => A），展開狀態機是否會發生無窮遞迴？  
> 💡 **防護解法**：`expand_query_weighted` 採用單步寬度展開 (Single-step Breadth Expansion)，而非遞迴深搜；且展開時以全域 `seen: Set[str]` 集合過濾，任何已處理過的詞條絕不發起二次擴展，徹底杜絕循環。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/knowledge-db/knowledge_db/schema.py` 定義 `WeightedToken` 與升級 `ThesaurusConfig`（含序列化/反序列化）。
- [ ] **TASK-02**：在 `source/knowledge-db/knowledge_db/thesaurus.py` 實作 `ThesaurusEngine` 三階加權展開、別名與關聯詞擴展方法。
- [ ] **TASK-03**：在 `source/knowledge-db/knowledge_db/space.py` 升級 `SpaceManager.load_thesaurus` 與 `load_thesaurus_config`。
- [ ] **TASK-04**：在 `source/knowledge-db/knowledge_db/retrieval.py` 重構 `BM25Engine.search` 整合 Token 權重衰減計分。
- [ ] **TASK-05**：在 `source/knowledge-db/tests/test_thesaurus_weighted.py` 編寫完整單元測試覆蓋 FT-01~FT-06 與 ET-01~ET-04。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立三階加權展開採用單步去重與 Max-Weight 保留演算法，BM25 計算直接於 term 得分注入衰減權重。
