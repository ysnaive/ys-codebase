# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 模組 Web 語言解譯器 (JS/TS/HTML/CSS Parsers)  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `LanguageType` 包含 `javascript`, `typescript`, `html`, `css` | FR-01 | `test_web_parsers.py::test_ft_01_language_type_enum` |
| **FT-02** | 單元測試 | 驗證 `JsTsParser` 能正確提取 class, interface, function, arrow func, enum, type alias, method 與 JSDoc | FR-02 | `test_web_parsers.py::test_ft_02_js_ts_parser` |
| **FT-03** | 單元測試 | 驗證 `HtmlParser` 能正確提取 title, h1~h6, id 選擇器元素, 語意區塊與 HTML 註解 | FR-03 | `test_web_parsers.py::test_ft_03_html_parser` |
| **FT-04** | 單元測試 | 驗證 `CssParser` 能正確提取 class selector, id selector, CSS/SASS/LESS 變數與 @keyframes | FR-04 | `test_web_parsers.py::test_ft_04_css_parser` |
| **FT-05** | 單元測試 | 驗證 `ParserRegistry` 能依副檔名正確匹配並解析 Web 檔案 | FR-05 | `test_web_parsers.py::test_ft_05_parser_registry_integration` |
| **ET-01** | 邊界測試 | 驗證 `JsTsParser` 防範樣板字串 (`` `...` ``) 與正則表達式干擾 | EC-01 | `test_web_parsers.py::test_et_01_js_template_literals_edge_case` |
| **ET-02** | 邊界測試 | 驗證 TSX / JSX 標籤與 TS 泛型 `<T>` 之歧義防禦 | EC-02 | `test_web_parsers.py::test_et_02_tsx_generics_edge_case` |
| **ET-03** | 邊界測試 | 驗證 `HtmlParser` 對自閉合標籤與缺損 HTML 標籤之容錯性 | EC-03 | `test_web_parsers.py::test_et_03_html_malformed_edge_case` |
| **ET-04** | 邊界測試 | 驗證 `CssParser` 對 `@media` 與 SASS 多層嵌套括弧之堆疊正確性 | EC-04 | `test_web_parsers.py::test_et_04_css_nested_media_edge_case` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `PASSED` | `test_ft_01_language_type_enum`: 順利驗證 JAVASCRIPT/TYPESCRIPT/HTML/CSS 列舉 | 2026-08-30 |
| **FT-02** | `PASSED` | `test_ft_02_js_ts_parser`: 100% 提取 7 種 JS/TS 語意符號及 JSDoc | 2026-08-30 |
| **FT-03** | `PASSED` | `test_ft_03_html_parser`: 100% 提取 title, headings, id 選擇器與語意區塊 | 2026-08-30 |
| **FT-04** | `PASSED` | `test_ft_04_css_parser`: 100% 提取 class/id, CSS/SASS/LESS 變數與 @keyframes | 2026-08-30 |
| **FT-05** | `PASSED` | `test_ft_05_parser_registry_integration`: ParserRegistry 自動分流正確 | 2026-08-30 |
| **ET-01** | `PASSED` | `test_et_01_js_template_literals_edge_case`: 樣板字串中偽關鍵字完美過慮 | 2026-08-30 |
| **ET-02** | `PASSED` | `test_et_02_tsx_generics_edge_case`: TSX 泛型 `<T>` 與語意標籤歧義正常處理 | 2026-08-30 |
| **ET-03** | `PASSED` | `test_et_03_html_malformed_edge_case`: 缺損標籤與多層註解成功容錯 | 2026-08-30 |
| **ET-04** | `PASSED` | `test_et_04_css_nested_media_edge_case`: SASS/LESS 變數與 @media 嵌套無干擾 | 2026-08-30 |

> **沙盒測試總結**：`python yscb.py dev test knowledge-db` 全數通過 (103/103 PASSED, 1.62s)。

---

## 3. 人工 / UX 驗證 Checkpoint

- [ ] **UX-01**：實機執行 `python yscb.py knowledge-db search '<query>' -s` 對含 JS/TS/HTML/CSS 檔案之專案進行搜尋，驗證程式碼切片標記正確無誤。
