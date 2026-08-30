# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 模組 Web 語言解譯器 (JS/TS/HTML/CSS Parsers)  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Draft  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `LanguageType` Enum 擴充 | 於 `schema.py` 新增 `JAVASCRIPT = "javascript"`、`TYPESCRIPT = "typescript"`、`HTML = "html"`、`CSS = "css"`。 | P0 | [P00:DR-02] |
| **FR-02** | `JsTsParser` 解譯器 | 支援 `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`, `.cts`；提取 Class, Interface, Type Alias, Enum, Function, Arrow Function, Class Method，並連動 JSDoc/TSDoc 註解。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-03** | `HtmlParser` 解譯器 | 支援 `.html`, `.htm`；提取網頁 Title (`<title>`)、標題結構 (`<h1>`~`<h6>`)、帶 `id="..."` 之元素、HTML5 語意區塊 (`<main>`, `<article>` 等) 及註解。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | `CssParser` 解譯器 | 支援 `.css`, `.scss`, `.less`；提取 Class 選擇器 (`.btn`)、ID 選擇器 (`#app`)、CSS 變數 (`--var`)、SASS/LESS 變數 (`$var`, `@var`)、Keyframes 動畫 (`@keyframes`) 及 CSS 註解。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-05** | `ParserRegistry` 註冊與 CLI 過濾相容 | 將三項新解析器於 `ParserRegistry` 預設註冊（優先級 100）；`knowledge-db search` CLI 支援 `--ftype=js,ts,html,css` 過濾。 | P0 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 多行樣板字串 (`` `...` ``) 或正則字面量包含關鍵字 | 狀態機掃描時防範樣板字串內的大括弧與關鍵字，避免將字串內容誤判為類別或函式。 |
| **EC-02** | TSX / JSX 標籤與 TS 泛型 `<T>` 混淆 | 比對識別標籤與型別參數語境，防禦 JSX 標籤與 TypeScript 泛型宣告之歧義衝突。 |
| **EC-03** | HTML 自閉合標籤與非規範語法 | 容錯處理 `<img />`, `<br>`, `<input>` 等自閉合標籤及遺失閉合標籤之惡意/非正規 HTML 檔案。 |
| **EC-04** | CSS 媒體查詢 (`@media`) 與 SASS 多層嵌套 | 維護 `{}` 括號深度堆疊，避免深層選擇器或 `@media` / `@supports` 區塊破壞解析器結構。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴與極速 | 100% 採用 Python 原生標準庫實現（0 外部 C/DLL 與 0 Node.js 依賴），單檔解析平均耗時 $< 5\text{ms}$。 |
| **NFR-02** | 測試覆蓋率與合規性 | 新增 `test_web_parsers.py` 單元測試，全模組與全生態系跑測 100% Passed，`dev check knowledge-db` 靜態合規性 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 參考 `SpiceParser` 與 `CppParser` 之多行簽名狀態機與正則優先級匹配模式，確保 `ParserRegistry.get_parser` 精準匹配。
