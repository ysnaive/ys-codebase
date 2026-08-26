# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：模組資料管理相關 URI 協議釐清與遷移 (Module Data Management URI Protocol Alignment & Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Passed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證三大資料協議（`storage://`, `cache://`, `config://`）之物理映射路徑正確無誤，且 `temp://` 已被廢除。 | FR-01 | `python yscb.py dev test core -k test_vfs_uri_resolution` |
| **FT-02** | 單元測試 | 驗證方案 B 顯式跨模組尋址（`storage://dev/file`）與根空間（`storage://`）解算正確，且無雙重嵌套。 | FR-02 | `python yscb.py dev test core -k test_option_b_semantic_resolution` |
| **FT-03** | 單元測試 | 驗證方案 B 當前模組自省語法（`storage://@/file`）在上下文存在時正確展開為當前模組路徑。 | FR-02 | `python yscb.py dev test core -k test_active_module_placeholder_syntax` |
| **FT-04** | 整合測試 | 驗證標準卸載（`core:remove <mod>`）時自動清空 `cache`，並安全保留 `storage` 與 `config`。 | FR-03 | `python yscb.py dev test core -k test_remove_module_cache_clearing` |
| **FT-05** | 整合測試 | 驗證深度清除（`core:remove <mod> --purge`）時強制物理刪除 `storage`、`config` 與 `cache`。 | FR-03 | `python yscb.py dev test core -k test_remove_module_purge_flag` |
| **FT-06** | 整合測試 | 驗證 `dev` 沙盒測試環境自 `temp://` 遷移至 `cache://dev/sandbox/` (`.cache/dev/sandbox`) 後所有測試執行正常。 | FR-05 | `python yscb.py dev test dev` |
| **FT-07** | 整合測試 | 驗證 `agents-workflow` 發布時發布清冊正確寫入 `storage/agents-workflow/release_manifest.json`，且自動清理歷史遺留目錄。 | FR-06 | `python yscb.py dev test agents-workflow` |
| **ET-01** | 異常測試 | 驗證無上下文環境下調用 `@/` 自省語法時拋出 `UndefinedModuleContextError`（EC-01）。 | EC-01 | `python yscb.py dev test core -k test_active_module_without_context_raises_error` |
| **ET-02** | 安全測試 | 驗證路徑穿越攻擊（`../` 企圖逃逸協議根目錄）被安全攔截並拋出 PermissionError（EC-02）。 | EC-02 | `python yscb.py dev test core -k test_security_path_traversal_blocked` |
| **ET-03** | 相容測試 | 驗證調用舊版 `*.root://` 協議時自動發出 DeprecationWarning 並平滑重定向（EC-03）。 | EC-03 | `python yscb.py dev test core -k test_deprecated_schemes_redirection` |
| **ET-04** | 邊界測試 | 驗證執行 `--purge` 時若目標目錄不存在能平滑略過不拋出例外（EC-04）。 | EC-04 | `python yscb.py dev test core -k test_purge_non_existent_paths_safe` |
| **RT-01** | 全量回歸 | 執行全專案全模組回歸測試套件，維持 100% Passed (110/110 測試案例全綠)。 | NFR-03 | `python yscb.py dev test --all` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 驗證成果 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `storage://`, `cache://`, `config://` 正確解析為 `yscb://storage/`, `yscb://.cache/`, `yscb://config/`；`temp://` 拋出 UnknownSchemeError | 2026-08-26 18:44 |
| **FT-02** | `Passed` | `storage://dev/file.json` 正確解析為 `.../ys_codebase/storage/dev/file.json`，絕無 `storage/core/dev` 嵌套 | 2026-08-26 18:44 |
| **FT-03** | `Passed` | 在 `with uri.module_scope("my_mod"):` 下 `storage://@/data.json` 精準解析為 `.../storage/my_mod/data.json` | 2026-08-26 18:44 |
| **FT-04** | `Passed` | 模組卸載時自動清空 `cache://{mod}/`，確認 `storage://{mod}/` 與 `config://{mod}/` 完整保留 | 2026-08-26 18:44 |
| **FT-05** | `Passed` | 執行 `--purge` 卸載時安全物理刪除 `storage://{mod}/` 與 `config://{mod}/`，具備目錄邊界逃逸防護 | 2026-08-26 18:44 |
| **FT-06** | `Passed` | 沙盒建立於 `cache://dev/sandbox/sandbox_{timestamp}` (`.cache/dev/sandbox`)，25/25 dev 測試案例全數通過，測試後自動乾淨清理 | 2026-08-26 18:48 |
| **FT-07** | `Passed` | `agents-workflow` 發布清冊產出至 `storage/agents-workflow/release_manifest.json`，歷史遷移平滑生效 | 2026-08-26 18:44 |
| **ET-01** | `Passed` | 無模組上下文調用 `storage://@/file.json` 精準觸發 `UndefinedModuleContextError`，並提示 `module_scope` 解決方案 | 2026-08-26 18:44 |
| **ET-02** | `Passed` | 包含 `../` 企圖逃逸之 URI 被安全攔截，觸發 `PermissionError: Path traversal detected` | 2026-08-26 18:44 |
| **ET-03** | `Passed` | 調用 `storage.root://` 時觸發 `DeprecationWarning` 並成功重定向至 `storage://` | 2026-08-26 18:44 |
| **ET-04** | `Passed` | 當 `storage` 或 `config` 目錄不存在時執行 `--purge` 順暢無異常結束 | 2026-08-26 18:44 |
| **RT-01** | `Passed` | `python yscb.py dev test --all`：**110 Total, 110 Passed, 0 Failed, 0 Skipped (18.607s)** | 2026-08-26 18:44 |

---

## 3. 人工 / UX 驗證 Checkpoint

- [x] **UX-01**：在終端機檢視 `python yscb.py status` 與各模組指令，確認微內核運作健康、8 大標準協議清晰正交無報錯。
- [x] **UX-02**：檢視目前已打開的 [`storage/agents-workflow/release_manifest.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/storage/agents-workflow/release_manifest.json)，確認發布清冊已正確座落於標準 `storage/agents-workflow/` 下，且 `storage/core/agents-workflow/` 歷史遺留目錄已被清理。
