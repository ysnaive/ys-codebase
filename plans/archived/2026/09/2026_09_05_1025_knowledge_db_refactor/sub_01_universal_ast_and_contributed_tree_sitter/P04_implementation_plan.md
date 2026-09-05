# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_universal_ast_and_contributed_tree_sitter  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-07 在 P03 API 規格書中均有明確對應之型別與方法契約
- [x] **邊界防護**：EC-01 ~ EC-05 具備完整的 Error Recovery、依賴缺失隔離與遞迴防禦設計
- [x] **依賴純淨**：相依性嚴格宣告於 `source/knowledge-db/manifest.json`，由 `yscb.venv` 治理，無全域污染

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/_project/STANDARDS.md` | Modify | 更新 Universal AST 概念與 contributes 外掛註冊規範說明 |
| **專題手冊** | `source/knowledge-db/README.md` | Modify | 說明 Tree-sitter S-Expression 擴充規範與自貢獻機制 |
| **設計決策** | `plans/.../P00_discuss.md` | Recorded | 登記 DR-01~DR-06 各項架構決策與邊界防護 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：若專案環境未編譯或無法安裝某語言的 Tree-sitter Grammar，是否會造成整個 knowledge-db 掃描癱瘓？**  
> 💡 **防護解法**：`LanguageRegistry` 採用懶加載與隔離容錯設計（EC-02）。當某語言之 grammar 載入失敗時，捕獲 `ImportError` 並登記警告日誌，該副檔名自動略過或退化，其餘語言檔案維持 100% 正常解析。

> ❓ **尖銳問題 2：移除舊手刻 parsers 後，舊有的單元測試（如 test_parsers.py）會不會引發大量 ImportError 或測試失敗？**  
> 💡 **防護解法**：依據使用者明確指示（FR-07 / DR-03），在實作過程中將舊手刻正則 parsers 檔案與針對私有手刻正則的過時測試用例進行徹底清理，重構為基於 `Universal AST` 與 `TreeSitterDriver` 的現代測試套件，確保測試套件 100% 通過。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/knowledge-db/manifest.json` 宣告 `pip_dependencies` (`tree-sitter` 等相依性)
- [ ] **TASK-02**：重構 `knowledge_db/schema.py`，實作遞迴 `UnifiedSymbol` (FQN, parameters, search_payload) 與相容適配層
- [ ] **TASK-03**：實作 `knowledge_db/parsers/base.py` 抽象介面與 `knowledge_db/parsers/treesitter.py` 通用驅動器
- [ ] **TASK-04**：建立各語言 S-Expression 查詢規則資產 (`assets/queries/*.scm`)
- [ ] **TASK-05**：重構 `knowledge_db/parsers/registry.py`，實作基於 `contributes` 的動態 `LanguageRegistry`
- [ ] **TASK-06**：在 `contributes/knowledge-db.json` 宣告自身語言能力自貢獻 (Zero-Privilege Dogfooding)
- [ ] **TASK-07**：徹底清理 `parsers/` 下手刻正則檔案，並改寫/清理 `tests/` 中的過時測試案例
- [ ] **TASK-08**：跑測單元/邊界測試 (FT-01~07, ET-01~05) 並完成全系統回歸

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 確立由底而上的單向實作拓撲**：Schema ➔ Drivers ➔ SCM Queries ➔ Registry ➔ Contributes ➔ Legacy Cleanup ➔ Tests。
- **[P04:DR-02] 測試資產淨化**：徹底廢除舊正則測試，改為驗證 Universal AST 階層結構、FQN 精度與容錯表現。
