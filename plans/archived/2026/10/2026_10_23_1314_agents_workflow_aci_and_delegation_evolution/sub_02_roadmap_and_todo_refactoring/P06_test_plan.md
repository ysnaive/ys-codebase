# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_02_roadmap_and_todo_refactoring  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `TodoManager.add_todo` 免讀盲寫初始化 `TODO.md`、分配 `[TODO-01]` 並更新頂部 `> 最後分配編號：1` 與 `> 模型：`。 | FR-01 | `python yscb.py dev test agents-workflow -q` (`test_todo_add_and_monotonic_id`) |
| **FT-02** | 單元測試 | 驗證 `TodoManager.list_todos` 與 `cli.todo(["list", "--scope", ...])` 唯讀檢索與關鍵字過濾。 | FR-02 | `python yscb.py dev test agents-workflow -q` (`test_todo_list_and_scope_filter`) |
| **FT-03** | 單元測試 | 驗證 `TodoManager.promote_todos` 支援單筆與多筆批次（如 `TODO-01 TODO-03`）原子剪切拔除，建立 `plans/YYYY_MM_DD_HHMM_<slug>/todo.md` 並伴隨初始化 `changelog.md`。 | FR-03 | `python yscb.py dev test agents-workflow -q` (`test_todo_promote_batch_and_seeded_dir`) |
| **FT-04** | 單元測試 | 驗證 `RoadmapManager.scan_roadmaps(status_filter=...)` 支援狀態過濾並解析 `scope` 與 `trigger` 標頭。 | FR-04 | `python yscb.py dev test agents-workflow -q` (`test_roadmap_status_filter_and_exclude_todo`) |
| **FT-05** | 單元測試 | 驗證 `RoadmapManager.promote_roadmap` 將 `plans/roadmap/<topic>.md` 物理搬移 (`shutil.move`) 為計畫目錄下之 `roadmap.md`，且 `changelog.md` 模型採用當輪 `--model`（不繼承舊檔模型）。 | FR-05 | `python yscb.py dev test agents-workflow -q` (`test_roadmap_promote_physical_move_and_model_isolation`) |
| **FT-06** | 整合測試 | 驗證 `PlanScanner`、`PlanStatusResolver` 對僅含 `roadmap.md` / `todo.md` 之目錄回報 `Seeded` 狀態，且建立 `P00_discuss.md` 後自動切換為主體進度。 | FR-06 | `python yscb.py dev test agents-workflow -q` (`test_seeded_plan_status_and_verifier_whitelist`) |
| **ET-01** | 邊界測試 | 驗證 `TODO.md` 不存在時執行 `todo list` 平穩回傳 0，執行 `todo promote` 回傳錯誤碼 1。 | EC-01 | `python yscb.py dev test agents-workflow -q` (`test_todo_list_and_scope_filter`) |
| **ET-02** | 邊界測試 | 驗證 `TODO.md` 條目被 `todo promote` 全數拔空後，再次 `todo add` 仍依 `> 最後分配編號：N` 嚴格單調遞增（不重置為 `TODO-01`）。 | EC-02 | `python yscb.py dev test agents-workflow -q` (`test_todo_add_and_monotonic_id`) |
| **ET-03** | 邊界測試 | 驗證 `todo promote` 傳入不存在之 `TODO-ID` 或非法 `--slug`（如含大寫、連字號或空白）時拒絕執行並保持原 `TODO.md` 100% 原子無損。 | EC-03 | `python yscb.py dev test agents-workflow -q` (`test_todo_promote_batch_and_seeded_dir`) |
| **ET-04** | 邊界測試 | 驗證 `roadmap promote` 傳入不存在主題或 `TODO.md` 時拒絕搬移並回傳錯誤。 | EC-04 | `python yscb.py dev test agents-workflow -q` (`test_roadmap_promote_physical_move_and_model_isolation`) |
| **ET-05** | 邊界測試 | 驗證包含 `roadmap.md`（具 `> 歸檔日期：` 與 `> 狀態：Ready`）或 `todo.md` 之主計畫／子計畫目錄執行 `PlanVerifier.verify_plan` 100% `PASS`。 | EC-05 | `python yscb.py dev test agents-workflow -q` (`test_seeded_plan_status_and_verifier_whitelist`) |
| **ET-06** | 邊界測試 | 驗證 `plans/roadmap/TODO.md` 存在時，`RoadmapManager.scan_roadmaps()` 自動將其排除，不混入策略路線圖清單。 | EC-06 | `python yscb.py dev test agents-workflow -q` (`test_roadmap_status_filter_and_exclude_todo`) |
| **RT-01** | 回歸測試 | 驗證單次 CLI 操作效能與零外部依賴符合約束，且既有 `agents-workflow` 全套單元測試 100% 通過。 | NFR-01 | `python yscb.py dev test agents-workflow -q` |
| **RT-02** | 回歸測試 | 驗證 `python yscb.py dev check agents-workflow` 靜態合規檢查（`core.json` 與 `cli.py` 1:1 對稱性、Stage 1/2 編譯）100% 通過。 | NFR-02 | `python yscb.py dev check agents-workflow` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `test_todo_add_and_monotonic_id` 通過：自動建立 `TODO.md` 並分配 `TODO-01`/`TODO-02`，標頭寫入 `> 最後分配編號：2`。 | 2026-10-24 |
| **FT-02** | `Passed` | `test_todo_list_and_scope_filter` 通過：`--scope` 關鍵字精準過濾目標條目。 | 2026-10-24 |
| **FT-03** | `Passed` | `test_todo_promote_batch_and_seeded_dir` 通過：打包提取 `TODO-01` 與 `TODO-03` 生成 `todo.md` 與 `changelog.md`，原檔僅留 `TODO-02`。 | 2026-10-24 |
| **FT-04** | `Passed` | `test_roadmap_status_filter_and_exclude_todo` 通過：`status_filter="Ready"` 精確過濾並解析 `scope` 與 `trigger`。 | 2026-10-24 |
| **FT-05** | `Passed` | `test_roadmap_promote_physical_move_and_model_isolation` 通過：`shutil.move` 物理移轉為 `roadmap.md`，且 `changelog.md` 記載當輪模型 `CurrentSessionModel`（未受 `HistoricalOldModel-v1` 污染）。 | 2026-10-24 |
| **FT-06** | `Passed` | `test_seeded_plan_status_and_verifier_whitelist` 通過：`PlanStatusResolver` 與 `PlanScanner` 正確回報 `Seeded` / `Seeded (Pending Plan)`。 | 2026-10-24 |
| **ET-01** | `Passed` | `test_todo_list_and_scope_filter` 通過：空帳本不報錯且不產生空檔案。 | 2026-10-24 |
| **ET-02** | `Passed` | `test_todo_add_and_monotonic_id` 通過：全數 Pop 清空後再次 `add_todo` 分配 `TODO-03`，無歷史編號碰撞。 | 2026-10-24 |
| **ET-03** | `Passed` | `test_todo_promote_batch_and_seeded_dir` 通過：無效 ID `TODO-99` 與非法 slug `Invalid-Slug!` 均被阻斷且原檔無損。 | 2026-10-24 |
| **ET-04** | `Passed` | `test_roadmap_promote_physical_move_and_model_isolation` 通過：阻斷對 `TODO` 與不存在主題之 `roadmap promote`。 | 2026-10-24 |
| **ET-05** | `Passed` | `test_seeded_plan_status_and_verifier_whitelist` 與實機 `plan verify --all` 通過：子計畫內 `roadmap.md` 100% `PASS`（0 Warnings, 0 Failed）。 | 2026-10-24 |
| **ET-06** | `Passed` | `test_roadmap_status_filter_and_exclude_todo` 通過：`TODO.md` 自動排除於 `scan_roadmaps()` 之外。 | 2026-10-24 |
| **RT-01** | `Passed` | `python yscb.py dev test agents-workflow -q` 全套 129 項測試 100.0% 通過（0 Fail, 0 Skip）。 | 2026-10-24 |
| **RT-02** | `Passed` | `python yscb.py dev check agents-workflow` 靜態合規檢查 `PASSED`（並完成 `@build` 安裝與 51 份資產原子發布）。 | 2026-10-24 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 實機執行 `python yscb.py agents-workflow todo list`、`python yscb.py agents-workflow roadmap --status Ready` 與 `python yscb.py agents-workflow plan verify --all`，確認雙層儲備 CLI 與子計畫內 `roadmap.md` 白名單檢核輸出清晰合規。 | `[測試通過]` | 2026-10-24 經反向延伸檢閱與實機驗證通過 |
