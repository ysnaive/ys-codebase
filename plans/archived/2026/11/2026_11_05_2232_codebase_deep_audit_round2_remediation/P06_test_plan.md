# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：全專案第二輪八維度深度審計與反向溯源收斂修復 (Codebase Deep Audit Round 2 Remediation)  
> 建立日期：2026-11-05  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `InterProcessLock.acquire` POSIX `(st_dev, st_ino)` 比對與 `AtomicEngine.act_lock` 過期鎖非阻塞探測自癒 | FR-01, EC-01 | `python yscb.py dev test core -q` |
| **FT-02** | 單元測試 | 驗證 `process.py:can_spawn_background_daemon` 使用 4-byte `wintypes.BOOL` 與 `wintypes.HANDLE` | FR-02, NFR-02 | `python yscb.py dev test core -q` |
| **FT-03** | 單元測試 | 驗證 `dispatcher.clear_cache()` 清空註冊表與模組快取，且 `engine.act_reload` 同步呼叫及 `_load_registry` 排序容錯 | FR-03 | `python yscb.py dev test core -q` |
| **FT-04** | 單元測試 | 驗證 `gitignore.py`、`installer.py` 之 `os.path.realpath` 軟連結根目錄對齊與 `pip_manager.py` `_WHEEL_PKG_DIR=None` 防護 | FR-04, NFR-02 | `python yscb.py dev test core -q` |
| **FT-05** | 單元測試 | 驗證 `venv._is_source_tree_path` 上層含 `/source/` 豁免與 `OSBackend.copy` 同源路徑及子目錄遞迴攔截 | FR-05 | `python yscb.py dev test core -q` |
| **FT-06** | 單元測試 | 驗證 `YSCBTestCase.create_mock_source_module` 保留預設 `test_dummy.py` 並允許自訂 `contributes/core.json` 落盤 | FR-06 | `python yscb.py dev test dev -q` |
| **FT-07** | 單元測試 | 驗證 `tester.py:_run_test` 於 `cfg.is_all` 或預設全量測試時透過 `TestDiscovery.discover_modules(None)` 補齊 `tested_mods` | FR-07 | `python yscb.py dev test dev -q` |
| **FT-08** | 單元測試 | 驗證 `PlanVerifier.verify_plan` 對 `sub_*` 子計畫執行三步自癒管線並豁免 `Seeded` 子計畫 | FR-08, EC-04 | `python yscb.py dev test agents-workflow -q` |
| **FT-09** | 單元測試 | 驗證 `releaser.py:_run_git_cmd` 與 `session_trace.py:_get_git_changed_files` 具備 `encoding="utf-8", errors="replace", stdin=DEVNULL` | FR-09 | `python yscb.py dev test dev -q` |
| **FT-10** | 單元測試 | 驗證 `knowledge_db/service.py:write_worker_state` 具備 5 次 `PermissionError` 退避重試與異常 `.tmp` 清理 | FR-10 | `python yscb.py dev test knowledge-db -q` |
| **FT-11** | 單元測試 | 驗證 `semver.match_constraint` 預發布/build 守衛、`act_solve_deps` 雙範圍算符合併與 `isinstance(meta, dict)` 防護 | FR-11 | `python yscb.py dev test core -q` |
| **FT-12** | 單元測試 | 驗證 `validator.parse_type_signature` 括號平衡解析 `dict[str, enum(a, b, c)]` 與 `contributes.get()` 深拷貝隔離 | FR-12 | `python yscb.py dev test core -q` |
| **FT-13** | 單元測試 | 驗證 `status.py:_resolve_p00_next_action` 支援 `P00_*.md` 動態解析與 `agents-workflow init` 支援 `--path-roadmap` | FR-13 | `python yscb.py dev test agents-workflow -q` |
| **FT-14** | 單元測試 | 驗證 `sandbox.py:cleanup_sandbox` 活躍沙盒守門順序與 `normcase`、`server/master.py` PID 快照及 `watcher.py` 鎖探測移位 | FR-14 | `python yscb.py dev test server -q` |
| **FT-15** | 單元測試 | 驗證 `knowledge_db/engine.py:clean` 委派重置、`retrieval.py` C# 鍵值、`file-space` 單檔過濾與 O(1) 前綴、`ast` 行號指紋與 12 檔零工單註解合規 | FR-15, EC-02, EC-03, EC-05, EC-08, NFR-01, NFR-03 | `python yscb.py dev test file-space -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | 同進程過期鎖重入自癒與跨實例非阻塞互斥皆通過 | 2026-11-05 |
| **FT-02** | `Passed` | AST 靜態檢查與 `sizeof(wintypes.BOOL) == 4` 驗證通過 | 2026-11-05 |
| **FT-03** | `Passed` | 快取清空、`"core"` 優先排序與別名衝突警告驗證通過 | 2026-11-05 |
| **FT-04** | `Passed` | 模擬 macOS 軟連結根目錄產出 `/ys_codebase/.venv/` 正確相對路徑 | 2026-11-05 |
| **FT-05** | `Passed` | `/tmp/.../source/host/ys_codebase/.modules/core` 回傳 `False`；子目錄複製拋出 `ValueError` | 2026-11-05 |
| **FT-06** | `Passed` | 自訂 `contributes/core.json` 與預設 `tests/test_dummy.py` 同時存在 | 2026-11-05 |
| **FT-07** | `Passed` | 驗證 `tester.py` AST 與分支邏輯 100% 覆蓋單模組、指定模組與全量模式 | 2026-11-05 |
| **FT-08** | `Passed` | 活躍子計畫自動補齊 `P06_test_plan.md` 且零孤兒條目警告 | 2026-11-05 |
| **FT-09** | `Passed` | 靜態與執行期單元驗證確認 Git 子進程參數完整包含 UTF-8 編碼、容錯與超時防護 | 2026-11-05 |
| **FT-10** | `Passed` | 模擬轉態檔寫入與異常中斷確認 `.tmp` 檔案零殘留 | 2026-11-05 |
| **FT-11** | `Passed` | `1.0.0-alpha.1` 對 `1.0.0` 回傳 `False`，正常三段式 `1.2.3.4` 對 `1.2.3` 回傳 `True` | 2026-11-05 |
| **FT-12** | `Passed` | 巢狀 `enum` 正確解析且快取命中 | 2026-11-05 |
| **FT-13** | `Passed` | `P00_custom.md` 正確解析下一步行動且 `init` 選項符合 Schema | 2026-11-05 |
| **FT-14** | `Passed` | 沙盒保護守門觸發 `RuntimeError` 時目標路徑仍保留於 `_ACTIVE_SANDBOXES` | 2026-11-05 |
| **FT-15** | `Passed` | 全數 40 個修復檔案通過 `ast.parse` / `json.loads`、零工單註解與契約斷言 | 2026-11-05 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視第二輪深度審計修復成果與全倉 7 大受影響模組 (`core`, `server`, `dev`, `agents-workflow`, `file-space`, `ast`, `knowledge-db`) 之合規與沙盒測試狀態 | `[測試通過]` | 全倉 9 模組 `dev check --all` 100% 通過，7 大受影響模組共 715 項沙盒單元測試 100% 通過並完成 `@build` 熱同步，盲眼靜態審查 `REVIEW_STATUS: PASSED` |
