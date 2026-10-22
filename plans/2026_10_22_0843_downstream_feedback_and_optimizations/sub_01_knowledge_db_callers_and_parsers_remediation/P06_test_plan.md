# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_01_knowledge_db_callers_and_parsers_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `callers --json` 在有實際 caller 命中時（`simple`, `preview`/`-s`, `detail` 三種模式）正常輸出 JSON 且不拋出 `KeyError: 'caller_symbol'` | FR-01 | `python yscb.py dev test knowledge-db -k test_cli -q` |
| **FT-02** | 單元測試 | 驗證 `callers` / `callees` / `impact` 預設排除 Markdown 文檔提及，且指定 `--ftype=md` 時可正確篩選出文檔引用 | FR-02 | `python yscb.py dev test knowledge-db -k test_graph -q` |
| **FT-03** | 單元測試 | 驗證 C# 全場景調用提取與鏈接：傳統與 file-scoped `namespace`、隱含 `this` 呼叫 (`MarkMeasureDirty()`)、欄位/變數接收者 (`m_Owner.MarkMeasureDirty()`)、條件存取 (`m_Owner?.MarkMeasureDirty()`)、泛型呼叫 (`GetService<T>()`)、完整命名空間限定呼叫 (`UIToolkit.UI.Layout.FlexLayoutEngine.CalculateLayout`)、`override` 方法與 `property` 存取器內呼叫 | FR-03<br/>FR-04 | `python yscb.py dev test knowledge-db -k test_graph -q` |
| **FT-04** | 單元測試 | 驗證遞迴自呼叫（如 `FlexLayoutEngine.CalculateLayout` 內部遞迴呼叫自身）在 `callers` 與 `callees` 中正確保留，且其他語言（C 結構指標 `ptr->fn()`、C++ 模板與類別外方法 `Class::Method`、Python/TS 鏈式呼叫）均正確提取 | FR-03<br/>FR-04 | `python yscb.py dev test knowledge-db -k test_graph -q` |
| **FT-05** | 單元測試 | 驗證介面方法與實作類別契約關聯聚合：查詢 `IPanel.UpdateLayout` 時，能自動關聯並回報實作類別 `Panel.UpdateLayout` 與基類呼叫端之所有 callers 與 impact | FR-05 | `python yscb.py dev test knowledge-db -k test_graph -q` |
| **ET-01** | 邊界測試 | 驗證遞迴自呼叫與介面/實作雙向關聯下，`act_impact` 具備環路剪枝不陷入死循環且不將目標自身重複計入擴散層 | EC-01 | `python yscb.py dev test knowledge-db -k test_graph -q` |
| **ET-02** | 邊界測試 | 驗證無關類別同名方法在無前綴裸調用且無繼承關係時，嚴格阻斷不產生跨類別幽靈邊；以及不匹配 `--ftype` 時安全回傳空結果 | EC-02<br/>EC-04 | `python yscb.py dev test knowledge-db -k test_graph -q` |
| **RT-01** | 回歸測試 | 驗證 `knowledge-db` 全套單元測試與靜態檢查 100% 通過 | NFR-01<br/>NFR-02 | `python yscb.py dev test knowledge-db -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCLI.test_cli_options_extraction_and_orthogonal_filter` 驗證 `callers --json` 在有實際 caller 時正常序列化輸出（`simple`/`-s`/`--detail`） | 2026-10-22 |
| **FT-02** | `Passed` | `TestCallGraphAndReferenceIndex.test_ft_12` 驗證預設排除 `.md` 文檔引用，且指定 `--ftype=md` 可篩選出文檔引用 | 2026-10-22 |
| **FT-03** | `Passed` | `test_ft_12` 驗證 C# 命名空間、隱含 `this`、繼承 `base_types`、條件存取 `?.`、屬性 setter 與完整命名空間呼叫鏈接 | 2026-10-22 |
| **FT-04** | `Passed` | `test_ft_08` ~ `test_ft_12` 驗證遞迴自呼叫保留與 C/C++/C#/Python/TS 跨語言呼叫點提取 | 2026-10-22 |
| **FT-05** | `Passed` | `test_ft_12` 驗證 `IPanel.UpdateLayout` 與 `Panel.UpdateLayout` 介面與實作雙向契約聚合 | 2026-10-22 |
| **ET-01** | `Passed` | `test_ft_12` 與 `test_cyclic_graph_resilience` 驗證遞迴與環路在 `act_impact` 中正常剪枝 | 2026-10-22 |
| **ET-02** | `Passed` | `test_fqn_disambiguation_eliminates_ghosts` 與 `--ftype` 測試驗證無關跨檔裸調用阻斷與過濾安全性 | 2026-10-22 |
| **RT-01** | `Passed` | `python yscb.py dev test knowledge-db -q` 全數通過：`Pass: 158(100.0%), Fail: 0, Skip: 0`；`dev check knowledge-db --json` 為 `PASS` | 2026-10-22 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py knowledge-db callers resolve_call_site --json -s` 與 `--ftype=md`，確認 JSON 輸出結構完整無崩潰，且預設排除 `.md` 文檔、加 `--ftype=md` 可檢視文檔引用 | `[測試通過]` | 2026-10-22 實機驗證與 C# 模擬環境全場景測試通過 |
