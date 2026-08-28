# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 子計畫 02: 多語言解析與語意打包 (Parsers & Semantic Bundler)  
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

- [x] **需求對齊**：FR-01 ~ FR-10 在 `P03_api_spec.md` 中均有對應抽象介面、類別實作與 CLI 指令。
- [x] **邊界防護**：EC-01 ~ EC-08 在 Python AST 容錯、未知副檔名略過、Markdown 降級與原子寫入中均有明確防禦。
- [x] **依賴純淨**：NFR-01 ~ NFR-04 承諾 100% Python 原生標準庫（零外部 C/Python 套件依賴）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2 (指南)** | `docs/knowledge-db/parsers.md` | **New** | 多語言解析器架構、AST 提取細節與自訂 Parser 外掛擴充指南 |
| **維度 3 (架構)** | `docs/knowledge-db/bundler.md` | **New** | `SemanticBundle` 資料規範、打包流程與離線可攜式導出/導入手冊 |
| **維度 1 (概覽)** | `docs/knowledge-db/README.md` | **Modify** | 更新 sub_02 演進里程碑與 CLI `bundle` 指令用法 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：當解析大型原始碼庫中存在大量語法未完工、非 UTF-8 或格式異常的檔案時，如何保證解析器群不崩潰且記憶體不外洩？**  
> 💡 **防護解法**：每個 Parser 內部均實作頂層異常防禦；PythonParser 專屬捕獲 `SyntaxError`，正則解析器設定最大回溯限制；所有檔案讀取統一使用 `utf-8` + `errors="replace"`；解析以串流方式生成符號清單，不持久持有 AST 物件，確保記憶體即時釋放。

> ❓ **尖銳問題 2：當導出包含數萬個符號的龐大 Bundle 檔案時，若寫入過程遭遇進程終止或儲存空間不足，如何防止毀損既有快取？**  
> 💡 **防護解法**：`export_bundle` 採用同目錄暫存檔 (`tempfile.mkstemp`) 序列化完成後，透過 `os.replace` 原子替換目標檔案；若序列化過程出錯，在 `finally` 區塊強制銷毀暫存檔，保證目標 Bundle 要麼完整生成、要麼維持原樣，絕對不留下半截殘損檔案。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (解析器基礎抽象)**：實作 `source/knowledge-db/knowledge_db/parsers/base.py`，定義 `BaseParser` 抽象類別。
- [ ] **TASK-02 (四大多元解析器實作)**：
  - 實作 `source/knowledge-db/knowledge_db/parsers/python_parser.py` (AST 語法樹解析)
  - 實作 `source/knowledge-db/knowledge_db/parsers/markdown_parser.py` (文檔狀態機解析)
  - 實作 `source/knowledge-db/knowledge_db/parsers/cpp_parser.py` (C/C++ 類別/巨集狀態機解析)
  - 實作 `source/knowledge-db/knowledge_db/parsers/csharp_parser.py` (C# 類別/XML Doc 狀態機解析)
- [ ] **TASK-03 (解析器註冊中心)**：實作 `source/knowledge-db/knowledge_db/parsers/registry.py` 與 `parsers/__init__.py`，提供動態註冊與分發調度。
- [ ] **TASK-04 (語意打包引擎)**：實作 `source/knowledge-db/knowledge_db/bundler.py`，包含 `SemanticBundle` 資料模型與 `SemanticBundler` 打包/導出/導入引擎。
- [ ] **TASK-05 (入口與元數據更新)**：更新 `source/knowledge-db/scripts/cli.py`（擴充 `bundle` 指令）、`manifest.json` 與 `knowledge_db/__init__.py`。
- [ ] **TASK-06 (單元測試套件)**：實作 `tests/test_parsers.py` 與 `tests/test_bundler.py`，覆蓋 FT-01~08、ET-01 與 RT-01。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿實作計畫與測試清單**：確認 Phase 1~3 規格與依賴拓撲無誤，同步定稿 `P06_test_plan.md` 為 `Confirmed`，進入 Phase 5 編碼實作。
