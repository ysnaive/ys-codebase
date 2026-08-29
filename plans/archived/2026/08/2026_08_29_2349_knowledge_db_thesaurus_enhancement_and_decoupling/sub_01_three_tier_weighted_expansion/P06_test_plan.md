# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_three_tier_weighted_expansion  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Completed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `WeightedToken` 資料模型與 `ThesaurusConfig` 序列化/反序列化 | FR-01 | `test_weighted_token_and_config` |
| **FT-02** | 單元測試 | 驗證單向別名 `add_alias` 展開正確性 (A => B 有效且 B 不反向展開 A) | FR-02 | `test_directed_aliases` |
| **FT-03** | 單元測試 | 驗證領域關聯詞 `add_related_group` 雙向關聯展開 (權重 0.25, kind="related") | FR-03 | `test_related_terms_expansion` |
| **FT-04** | 單元測試 | 驗證三階加權展開 `expand_query_weighted` 之展開順序與權重指派 | FR-04 | `test_expand_query_weighted_tiers` |
| **FT-05** | 單元測試 | 驗證 BM25 加權計分：原始詞匹配文檔得分 > 同義詞匹配 > 關聯詞匹配 | FR-05 | `test_bm25_weighted_scoring_ranking` |
| **FT-06** | 單元測試 | 驗證 `SpaceManager.load_thesaurus()` 正確聚合 contributes 中的同義詞、別名與關聯詞 | FR-06 | `test_space_manager_thesaurus_loading` |
| **ET-01** | 邊界測試 | 驗證同義詞/別名循環 (A=>B=>A) 之單步展開與防無窮迴圈機制 | EC-01 | `test_cycle_and_infinite_loop_prevention` |
| **ET-02** | 邊界測試 | 驗證多重路徑衝突時之最高權重保留 (Max-Weight Retention, 1.0 > 0.6 > 0.25) | EC-02 | `test_max_weight_conflict_retention` |
| **ET-03** | 邊界測試 | 驗證空值、純空白字元與畸形字串之邊界安全防護 | EC-03 | `test_malformed_and_empty_inputs` |
| **ET-04** | 邊界測試 | 驗證 `max_expanded` 數量截斷時優先保留高權重詞條 | EC-04 | `test_max_expanded_tier_prioritization` |
| **RT-01** | 回歸測試 | 驗證 `knowledge-db` 既有全部單元測試 100% Passed (向後相容驗證) | NFR-02 | `python yscb.py dev test knowledge-db` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestThesaurusWeighted.test_weighted_token_and_config` 通過 | 2026-08-29 23:54 |
| **FT-02** | `Passed` | `TestThesaurusWeighted.test_directed_aliases` (單向展開且反向不展開) 通過 | 2026-08-29 23:54 |
| **FT-03** | `Passed` | `TestThesaurusWeighted.test_related_terms_expansion` (權重 0.25) 通過 | 2026-08-29 23:54 |
| **FT-04** | `Passed` | `TestThesaurusWeighted.test_expand_query_weighted_tiers` 通過 | 2026-08-29 23:54 |
| **FT-05** | `Passed` | `TestThesaurusWeighted.test_bm25_weighted_scoring_ranking` (原始詞 > 同義詞 > 關聯詞) 通過 | 2026-08-29 23:54 |
| **FT-06** | `Passed` | `TestThesaurusWeighted.test_space_manager_thesaurus_loading` 通過 | 2026-08-29 23:54 |
| **ET-01** | `Passed` | `TestThesaurusWeighted.test_cycle_and_infinite_loop_prevention` 通過 | 2026-08-29 23:54 |
| **ET-02** | `Passed` | `TestThesaurusWeighted.test_max_weight_conflict_retention` (1.0 優先保留) 通過 | 2026-08-29 23:54 |
| **ET-03** | `Passed` | `TestThesaurusWeighted.test_malformed_and_empty_inputs` (安全略過) 通過 | 2026-08-29 23:54 |
| **ET-04** | `Passed` | `TestThesaurusWeighted.test_max_expanded_tier_prioritization` 通過 | 2026-08-29 23:54 |
| **RT-01** | `Passed` | 全套件 75/75 Passed (100% Ready, 2.381s), 合規性檢查 100% Passed | 2026-08-29 23:54 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：開發者指示免測，全自動化測試套件 75/75 Passed (100% Ready) 驗收通過。
