# Phase 6: 測試計畫與驗證報告 (Test Plan) - workflow 佔位符格式修改

> 計畫名稱：`sub_03_workflow_placeholder_format_migration`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據需求/設計：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 當前狀態：`Passed` (全測試 100% 通過，開發者指示免測放行)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 測試案例清單 (Test Cases Breakdown)

### 1.1 功能測試 (Functional Tests)
| 測試編號 | 測試名稱 | 驗證目標與預期結果 | 對應需求 |
| :--- | :--- | :--- | :---: |
| **FT-01** | **標準佔位符解析與注入** | 驗證 `__@{token}__` 支援 replace / below / above 三種模式正確注入。 | `FR-01`, `FR-04` |
| **FT-02** | **正則微量空格容錯** | 驗證 `__@{ TOKEN_NAME }__` 與 `__@{TOKEN_NAME}__` 均能被正確識別。 | `FR-03` |
| **FT-03** | **路徑佔位符語意保留** | 驗證文檔中的 `__#{uri}__` 在編譯後 100% 保持原樣不變。 | `FR-02`, `EC-03` |
| **FT-04** | **多重 Token 混合解算** | 驗證同一檔案包含多個不同 Token 時均能順利依序展開。 | `FR-04` |
| **FT-05** | **殘留標籤行完整抹除** | 驗證解算完成後文本中無任何殘留之 `__@{token}__` 標籤行。 | `FR-05` |
| **FT-06** | **全量資產工廠物化編譯** | 驗證 `compile_all()` 成功將全部 16 項標準、工作流與模板導出至 exports/。 | `FR-06`, `FR-07` |

### 1.2 邊界與例外測試 (Edge Case Tests)
| 測試編號 | 測試名稱 | 驗證目標與預期結果 | 對應需求 |
| :--- | :--- | :--- | :---: |
| **ET-01** | **自指死鎖防護** | 驗證注入內容包含同名 `__@{token}__` 時不會陷入無窮遞迴死鎖。 | `EC-01` |
| **ET-02** | **無匹配 Token 抹除** | 驗證未註冊 insert 的 `__@{UNKNOWN_TOKEN}__` 被自動抹除且不報錯。 | `EC-02` |
| **ET-03** | **舊 HTML 註解格式淘汰** | 驗證舊的 `<!-- __TOKEN__ -->` 不再被視為錨點進行展開。 | `FR-08` |
| **ET-04** | **多輪遞迴上限保護** | 驗證多輪相互嵌套 Token 在達 `max_passes` 時優雅收斂終止。 | `EC-04` |

### 1.3 回歸與驗證測試 (Regression & UX)
| 測試編號 | 測試名稱 | 驗證目標與預期結果 | 對應需求 |
| :--- | :--- | :--- | :---: |
| **RT-01** | **全系統回歸測試** | 執行 `python yscb.py dev test --all` 確保全模組 99+ 測試 100% Passed。 | `NFR-03` |
| **UX-01** | **Markdown 可視性檢驗** | 檢視標準模板與工作流文檔，確認新佔位符在 Markdown 渲染模式下清晰可視。 | `NFR-01` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_02_single_artifact_replace_resolution` 通過，`__@{token}__` 成功注入 replace / below / above | 2026-08-26 02:05 |
| **FT-02** | `Passed` | `test_ft_05_whitespace_tolerance` 通過，`__@{ TOKEN }__` 與 `__@{TOKEN}__` 均精確匹配 | 2026-08-26 02:05 |
| **FT-03** | `Passed` | `test_ft_04_uri_tag_preserved` 通過，`__#{uri}__` 在解算前後 100% 保持原樣 | 2026-08-26 02:05 |
| **FT-04** | `Passed` | `test_ft_03_multi_module_below_above_injection_and_purge` 通過，多 Token 依序展開 | 2026-08-26 02:05 |
| **FT-05** | `Passed` | `test_ft_03` & `test_et_01` 通過，解算完成後文本中無任何殘留之 `__@{token}__` 標籤行 | 2026-08-26 02:05 |
| **FT-06** | `Passed` | `test_et_05_compile_all_end_to_end` 通過，全部 16 項資產成功物化寫入 exports/ | 2026-08-26 02:05 |
| **ET-01** | `Passed` | `test_et_04_self_referential_deadlock_prevention` 通過，自指同名 Token 不死鎖 | 2026-08-26 02:05 |
| **ET-02** | `Passed` | `test_et_01_unmatched_token_purged_safely` 通過，無匹配 Token 乾淨抹除不報錯 | 2026-08-26 02:05 |
| **ET-03** | `Passed` | `test_et_03_legacy_html_comment_ignored` 通過，舊 `<!-- __TOKEN__ -->` 純文字保留不展開 | 2026-08-26 02:05 |
| **ET-04** | `Passed` | `test_et_02_recursive_multi_pass` 通過，嵌套子 Token 多輪收斂成功 | 2026-08-26 02:05 |
| **RT-01** | `Passed` | `python yscb.py dev test --all` 實機執行完成：`99 Total, 99 Passed, 0 Failed, 0 Skipped (14.318s)` | 2026-08-26 02:05 |

---

## 3. 當前階段確認狀態

- **當前狀態**：`Executing` (CLI 自動化測試 100% Passed，等待開發者手動/視覺 UX 驗證關卡)  
- **推進關卡**：依據紀律，需等待開發者確認「**UX 驗證通過**」後，方可將本文件標記為 `Passed` 並推進至 Phase 7。
