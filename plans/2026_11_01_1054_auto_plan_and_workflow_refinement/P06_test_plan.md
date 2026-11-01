# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：PXX-05_auto 單檔合併模板與 agents-workflow 工具鏈完善  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1054_auto_plan_and_workflow_refinement  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `PXX-05_auto.md` 模板註冊、五段 H2 標題合約，以及 `PlanStatusResolver.resolve_phase_file` 將 `P01`~`P05` 動態解析至 `P01-05_auto.md` | FR-01 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **FT-02** | 單元測試 | 驗證 `PlanVerifier` 對 `P01-05_auto.md` 執行五段 H2 契約、FR/EC/NFR/API/TASK 雙向追溯與偏差紀錄表校驗，`SessionTraceAnalyzer.audit_plan_mtimes` 同檔跳過自比對零誤報 | FR-02 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **FT-03** | 單元測試 | 驗證 `PlanSearcher` 對 Umbrella `sub_XX/` 同名 `[P00:DR-01]` 按 `(plan_name, rel_src_str, dr_id)` 去重不吞沒、`search_full_text` 保留 `sub_XX/` 相對路徑，且 CLI `plan search` 支援 `--full` / `--json` | FR-03 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **FT-04** | 單元測試 | 驗證 `PlanScanner.execute_resume` 於無 `handoff.md` 時自動輸出 `=== [AUTO-GENERATED RECOVERY CAPSULE] ===` 雙軸膠囊，且 `render_matrix_ascii` 針對未封存完持計畫輸出 `plan archive` 提醒 | FR-04 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **FT-05** | 單元測試 | 驗證 `compiler.py` `_replace_in_code_span` 針對無 `#anchor` 之完整反引號 `project://` URI 直接替換為反引號包裹相對路徑，不展開 Markdown 雙重連結 | FR-05 | `python yscb.py dev test agents-workflow -k test_ft_09_exact_code_span_project_uri_without_anchor_no_link` |
| **FT-06** | 單元測試 | 驗證 `PlanVerifier` 針對非代码块中硬編碼 `file:///` 或磁碟機絕對路徑發出 `[WARN] PORTABILITY`，且當 `P05_task.md` 含 `Major`/`Critical` 偏差而 `P02`/`P03` mtime 較舊時發出 `[WARN] BACKPROP` | FR-06 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **ET-01** | 邊界測試 | 驗證中途啟動 `/auto` 產出 `P03-05_auto.md`（搭配既有 `P01`/`P02` 獨立檔）時，`PlanStatusResolver` 將 `P01`/`P02` 解析至獨立檔、`P03`~`P05` 解析至 `P03-05_auto.md`，且 `PlanVerifier` 僅要求 `P03-05_auto.md` 具備 `§3 (P03)`~`§5 (P05)` 段落 | EC-01 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **ET-02** | 邊界測試 | 驗證既有封存與活躍計畫中之舊版多檔 `P01_..._auto.md`~`P05_..._auto.md` 仍正常通過 `resolve_phase_file` 與 `verify_plan` 向下相容校驗 | EC-02 | `python yscb.py dev test agents-workflow -k test_ft_15_auto_track_end_to_end_lifecycle` |
| **ET-03** | 邊界測試 | 驗證代碼圍欄區塊或行內反引號內出現之 `C:\...` 或 `file:///` 範例字串不觸發 `PORTABILITY` 誤報 | EC-03 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **ET-04** | 邊界測試 | 驗證剛開立僅含 `P00_discuss.md` 且無 `P05`/`P06` 之新計畫執行 `plan resume --plan` 時，膠囊優雅降級輸出最新階段與最近 3 筆 `changelog.md` 事件且不拋出異常 | EC-04 | `python yscb.py dev test agents-workflow -k test_ft_16` |
| **RT-01** | 回歸測試 | 驗證 `agents-workflow` 全量 136 項單元、邊界與整合測試 100% 通過，且單次 `plan verify` 耗時遠低於 500ms | NFR-01 | `python yscb.py dev test agents-workflow -q` |
| **RT-02** | 回歸測試 | 驗證 `contributes check` 與 `dev check agents-workflow` 合規檢查 100% 通過，遵循純標準庫與零外部依賴紀律 | NFR-02 | `python yscb.py contributes check ; python yscb.py dev check agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_ft_16_pxx_05_auto_consolidated_search_capsule_and_portability` 驗證通過 (`P01-05_auto.md` 五段解析與狀態映射無誤) | 2026-11-01 |
| **FT-02** | `Passed` | `test_ft_16` 驗證通過 (`PlanVerifier` 五段契約與跨檔追溯、`audit_plan_mtimes` 同檔免自比對無誤) | 2026-11-01 |
| **FT-03** | `Passed` | `test_ft_16` 驗證通過 (`Umbrella sub_01/sub_02` 同名 DR 去重保留 2 筆、`--full` 與 `--json` 輸出無誤) | 2026-11-01 |
| **FT-04** | `Passed` | `test_ft_16` 驗證通過 (`[AUTO-GENERATED RECOVERY CAPSULE]` 與 `plan archive` 提醒輸出無誤) | 2026-11-01 |
| **FT-05** | `Passed` | `test_ft_09_exact_code_span_project_uri_without_anchor_no_link` 驗證通過 (反引號內無錨點 `project://` 保持純反引號路徑) | 2026-11-01 |
| **FT-06** | `Passed` | `test_ft_16` 驗證通過 (`PORTABILITY` 與 `BACKPROP` 雙警告精準觸發) | 2026-11-01 |
| **ET-01** | `Passed` | `test_ft_16` 驗證通過 (`P03-05_auto.md` 中途接手 `min_phase=3` 動態段落校驗通過) | 2026-11-01 |
| **ET-02** | `Passed` | `test_ft_15_auto_track_end_to_end_lifecycle` 驗證通過 (舊版 `PXX_<name>_auto.md` 100% 向下相容) | 2026-11-01 |
| **ET-03** | `Passed` | `test_ft_16` 驗證通過 (僅掃描 `non_code_lines`，代碼圍欄與反引號內路徑零誤報) | 2026-11-01 |
| **ET-04** | `Passed` | `test_ft_16` 驗證通過 (僅含 `P00_discuss.md` 之新計畫生成膠囊不崩潰) | 2026-11-01 |
| **RT-01** | `Passed` | `Pass: 136(100.0%), Fail: 0, Skip: 0` (耗時 3.00s) | 2026-11-01 |
| **RT-02** | `Passed` | `All contributes definitions are valid! (Checked 15 file(s))` & `agents-workflow [PASS]` | 2026-11-01 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視本計畫實際採用之 [`P01-05_auto.md`](P01-05_auto.md) 單檔合併規格結構，以及執行 `python yscb.py agents-workflow plan verify 2026_11_01_1054_auto_plan_and_workflow_refinement`、`python yscb.py agents-workflow plan status` 與 `python yscb.py agents-workflow plan search DR-01 --dr --full` 之終端機輸出體驗 | `[測試通過]` | 經雙輪盲眼子代理全範疇審查與開發者確認通過 |
