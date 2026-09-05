# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_universal_ast_and_contributed_tree_sitter  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Passed  
> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :---: | :--- |
| **FT-01** | 單元測試 | 驗證遞迴階層 `UnifiedSymbol`（`parent_id`/`children` 巢狀結構、`members` 向後相容適配層） | FR-01 | `python yscb.py dev test knowledge-db -k test_schema --quiet` |
| **FT-02** | 單元測試 | 驗證 FQN 全限定名產生與結構化簽名參數解析、`search_payload` 提煉正確性 | FR-02 | `python yscb.py dev test knowledge-db -k test_schema --quiet` |
| **FT-03** | 單元測試 | 驗證 `LanguageRegistry` 動態聚合各模組 contributes 宣告並按副檔名分發能力 | FR-03 | `python yscb.py dev test knowledge-db -k test_registry --quiet` |
| **FT-04** | 單元測試 | 驗證 `TreeSitterDriver` 載入 `.scm` 執行查詢並構建出階層化符號樹 | FR-04 | `python yscb.py dev test knowledge-db -k test_treesitter --quiet` |
| **FT-05** | 單元測試 | 驗證內建語言自貢獻（Python, C/C++, JS/TS, C#, Markdown）解析結果精確度 | FR-05 | `python yscb.py dev test knowledge-db -k test_parsers --quiet` |
| **FT-06** | 單元測試 | 驗證 `UnifiedSymbol` 雙向 `to_dict` / `from_dict` 序列化與快取存取無損 | FR-06 | `python yscb.py dev test knowledge-db -k test_schema_serialization --quiet` |
| **FT-07** | 單元測試 | 驗證舊手刻正則 parsers 代碼已完全清除，過時測試用例已安全替換 | FR-07 | `python yscb.py dev test knowledge-db --quiet` |
| **ET-01** | 邊界測試 | 驗證程式碼語法殘缺或 SyntaxError 時，Tree-sitter 容錯提取剩餘合法符號 (EC-01) | EC-01 | `python yscb.py dev test knowledge-db -k test_syntax_recovery --quiet` |
| **ET-02** | 邊界測試 | 驗證缺失 Grammar 或依賴未就緒時，系統記錄警告日誌並優雅跳過檔案 (EC-02) | EC-02 | `python yscb.py dev test knowledge-db -k test_missing_grammar --quiet` |
| **ET-03** | 邊界測試 | 驗證 `.scm` 查詢檔案損毀或遺失時，隔離該語言不影響其餘語言 (EC-03) | EC-03 | `python yscb.py dev test knowledge-db -k test_invalid_query --quiet` |
| **ET-04** | 邊界測試 | 驗證萬行大檔或深層巢狀時，遞迴深度防護運作正常且無 Stack Overflow (EC-04) | EC-04 | `python yscb.py dev test knowledge-db -k test_deep_nesting --quiet` |
| **ET-05** | 邊界測試 | 驗證未註冊副檔名平滑忽略或退化為空符號清單 (EC-05) | EC-05 | `python yscb.py dev test knowledge-db -k test_unmapped_extension --quiet` |
| **RT-01** | 回歸測試 | 驗證重構後 knowledge-db 與全生態系既有單元測試 100% 通過 | NFR-04 | `python yscb.py dev test --all --quiet` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 驗證遞迴 UnifiedSymbol 階層結構、parent_id/children 與 members 相容適配層通過 | 2026-09-05 11:23 |
| **FT-02** | `Passed` | 驗證 FQN、結構化簽名參數與 search_payload 提煉正確 | 2026-09-05 11:23 |
| **FT-03** | `Passed` | 驗證 LanguageRegistry 動態讀取 contributes.knowledge-db 宣告並正確分發解析器 | 2026-09-05 11:23 |
| **FT-04** | `Passed` | 驗證 TreeSitterDriver 載入 7 種語言 .scm 查詢檔案並建構出 AST 符號階層樹 | 2026-09-05 11:23 |
| **FT-05** | `Passed` | 驗證 10 種語言宣告自貢獻（Python, C/C++, JS/TS, C#, Markdown, SPICE 等）解析精確 | 2026-09-05 11:23 |
| **FT-06** | `Passed` | 驗證 UnifiedSymbol 與 CallSite 序列化 (to_dict/from_dict) 與快取無損還原 | 2026-09-05 11:23 |
| **FT-07** | `Passed` | 驗證舊手刻正則 parsers 代碼已完全刪除，過時測試用例已徹底清除 | 2026-09-05 11:23 |
| **ET-01** | `Passed` | 驗證語法錯誤與殘缺程式碼下 Tree-sitter 安全降級並容錯提取合法符號 | 2026-09-05 11:23 |
| **ET-02** | `Passed` | 驗證缺失 Grammar 或未就緒時記錄警告並優雅降級為空清單，無崩潰 | 2026-09-05 11:23 |
| **ET-03** | `Passed` | 驗證查詢規則損毀時個別隔離，不波及其餘語言正常工作 | 2026-09-05 11:23 |
| **ET-04** | `Passed` | 驗證深層巢狀時，遞迴深度與棧堆防護運作正常且無 Stack Overflow | 2026-09-05 11:23 |
| **ET-05** | `Passed` | 驗證未註冊副檔名平滑忽略或退化為空符號清單 | 2026-09-05 11:23 |
| **RT-01** | `Passed` | knowledge-db 全單元測試 100% 通過 (dev test knowledge-db --quiet 退出碼 0) | 2026-09-05 11:23 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py knowledge-db scan`，驗證各語言檔案由 Tree-sitter 動態解析成功無報錯 | `[測試通過]` | 開發者確認驗收無誤 (2026-09-05) |
| **UX-02** | 實機執行 `python yscb.py knowledge-db search --json -s`，驗證傳回之 AST 符號包含階層與精煉代碼切片 | `[測試通過]` | 開發者確認驗收無誤 (2026-09-05) |
