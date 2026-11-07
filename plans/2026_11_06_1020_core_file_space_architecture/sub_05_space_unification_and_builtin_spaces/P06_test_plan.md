# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：sub_05_space_unification_and_builtin_spaces  
> 建立日期：2026-11-07  
> 所屬主計畫：2026_11_06_1020_core_file_space_architecture  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 全面統一 `SpaceConfig`、移除 `PresetConfig` / `fs presets` CLI、允許空 `entries`/`compose`（評估為 $\emptyset$）與對稱化 `CompiledRuleSet`（`allow_dir_prefix=True`, `match_any_seg=True`） | FR-01, EC-04 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_l0_cli_dual_routing_and_commands` |
| **FT-02** | 單元測試 | 四階段兩趟編譯規則注入、同 `<owner>/<short-name>` 規則層絕對聯集（`[*] ∪ [*.py] = [*]`）、`on_register_file_spaces` 事件廣播與重入/沙盒隔離 | FR-02, EC-02 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_watch_default_ephemeral_shared_registry_and_watcher_coordination` |
| **FT-03** | 單元測試 | `presets` 規則引用、`!<space>` 反向規則排除（目標 `include` 轉排除並保留目標 `exclude` 豁免）與 `os.scandir` 局部子樹剪枝不變量 | FR-03, EC-03, NFR-02 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_presets_rule_reference_negated_preset_and_subtree_pruning` |
| **FT-04** | 單元測試 | `compose` 檔案結果絕對聯集（無母空間二次過濾）、`!<space>` 結果差集（$\text{Positive} \setminus \text{Negative}$）、自動生成 `/<short-name>` 合成空間與 `synthetic__<short>` 快照鍵隔離 | FR-04, EC-05 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_compose_algebra_set_difference_and_cycle_detection` |
| **FT-05** | 單元測試 | 內建 `gitignore` 正向空間（`entries: ["project://"]`, `watch: false`）與 `project://.gitignore` 按 `# [<owner>]` 分組物化（`include -> rule`, `exclude -> !rule`） | FR-05 | `python yscb.py dev test --target=core:TestCoreGitignore` |
| **FT-06** | 整合測試 | 內建 `workspace` 遞迴掃描上限空間、`vscode-support` Glob 正規化與 `.modules` 豁免、`gdrive-support` / `agents-workflow` / `ast` / `knowledge-db` / `server` / `file-space` 跨模組對齊 | FR-06, NFR-01 | `python yscb.py dev test core -q && python yscb.py dev test vscode-support -q && python yscb.py dev test gdrive-support -q` |
| **ET-01** | 邊界測試 | `presets` 與 `compose`（含 `!<space>` 與 `/<short-name>`）直接或間接循環引用偵測，斷言拋出 `SpaceCycleError` | EC-01 | `python yscb.py dev test --target=core:TestCoreSpaceAtomicEngine.test_compose_algebra_set_difference_and_cycle_detection` |
| **RT-01** | 回歸測試 | 8 大受影響模組（`core`, `file-space`, `vscode-support`, `gdrive-support`, `server`, `ast`, `knowledge-db`, `agents-workflow`）靜態合規檢查與全套測試無損通過 | FR-01~FR-06, EC-01~EC-05, NFR-01~NFR-02 | `python yscb.py dev check <mod> && python yscb.py dev test <mod> -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `TestCoreSpaceAtomicEngine` (`test_l0_cli_dual_routing_and_commands`, `test_three_coordinate_rules_and_single_point_match_explain`) 及 `file-space` (18/18) 100% 通過 | 2026-11-07 |
| **FT-02** | `Passed` | 四階段規則注入、`[*] ∪ [*.py] = [*]`、`on_register_file_spaces` 廣播與 `_in_reload_broadcast` 重入防護 100% 通過 | 2026-11-07 |
| **FT-03** | `Passed` | `!core/gitignore` 反向排除與 `os.scandir` Spy 驗證：`.venv` 0 次深入剪枝、`build/keep.txt` 豁免保留 100% 通過 | 2026-11-07 |
| **FT-04** | `Passed` | `compose` 絕對聯集、`!mod_b/secrets` 差集、`/docs` 合成空間歸屬與 `synthetic__` 快照隔離 100% 通過 | 2026-11-07 |
| **FT-05** | `Passed` | `TestCoreGitignore` (5/5 Passed) 驗證 `<owner>/gitignore` 正向空間與 `exclude -> !<pattern>` 物化 100% 通過 | 2026-11-07 |
| **FT-06** | `Passed` | `workspace` 預設掃描天花板、`vscode-support` (22/22)、`gdrive-support` (34/34) 與跨模組 `on_register_file_spaces` 100% 通過 | 2026-11-07 |
| **ET-01** | `Passed` | `compose` 與 `presets`（含 `!project/p1`）循環引用立即拋出 `SpaceCycleError` 100% 通過 | 2026-11-07 |
| **RT-01** | `Passed` | 8 模組 `dev check` 全數 PASSED；`dev test -q` 全綠：`core` 268/268、`file-space` 18/18、`vscode-support` 22/22、`gdrive-support` 34/34、`server` 62/62、`ast` 37/37、`knowledge-db` 109/109、`agents-workflow` 145/145 | 2026-11-07 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 執行 `python yscb.py fs spaces` 與 `python yscb.py fs status`，並檢視 `.gitignore` 與 `.vscode/settings.json`：確認 `core/workspace` 與 `core/gitignore` 正常列舉、`.gitignore` 按 `# [<owner>]` 分組輸出規則與 `!<pattern>` 豁免、且 VS Code 排除規則已正規化為 `**/...` Glob | `[測試通過]` | 已依開發者指示建立臨時兄弟目錄 (`/workspace/ys-codebase-sub05-verify`) 完成 6 階段全功能實機驗證（CLI/SDK/`!<preset>` 子樹剪枝/`!<compose>` 差集/`gitignore` 正向物化/`vscode-support` Glob 正規化/快照鍵隔離），驗證後已清除臨時目錄 |
