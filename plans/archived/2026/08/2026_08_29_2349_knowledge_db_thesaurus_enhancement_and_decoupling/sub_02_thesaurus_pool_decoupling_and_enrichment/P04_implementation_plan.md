# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_thesaurus_pool_decoupling_and_enrichment  
> 建立日期：2026-08-30  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 `P03_api_spec.md` 中均有具體型別與函式簽名承接。
- [x] **邊界防護**：EC-01 (空 Contributes)、EC-02 (重複詞去重)、EC-03 (向後相容) 均已定義具體防禦。
- [x] **依賴純淨**：100% Python 標準庫，零業務詞彙硬編碼 (NFR-01)；載入耗時 $< 2\text{ ms}$ (NFR-02)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **維度 2** | `docs/knowledge-db/tokenizer.md` | Modify | 更新詞庫載入方式說明：由 `SpaceManager.create_thesaurus_engine()` 動態裝配。 |
| **維度 4** | `docs/knowledge-db/contributes_guide.md` | Modify | 更新六大維度初始詞庫宣告說明與範例。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：將 `BUILTIN_THESAURUS` 從 `thesaurus.py` 刪除後，既有獨立測試若呼叫 `ThesaurusEngine()` 是否會因為缺乏詞庫而產生行為漂移？  
> 💡 **防護解法**：`ThesaurusEngine()` 自身定位為純粹容器，其單元測試若需測試特定詞庫應傳入 `custom_groups` 或由 `SpaceManager.create_thesaurus_engine()` 建立；同時在 `test_tokenizer.py` 與 `test_thesaurus_weighted.py` 中皆已自帶測試群組，不會受到影響。

> ❓ **尖銳問題 2**：`contributes/knowledge-db.json` 包含 6 大維度數百組詞條，是否會在每次 search 時重複解析 JSON 造成 I/O 瓶頸？  
> 💡 **防護解法**：`SpaceManager` 內部具備執行期快取或由上層常駐實例持有已裝配之 `ThesaurusEngine`，且 JSON 體積小於 50 KB，單次記憶體解析耗時小於 1ms。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/knowledge-db/contributes/knowledge-db.json` 建立完整六大維度初始詞彙庫。
- [ ] **TASK-02**：在 `source/knowledge-db/knowledge_db/thesaurus.py` 徹底移除 `BUILTIN_THESAURUS`，將 `ThesaurusEngine` 重構為純容器。
- [ ] **TASK-03**：在 `source/knowledge-db/knowledge_db/space.py` 實作 `create_thesaurus_engine()` 工廠方法。
- [ ] **TASK-04**：在 `source/knowledge-db/tests/test_thesaurus_decoupling.py` 編寫單元測試覆蓋 FT-01~FT-04 與 ET-01~ET-03。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立源碼 100% 詞庫解耦，全面由 `core.contributes` 管道與 `contributes/knowledge-db.json` 驅動。
