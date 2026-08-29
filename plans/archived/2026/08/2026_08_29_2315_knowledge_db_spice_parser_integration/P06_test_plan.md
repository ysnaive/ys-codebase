# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：knowledge-db 模組 SPICE 網表語系解譯器 (SpiceParser) 整合  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `can_parse()` 支援 `.cir`, `.sp`, `.spice`, `.net`, `.cdl` 及大小寫不敏感匹配 | FR-01 | `test_spice_parser.py::test_ft_01_can_parse_extensions` |
| **FT-02** | 單元測試 | 驗證 Stage 1 行聚合器正確合併 `+` 接續行，並萃取前置 `*` 註解為 Docstring | FR-02 | `test_spice_parser.py::test_ft_02_line_continuation_and_docstring` |
| **FT-03** | 單元測試 | 驗證 `.subckt`, `.model`, `.param`, `.include`, `.lib`, `.global` 符號提取與屬性完整性 | FR-03 | `test_spice_parser.py::test_ft_03_dot_commands_extraction` |
| **FT-04** | 單元測試 | 驗證子電路內部 `members` (電晶體 `M/Q`, 被動元件 `R/C/L`, 實例 `X`) 與頂層 `X` 實例提取 | FR-04 | `test_spice_parser.py::test_ft_04_subckt_members_and_instances` |
| **FT-05** | 整合測試 | 驗證 `ParserRegistry` 正確調度 `SpiceParser` 並支援多語言符號提取 | FR-05 | `test_spice_parser.py::test_ft_05_registry_integration` |
| **ET-01** | 邊界測試 | 驗證跨多行 `+` 接續夾雜空行與行尾 `;` / `$` 註解時之穩定合併與行號精準映射 | EC-01 | `test_spice_parser.py::test_et_01_continuation_with_comments_and_blank_lines` |
| **ET-02** | 邊界測試 | 驗證未閉合 `.subckt` 網表自動防禦封裝至檔案結尾，不拋出未捕獲例外 | EC-02 | `test_spice_parser.py::test_et_02_unclosed_subcircuit_fallback` |
| **ET-03** | 邊界測試 | 驗證混合方言註解 (`*`, `;`, `$`) 與大小寫混雜關鍵字之正規化識別 | EC-03 | `test_spice_parser.py::test_et_03_mixed_dialect_comments_and_case` |
| **ET-04** | 邊界測試 | 驗證空檔案、首行純標題或純註解網表優雅回傳空清單 `[]` | EC-04 | `test_spice_parser.py::test_et_04_empty_and_comment_only_files` |
| **RT-01** | 回歸測試 | 全生態系模組單元測試 100% 通過（含 core, dev, agents-workflow, knowledge-db） | NFR-02 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_01_can_parse_extensions` 驗證 6 種有效副檔名與 6 種無效副檔名全數通過 (0.01s) | 2026-08-29 23:18 |
| **FT-02** | `Passed` | `test_ft_02_line_continuation_and_docstring` 驗證多行接續、Docstring 萃取與行號映射精準無誤 | 2026-08-29 23:18 |
| **FT-03** | `Passed` | `test_ft_03_dot_commands_extraction` 驗證點指令 (.include, .lib, .global, .param, .model) 符號提取 100% 符合 | 2026-08-29 23:18 |
| **FT-04** | `Passed` | `test_ft_04_subckt_members_and_instances` 驗證子電路內部 members 與頂層 X 實例結構化解析通過 | 2026-08-29 23:18 |
| **FT-05** | `Passed` | `test_ft_05_registry_integration` 驗證 ParserRegistry 動態調度 SpiceParser 正確整合 | 2026-08-29 23:18 |
| **ET-01** | `Passed` | `test_et_01_continuation_with_comments_and_blank_lines` 驗證夾雜空行與行尾註解接續合併防禦通過 | 2026-08-29 23:18 |
| **ET-02** | `Passed` | `test_et_02_unclosed_subcircuit_fallback` 驗證未閉合 .subckt 自動封裝至檔案末端通過 | 2026-08-29 23:18 |
| **ET-03** | `Passed` | `test_et_03_mixed_dialect_comments_and_case` 驗證混合方言註解 (*, ;, $) 與大小寫混雜正規化通過 | 2026-08-29 23:18 |
| **ET-04** | `Passed` | `test_et_04_empty_and_comment_only_files` 驗證空檔案與純註解安全回傳空清單通過 | 2026-08-29 23:18 |
| **RT-01** | `Passed` | `python yscb.py dev test --all` ➔ 全生態系 4 大模組 210/210 測試 100% Passed (12.26s) | 2026-08-29 23:18 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：使用 `python yscb.py knowledge-db search '<SPICE符號>' -s` 對真實 SPICE 網表 [`docs/LS_CB3N.sp`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/LS_CB3N.sp) 進行實機語意檢索，確認輸出之子電路 `SR_LATCH_CB3N`、內部元件 `M_PA`、Docstring 註解與代碼切片 100% 精準呈現（開發者實測確認通過）。
