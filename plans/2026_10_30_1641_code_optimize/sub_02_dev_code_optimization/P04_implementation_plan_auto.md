# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_dev_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 API 規格書中有對應介面與方法簽名定義
- [x] **邊界防護**：EC-01 ~ EC-05 有具體錯誤處理、鎖保護與異常回滾策略
- [x] **依賴純淨**：100% 符合 NFR-01 ~ NFR-03 指標約束，零跨模組越界修改

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/dev/README.md` | None | 內部實現純化與別名清除，公開 CLI 用法無變更 |
| **專題手冊** | `ys_codebase/source/dev/assets/usage_guide.md` | None | 標準 CLI 契約維持不變 |
| **設計決策** | `plans/2026_10_30_1641_code_optimize/sub_02_dev_code_optimization/R01_code_optimization_audit.md` | None | 已於調研階段定稿 |
| **微觀註解** | `ys_codebase/source/dev/dev/*.py` & `scripts/cli.py` Docstrings | Modify | 同步更新重構後之函式簽名與模組 Docstring |
| **發布日誌** | `plans/2026_10_30_1641_code_optimize/sub_02_dev_code_optimization/changelog.md` | Modify | 透過 `plan verify --log` 記錄 `/auto` 推進摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：`Checker` 移除 `def process(args)` 相容分支後，若測試建立之最小假模組未提供 `contributes/core.json`，`_check_cli_compliance` 如何判定 `scripts/cli.py` 合規？  
> [*] **防護解法**：當模組未定義 `contributes/core.json` 之 `commands.cmd` 時，檢查 `scripts/cli.py` 是否至少宣告一個非私有（不以 `_` 開頭）且非 `main` 的頂層函式（如 `def hello(cmd_bags)`），同時更新 `test_checker.py` 假模組樣板，徹底淘汰 `def process(args)`。

> [?] **尖銳問題 2**：將 `uri.exists` / `uri.read_json` 遷移至 `vfs.exists` / `vfs.read_json` 後，既有單元測試若 `patch("core.uri.exists")` 是否會失效？  
> [*] **防護解法**：`vfs.exists` 底層呼叫 `uri.resolve` 再檢查 `os.path.exists`；在 `test_sandbox.py` 中直接將 `patch("core.uri.exists")` 同步更新為 `patch("core.vfs.exists")` 與 `patch("core.uri.resolve")`，確保測試與生產代碼一致。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`requirement.py` & `scaffold.py`)**：清除 `Requirement` 舊別名、`Scaffolder` 空 `__init__` 與 `author`/`desc` 殭屍參數，將 `scaffold.py` I/O 遷移至 `vfs` (`FR-01`, `FR-02`, `FR-03`)。
2. **TASK-02 (`checker.py`)**：刪除 `CheckReport` 序列解包方法、空 `__init__`、`def process(args)` 與 `"ISOLATE_SANDBOX"` 分支；拆解 `_check_cli_compliance` 與 `_check_test_classes` 為扁平化純函式並遷移至 `vfs`；提煉共用 `discover_source_modules` 探索入口 (`FR-01`, `FR-02`, `FR-03`, `FR-07`, `EC-05`)。
3. **TASK-03 (`builder.py` & `releaser.py`)**：抽取 `_create_module_archive_atomic`（含 `.zip.tmp` `try...finally` 清理）與 `resolve_module_dependency_order`；刪除 `Builder._should_ignore` 孤兒轉發方法、`ReleasePipeline`、死例外與 `skip_tests`；收斂 `discover_source_modules`、更新 `CheckReport` 屬性存取並遷移至 `vfs` (`FR-01`, `FR-02`, `FR-03`, `FR-05`, `FR-08`, `EC-02`, `EC-04`)。
4. **TASK-04 (`sandbox.py`, `case.py`, `contract.py`, `runner.py`, `testing/__init__.py`)**：修復 `SandboxProvisioner` `_SANDBOX_LOCK` 與 `create_sandbox` 失敗回滾並拆解為 4 階段；提煉 `_sweep_sandboxes` 與 `_find_latest_build_zip` 消除 `prune_sandboxes`/`cleanup_all_sandboxes` 及 `@build` zip 搜尋重複；收斂 `discover_source_modules`；移除 `quiet` 與 `active_types` 殭屍參數、空 `tearDownClass` 與多餘匯出；遷移至 `vfs` 與 `uri` 公開 scope API (`FR-02`, `FR-03`, `FR-04`, `FR-08`, `EC-01`, `EC-03`)。
5. **TASK-05 (`tester.py` & `scripts/cli.py`)**：引入 `_TestRunConfig` 與 `_execute_single_module_in_sandbox` 收斂單模與平行測試管線；收斂 `scripts/cli.py` 之 `check()` 單模/全模報表迴圈、`release_check()` 模組探索與 `vfs` 調用 (`FR-01`, `FR-02`, `FR-03`, `FR-06`)。
6. **TASK-06 (`tests/` 同步與語法驗證)**：同步更新 `test_checker.py`、`test_release_pipeline.py`、`test_case.py`、`test_sandbox.py`、`test_scaffold.py` 並執行 `python -m py_compile` 靜態語法檢核 (`FR-01` ~ `FR-08`)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 並行批次驗證策略對齊**：依主計畫並行隔離規則，Phase 05 完成後以 `python -m py_compile` 驗證全數修改檔案之 Python 語法零錯誤，並跳過子代理階段之 `dev test` / `dev build` 實機執行，交由主 Agent 於 5 個子計畫全數抵達 P06 後統一執行編譯與沙盒測試。
