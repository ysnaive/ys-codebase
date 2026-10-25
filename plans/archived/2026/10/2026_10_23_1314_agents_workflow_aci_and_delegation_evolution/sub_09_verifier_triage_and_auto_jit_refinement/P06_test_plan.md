# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：PlanVerifier 缺失率分流處方、確定性標頭自癒、階段前瞻提示與 /auto 兩階段 JIT 讀模板瘦身 (sub_09_verifier_triage_and_auto_jit_refinement)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `auto/SKILL.md` 拔除內聯章節表並收斂至 $\le 75$ 行（實測 74 行），落實兩階段 JIT 讀取 `P01~P06` 模板與 Phase 5 實作子代理量化門檻（$\ge 5$ 檔或 $> 1,500$ 行），且 `test_ft_09` 相容無衝突。 | FR-01, FR-02, NFR-02 | `python yscb.py dev test --target=agents-workflow:TestPlansModelRecord.test_ft_13_sub07_auto_context_lean_and_auto_suffix_support` |
| **FT-02** | 單元與邊界測試 | 驗證 `PlanVerifier` 在提供 `--log` 且檔案具備合法 `狀態`、`模型` 與完整章節時，自動原地無損補齊 `功能名稱`、`建立日期` 與 `sub_XX` 之 `所屬主計畫`（`header_healed`）；若缺 `狀態`/`模型` 或含未替換佔位符、或處於唯讀無 `--log` 模式則不改寫磁碟並於 `Fix Hint` 給出精確推導值；無 `>` Blockquote 時自動插於 `#` 標題下方。 | FR-03, EC-01, EC-02, NFR-01 | `python yscb.py dev test --target=agents-workflow:TestPlansModelRecord.test_ft_14_sub09_verifier_triage_header_heal_and_next_phase_hint` |
| **FT-03** | 單元與邊界測試 | 驗證 `PlanVerifier` 章節缺失率速評分流：單檔缺失聚合為單一 `TEMPLATE` `PlanIssue`；缺失率 $< 50\%$ 輸出 `[TRIAGE: QUICK_PATCH]` 與缺失之原始 Markdown 標題供 `edit_file` 修補；缺失率 $\ge 50\%$ 輸出 `[TRIAGE: FULL_REWRITE]` 與 `.agents/.yscb/templates/{tmpl_name}` 模板路徑及完整原始標題供 `write_file` 重寫。 | FR-04, EC-03 | `python yscb.py dev test --target=agents-workflow:TestPlansModelRecord.test_ft_14_sub09_verifier_triage_header_heal_and_next_phase_hint` |
| **FT-04** | 單元與邊界測試 | 驗證單一計畫檢核 `PASSED` 且尚未 `Completed` 時，`PlanReport.next_phase_hint` 與 CLI 輸出 `[NEXT PHASE GATE]` 下一階段檔名、模板路徑與必備章節預告；當計畫已 `Completed` 時 `next_phase_hint` 為 `None`。 | FR-05, EC-04 | `python yscb.py dev test --target=agents-workflow:TestPlansModelRecord.test_ft_14_sub09_verifier_triage_header_heal_and_next_phase_hint` |
| **RT-01** | 整合與回歸測試 | 執行 `dev check agents-workflow` 與全模組 133 項自動化測試套件，並完成 `dev build`、`install @build`、`compile` 與 `release --force` 驗證 57 項產物物化零警告。 | FR-01, FR-02, FR-03, FR-04, FR-05, NFR-01, NFR-02 | `python yscb.py dev check agents-workflow; python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_13_sub07_auto_context_lean_and_auto_suffix_support` 與 `test_ft_09` 通過，`auto/SKILL.md` 為 74 行（$\le 75$ 行）。 | 2026-10-25 |
| **FT-02** | `Passed` | `test_ft_14_sub09_verifier_triage_header_heal_and_next_phase_hint` 通過，驗證 `header_healed` 原地補齊與唯讀模式隔離。 | 2026-10-25 |
| **FT-03** | `Passed` | `test_ft_14` 驗證 1/4 (`25%`) `QUICK_PATCH` 與 3/4 (`75%`) `FULL_REWRITE` 單一 `TEMPLATE` 處方分流通過。 | 2026-10-25 |
| **FT-04** | `Passed` | `test_ft_14` 驗證 `P00 Passed` 輸出 `下一階段 P01 (P01_requirements_spec.md)` 及 `Completed` 回傳 `None` 通過。 | 2026-10-25 |
| **RT-01** | `Passed` | `dev check` `PASSED`；`dev test agents-workflow -q`：`Pass: 133(100.0%), Fail: 0, Skip: 0`；57 檔物化發布成功。 | 2026-10-25 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `.agents/skills/auto/SKILL.md` 兩階段 JIT 讀模板瘦身成果（74 行），並執行 `python yscb.py agents-workflow plan verify sub_09_verifier_triage_and_auto_jit_refinement` 檢視 `[NEXT PHASE GATE]` 預告與診斷體驗。 | `[測試通過]` | 開發者確認通過 |

