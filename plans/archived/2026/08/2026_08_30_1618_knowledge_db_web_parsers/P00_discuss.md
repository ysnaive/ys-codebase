# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 模組 Web 語言解譯器 (JS/TS/HTML/CSS Parsers)  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：幫 knowledge db 模組添加 js/ts/html/css 解譯器
- **核心目標**：為 `knowledge-db` 模組擴充 JavaScript, TypeScript, HTML, CSS 語意解析器 (Parsers)，支援 `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`, `.cts`, `.html`, `.htm`, `.css`, `.scss`, `.less` 等 Web 前端技術棧檔案的 AST / 狀態機符號萃取與 JIT 倒排索引檢索。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁引進外部二進位 / C-extension 或 Node.js process 依賴（如 tree-sitter, babel 等），100% 採用 Python 原生標準庫狀態機與正則語意掃描。
  - 暫不包含 WebAssembly (`.wasm`) 或 SourceMap 逆向反編譯。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 獨立模組化解析器架構**：採用分拆獨立解析器方案，分別建立 `JsTsParser` (`js_ts_parser.py`)、`HtmlParser` (`html_parser.py`) 與 `CssParser` (`css_parser.py`)，貫徹單一職責原則 (SRP)。
- **[P00:DR-02] LanguageType Enum 擴充**：於 `schema.py` 之 `LanguageType` 新增 `JAVASCRIPT = "javascript"`、`TYPESCRIPT = "typescript"`、`HTML = "html"`、`CSS = "css"`。
- **[P00:DR-03] 零外部依賴與純 Python 狀態機**：基於 Universal Ctags 與 TextMate 階層 Pattern 經驗，運用 Python 原生 `re` 與狀態機進行符號提取與 JSDoc/HTML/CSS 註解連結，確保極速與 100% 沙盒相容性。

---

## 3. 開放議題與確認紀錄

- [x] 分拆獨立解析器方案已獲開發者確認。
- [x] Level 1 (Full Track) 開發計畫立項已獲開發者確認。
