# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_three_tier_weighted_expansion  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 三階加權資料模型 (`WeightedToken`) | 定義 `WeightedToken` 資料結構，包含 `term: str` (小寫規格化詞條)、`weight: float` (展開衰減權重)、`kind: str` (`"original"`, `"synonym"`, `"alias"`, `"related"`)。`ThesaurusConfig` 擴充支援 `aliases` 與 `related` 欄位。 | P0 | [P00:DR-01] |
| **FR-02** | 單向別名展開機制 (Directed Aliases) | `ThesaurusEngine` 支援 `add_alias(source: str, targets: List[str])`。當查詢輸入包含 `source` 時，展開 `targets`（權重 0.6，kind="alias"）；若輸入為 `target` 則不反向展開 `source`。 | P0 | [P00:DR-01] |
| **FR-03** | 領域關聯詞擴展機制 (Related Terms) | `ThesaurusEngine` 支援 `add_related_group(group: List[str])`。於群組內詞條建立雙向關聯映射，展開時權重設為 0.25 (kind="related")。 | P0 | [P00:DR-01] |
| **FR-04** | 加權查詢展開引擎介面 (`expand_query_weighted`) | 實作 `ThesaurusEngine.expand_query_weighted(tokens: List[str], max_expanded: int = 50, include_related: bool = True) -> List[WeightedToken]`，依序進行 Tier 1 (1.0) ➔ Tier 2 (0.6) ➔ Tier 3 (0.25) 擴展與去重，並保留既有 `expand_query(tokens)` 100% 向後相容。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-05** | 加權 BM25 計分引擎重構 (`BM25Engine`) | `BM25Engine.search()` 整合 `expand_query_weighted()`，單一候選詞 term BM25 得分乘以該詞條之 `weight`：`term_score = idf * field_scores_sum * weighted_token.weight`，精確匹配 Exact Match 維持 2.0x 置頂加權。 | P0 | [P00:DR-01] |
| **FR-06** | Contributes 載入器擴充 (`SpaceManager`) | `SpaceManager.load_thesaurus()` 支援解析並載入 contributes 資料中的 `thesaurus` (雙向同義詞)、`aliases` (單向別名) 與 `related` (領域關聯詞)。 | P1 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 循環與遞迴別名/同義詞 (Cycle Prevention) | 當詞庫存在 A => B 且 B => A 或 A <=> B <=> C 等循環關係時，透過單步展開與 `seen` 集合追蹤，絕對杜絕無窮迴圈與重複項。 |
| **EC-02** | 權重衝突與優先級防護 (Max-Weight Retention) | 當同一個詞條同時符合多種擴展路徑（例如既是原始詞 1.0，又被其他詞展開為同義詞 0.6 或關聯詞 0.25），強制保留最高權重（1.0 > 0.6 > 0.25）。 |
| **EC-03** | 空輸入、空白字元與畸形字串防禦 | 輸入包含 None、空字串、純空白字元或特殊字元時，自動規格化為純小寫 strip 字串，無效項目安全略過，不引發異常。 |
| **EC-04** | 數量截斷與層級優先級保護 | 當展開詞條總數達到 `max_expanded` 上限時進行截斷，展開過程嚴格依據 Tier 1 > Tier 2 > Tier 3 優先納入高權重詞條。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與零第三方依賴 | 保持 100% Python 標準庫實作，單次查詢擴展 (50 tokens) 執行時間小於 0.5ms，BM25 加權計分時間無顯著膨脹 (< 5%)。 |
| **NFR-02** | 100% 向後相容性 | 既有公開 API（如 `ThesaurusEngine.expand_query()`、`BM25Engine.search()` 簽名）完全保持向後相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 
  - `ThesaurusEngine.expand_query` 目前已被 `BM25Engine` 及多個單元測試廣泛引用，新加權介面應作為首選，但舊介面需無損包裝轉調新方法。
  - Exact Match 置頂加權 (2.0x) 是直接作用於最終聚合的 `base_score`，不受中間詞條 weight 稀釋。
