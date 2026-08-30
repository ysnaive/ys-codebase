# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 模組 Web 語言解譯器 (JS/TS/HTML/CSS Parsers)  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 P03 API 規格書中已有具體類別與方法簽名
- [x] **邊界防禦**：EC-01 ~ EC-04 在 Parser 實作邏輯中均有具體防禦與邊界處理
- [x] **依賴純淨**：符合 NFR-01 (100% 原生 Python 標準庫，零 C/Node.js 依賴)

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `source/knowledge-db/README.md` | Modify | 於支援語言與 CLI `--ftype` 區塊補充 JS/TS, HTML, CSS 解析支援 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當 JavaScript / TypeScript 檔內含大量多行樣板字串 (Template Literals `` `...` ``) 或 JSX / TSX 標籤時，正則表達式是否會產生誤判？  
> 💡 **防護解法**：在狀態機掃描時，引入樣板字串跳過機制 (`in_template_literal` 狀態) 以及引態文字跳過，隔離多行字串內的大括弧與關鍵字。

> ❓ **尖銳問題 2**：HTML 檔案若為非正規格式或缺乏閉合標籤，解析器是否會崩潰？  
> 💡 **防護解法**：採單列/單標籤正則掃描加 `try-except` 區域包覆，即便單一行標籤語法異常，解析器仍能彈性跳過並繼續走訪，不拋出未捕獲例外。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [x] **TASK-01**：更新 `schema.py` 擴充 `LanguageType` Enum (`JAVASCRIPT`, `TYPESCRIPT`, `HTML`, `CSS`)
- [x] **TASK-02**：建立 `js_ts_parser.py` 實作 `JsTsParser`
- [x] **TASK-03**：建立 `html_parser.py` 實作 `HtmlParser`
- [x] **TASK-04**：建立 `css_parser.py` 實作 `CssParser`
- [x] **TASK-05**：更新 `registry.py` 與 `__init__.py` 完成外掛註冊與模組導出
- [x] **TASK-06**：編寫 `test_web_parsers.py` 單元測試套件並執行驗證

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] P06 測試計畫同步 Confirmed**：P06_test_plan.md 中的 FT-01~05 與 EC-01~04 測試案例已完成定稿。
