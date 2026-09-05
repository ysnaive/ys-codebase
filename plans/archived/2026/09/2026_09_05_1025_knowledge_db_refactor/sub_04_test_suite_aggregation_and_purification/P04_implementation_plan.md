# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_04_test_suite_aggregation_and_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在架構與介面規格書中有具體整併映射與方法契約
- [x] **邊界防護**：EC-01 ~ EC-04 包含 `__pycache__` 清除、Fixture 獨立臨時目錄、多進程鎖隔離
- [x] **依賴純淨**：NFR-01 ~ NFR-03 約束測試檔 <= 12、Unknown: 0、快測耗時 <= 3.5s

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 更新測試架構章節，說明 4-Tier 測試分流與整併後之測試套件目錄 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 DN-11 測試套件聚合拓撲與三態分類純化規範 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 sub_04 測試套件整併、Unknown 根絕與 4-Tier 分流落地 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：整併測試檔案時，不同測試類別中的 `setUp` 或全局 Mock 若命名重疊，是否會造成跨案例污染或偶發失敗？  
> 💡 **防護解法**：各測試類別保持獨立 Class 定義，測試臨時目錄嚴格封裝於各 TestCase 內之 `tempfile.TemporaryDirectory` 上下文，不依賴模組級別全局共享狀態。
>
> ❓ **尖銳問題 2**：若某些邊界測試因被判定為「過時正則」而誤刪，如何防止業務邏輯出現防禦空窗？  
> 💡 **防護解法**：遵循「純化非破壞」原則，僅刪除已被 AST 完全取代且已無相關實作程式碼的 dead tests（例如早已廢棄的舊 regex token lexer），所有涉及 AST 解析、語義選擇、圖譜分析與檢索的斷言 100% 完整保留並移入整併後的新套件中。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：整併圖譜測試套件 (`test_call_graph.py` + `test_networkx_graph.py` ➔ `test_graph.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [ ] **TASK-02**：整併解析器測試套件 (`test_spice_parser.py` + `test_web_parsers.py` ➔ `test_parsers.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [ ] **TASK-03**：整併檢索與聚合測試套件 (`test_search_aggregation.py` ➔ `test_retrieval.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [ ] **TASK-04**：整併熱重載與 JIT 修復測試套件 (`test_incremental_hot_reload.py` + `test_jit_hot_healing.py` ➔ `test_hot_reload.py`)，補齊 `self.mark_passed()`，刪除舊檔
- [ ] **TASK-05**：全面盤點現存獨立套件 (`test_selector.py`, `test_hybrid.py`, `test_tokenizer.py`, `test_schema.py`, `test_space.py`, `test_providers.py`, `test_cli.py`)，補齊所有測試方法的 `self.mark_passed()`
- [ ] **TASK-06**：為重型套件 (`test_engine.py`, `test_scanner.py`, `test_bundler.py`) 標註 `@require(Requirement.WORKFLOW)`，為 `test_benchmark_perf_and_memory.py` 標註 `@require(Requirement.PERF)`，並補齊 `self.mark_passed()`
- [ ] **TASK-07**：清理舊測試之 `__pycache__`，執行 `dev test knowledge-db --quiet` 驗證 100% 通過、0 Unknown、0 Fail，並更新 docs/ 與 changelog

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 嚴格三態分類與 0 Unknown 保證**：全測試案例方法必須顯式執行 `self.mark_passed()`，不允許任何方法遺漏。
- **[P04:DR-02] 4-Tier 分流標註標準**：日常快測運行 LOGIC，多進程/重磁碟操作運行 WORKFLOW，壓測運行 PERF。
