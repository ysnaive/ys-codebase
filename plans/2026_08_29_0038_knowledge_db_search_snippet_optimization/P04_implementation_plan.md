# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge_db_search_snippet_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 `P02_architecture_plan.md` 與 `P03_api_spec.md` 中均有對應介面承接。
- [x] **邊界防護**：EC-01 ~ EC-04 在 `SnippetExtractor` 具備檔案缺失降級、行號邊界防禦與編碼容錯處置。
- [x] **依賴純淨**：100% 使用標準庫 `os`, `sys`, `pathlib`, `dataclasses`，無外部依賴 (NFR-01)。
- [x] **Test-First 定稿**：`P06_test_plan.md` 完整映射 FT-01~06 與 ET-01~04 測試案例並定稿為 `Confirmed`。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/knowledge-db/README.md` | Modify | 更新 CLI 快速上手章節，加入 `--snippet` / `-s` 使用範例。 |
| **維度 6** | `docs/knowledge-db/retrieval.md` | Modify | 補充 `SnippetExtractor` 延遲切片提取與 `--snippet` 檢索輸出說明。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：當專案包含數萬個檔案且連續高頻搜尋時，`--snippet` 是否會引發磁碟 I/O 暴增或檔案句柄洩漏？**  
> 💡 **防護解法**：`SnippetExtractor` 僅在 BM25 評分與 Top-K（預設 10 筆）截斷後才針對命中檔案進行延遲讀取；且使用 context manager `with open(...)` 即開即關，檔案讀取開銷限制在 $< 5\text{ ms}$ 且 100% 確保無資源洩漏。

> ❓ **尖銳問題 2：若搜尋命中的檔案是二進位檔案或包含特殊字元導致 UTF-8 解碼失敗，是否會導致 CLI 崩潰？**  
> 💡 **防護解法**：檔案開啟強制指定 `errors="replace"`，若發生例外則安全捕獲並標註 `[Snippet Unavailable: Read error]`，保障 CLI 永不崩潰。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/knowledge-db/knowledge_db/retrieval.py` 實作 `CodeSnippet` 與 `SnippetExtractor`，並擴充 `SearchResult.code_snippet`。
- [ ] **TASK-02**：在 `source/knowledge-db/knowledge_db/engine.py` 更新 `KnowledgeEngine.search` 支援 `snippet` 參數與路徑正規化。
- [ ] **TASK-03**：在 `source/knowledge-db/scripts/cli.py` 新增 `--snippet` / `-s` / `--preview` 解析與終端多行代碼排版渲染。
- [ ] **TASK-04**：更新 `KnowledgeAgentsStandards.md`、`phase00_guild.md`、`research_guild.md` 與 `contributes/core.json` 注入資產。
- [ ] **TASK-05**：在 `source/knowledge-db/tests/test_retrieval.py` 與 `test_cli.py` 新增完整單元測試與邊界測試（FT-01~06, ET-01~04）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 採用 `CodeSnippet` 結構化物件封裝代碼切片，兼顧終端人類視覺手感排版與 `--json` 結構化序列化輸出。
- **[P04:DR-02]** 同步定稿 `P06_test_plan.md` 為 `Confirmed`，實作後立即於虛擬沙盒執行全量回歸驗證。
