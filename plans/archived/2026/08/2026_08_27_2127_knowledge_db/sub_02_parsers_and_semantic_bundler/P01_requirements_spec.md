# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 子計畫 02: 多語言解析與語意打包 (Parsers & Semantic Bundler)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 / 決策 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **解析器基礎抽象 (`BaseParser`)** | 定義解析器抽象基底類別 `BaseParser`，規範 `can_parse(file_path: Union[str, Path]) -> bool` 與 `parse(file_path: str, content: str, space: str) -> List[UnifiedSymbol]` 抽象介面契約。 | P0 | [P00:DR-01] |
| **FR-02** | **動態外掛解析器註冊表 (`ParserRegistry`)** | 實作 `ParserRegistry`，支援 `register_parser(parser, priority)` 註冊、優先權覆蓋、`get_parser(file_path)` 依副檔名/特徵比對分發，以及 `parse_file(file_path, content, space)` 批次調度。預設自動註冊 Python、Markdown、C++、C# 四大內建解析器。 | P0 | [P00:DR-01] |
| **FR-03** | **Python 原生 AST 語意解析器 (`PythonParser`)** | 使用 Python 原生 `ast` 模組解析 `.py` / `.pyi` 原始碼。提取 Class、Function、AsyncFunction、Method、Decorator、Docstring、Signature（含型別標註與預設值）與成員清單 (`MemberInfo`)，精確標註行號。 | P0 | [P00:DR-02] |
| **FR-04** | **Markdown 文檔語意解析器 (`MarkdownParser`)** | 實作輕量狀態機解析 `.md` / `.markdown` 文檔。提取 H1~H4 標題節點 (`DOC_HEADING_1` ~ `DOC_HEADING_4`)，收斂所屬區間內文摘要至 `docstring`；提取表格 (`DOC_TABLE`) 與程式碼區塊。 | P0 | [P00:DR-02] |
| **FR-05** | **C/C++ 語意狀態機解析器 (`CppParser`)** | 實作語意狀態機解析 `.cpp` / `.hpp` / `.h` / `.c` / `.cc` 原始碼。提取 Class、Struct、Enum、Function、Macro（巨集定義/宣告）與 Doxygen 註解（`/** */`, `///`）。 | P0 | [P00:DR-02] |
| **FR-06** | **C# 語意狀態機解析器 (`CSharpParser`)** | 實作語意狀態機解析 `.cs` 原始碼。提取 Namespace、Class、Interface、Struct、Enum、Method、Property 與 XML `<summary>` 註解。 | P0 | [P00:DR-02] |
| **FR-07** | **語意打包資料模型 (`SemanticBundle`)** | 實作不可變 `SemanticBundle` 模型，包含 `version`, `space_name`, `created_at`, `symbols: List[UnifiedSymbol]`, `thesaurus: List[ThesaurusGroup]`, `metadata: Dict[str, Any]`，支援無損 `to_dict()` 與 `from_dict()` 序列化。 | P0 | [P00:DR-03] |
| **FR-08** | **語意打包與解包引擎 (`SemanticBundler`)** | 實作 `SemanticBundler`：<br/>1. `bundle_space(space_config, scanner, parser_registry)`：掃描並解析空間所有有效檔案，打包符號與同義詞。<br/>2. `export_bundle(bundle, target_path=None)`：以原子寫入方式導出 `.bundle.json`。<br/>3. `import_bundle(bundle_path)`：載入並反序列化 Bundle 檔案。 | P0 | [P00:DR-03] |
| **FR-09** | **解析容錯與語法降級防禦** | 當解析器遭遇無效語法（如 Python `SyntaxError`）、不支援副檔名或非 UTF-8 字元時，記錄 Warning 日誌並安全降級回傳空符號清單，嚴禁引發未捕獲例外導致整體批次解析崩潰。 | P0 | [P00:DR-02] |
| **FR-10** | **CLI 指令支援 (`bundle`)** | 在 `scripts/cli.py` 擴充 `bundle [space | --all] [--output=path]` 指令，支援命令列一鍵打包導出空間語意 Bundle。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **Python 檔案包含語法錯誤 (SyntaxError)** | `PythonParser` 捕獲 `SyntaxError`，記錄 Warning 日誌並回傳空清單，其餘合法檔案正常解析。 |
| **EC-02** | **檔案副檔名無任何註冊之 Parser 匹配** | `ParserRegistry.get_parser` 回傳 `None`；`parse_file` 記錄 Debug 日誌並回傳空清單，不拋出未處理例外。 |
| **EC-03** | **Markdown 檔案無任何標題（純文字或僅段落）** | `MarkdownParser` 降級將首段或全篇提取為單一 `SymbolKind.DOC_SECTION` 符號節點，確保文檔內容不遺失。 |
| **EC-04** | **C/C++ 或 C# 檔案包含巢狀類別或複合巨集** | 狀態機遞迴/階層追蹤類別與命名空間前綴（如 `OuterClass::InnerClass` 或 `Namespace.Class`），正確標註父級結構。 |
| **EC-05** | **Bundle 檔案損毀或版本不相容** | `SemanticBundler.import_bundle` 捕獲 `JSONDecodeError` 或版本缺失時，拋出結構化 `KnowledgeDBError`。 |
| **EC-06** | **檔案包含特殊編碼或非 UTF-8 字元** | 統一採用 `utf-8` 搭配 `errors="replace"` 安全解碼。 |
| **EC-07** | **Bundle 導出目錄不存在或遭寫入中斷** | `export_bundle` 自動建立父層目錄，並採用同目錄暫存檔 + `os.replace` 原子替換保證檔案完整性。 |
| **EC-08** | **解析大型原始碼檔案（>10,000 行）** | 原生 `ast` 與純字串狀態機保證高吞吐量解析，單檔解析時間控制於 `< 50ms`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **零外部相依 (Zero External Dependency)** | 100% 採用 Python 3.9+ 原生標準庫（`ast`, `re`, `json`, `pathlib`, `dataclasses` 等），嚴禁引入第三方相依（如 tree-sitter, markdownit 等）。 |
| **NFR-02** | **解析效能與記憶體效率** | 純原生 AST 與狀態機實現，1,000 個原始碼檔案解析與打包總耗時 `< 2.0s`。 |
| **NFR-03** | **測試品質守門** | 單元測試 100% 繼承 `YSCBTestCase`，覆蓋所有 Parser 與 Bundler，模組跑測 100% Passed。 |
| **NFR-04** | **模組邊界與 Dogfooding** | 源碼 100% 位於 `source/knowledge-db/`，路徑存取透過 Core URI 協議。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!IMPORTANT]
  > **零外部相依解析實踐**：嚴格禁止引入 tree-sitter 或其他 C 擴展庫，Python 使用原生 `ast`，其他語言使用經過嚴格邊界測試之正則語意狀態機。

- > [!WARNING]
  > **Bundle 導出原子性**：Bundle 檔案可能包含全專案數萬個符號，寫入必須使用暫存檔原子替換，防止寫入中斷導致 Bundle 不完整。
