# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：P3 效能與穩健性細節打磨 (sub_05_p3_polish)  
> 建立日期：2026-11-03  
> 所屬主計畫：2026_11_03_1018_issue_triage_remediation  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `_try_hot_dispatch` 在 `accepted=True`（請求已被 Worker 接收）後若發生逾時或中斷，直接回傳非零退出碼而不降級冷派發；`accepted=False`（未連線）則回傳 `None` 降級冷派發 | FR-01, EC-01 | `python yscb.py dev test --target=core:TestCommandDispatcher.test_dev01_try_hot_dispatch_accepted_never_falls_back_to_cold` |
| **FT-02** | 單元測試 | 驗證 `yscb.py` 與 `core/engine.py` 之 `_parse_simple_semver` 正確將預發布標籤排在正式版之前（`1.2.0-rc1 < 1.2.0`），且 `"1.0.0-rc1"` 不誤解析為 `"1.0.1"`；`_write_json_lf` 直接 `os.replace` | FR-02 | `python yscb.py dev test --target=core:TestPlatformPrimitives.test_t22_parse_simple_semver_prerelease` |
| **FT-03** | 單元測試 | 驗證 `core.uri` `_build_scheme_token_map` 快取、`OSBackend._real_root_dir` 快取、`telemetry` 尾端讀取與 `InterProcessLock._try_lock_fd` 對 `ENOTSUP`/`ENOSYS` 拋出 `OSError` | FR-03 | `python yscb.py dev test --target=core:TestPlatformPrimitives.test_t40_try_lock_fd_raises_on_unsupported_errno` |
| **FT-04** | 單元測試 | 驗證 `DebouncedIOStreamer` `max_buffer_bytes=4096` 緩衝上限（未滿 4096 時遇到 `\n` 不立即 flush，滿 4096 或 `flush()` 時送出）、`master.py` 複用 `get_venv_site_packages`、`_tasks_executed` 鎖內遞增與 `Checker` AST 快取 | FR-04, EC-05 | `python yscb.py dev test --target=server:TestServerLifecycle.test_t39_debounced_streamer_max_buffer_bytes` |
| **FT-05** | 單元測試 | 驗證 `UnifiedSymbol.from_dict` 反序列化 `children`/`members` 為 `Tuple[MemberInfo, ...]`（消除雙重實例化並相容 `.line`/`.fqn`）、`TopologyLinker` `deque` BFS 與繼承映射快取、`extract_call_sites` 預排序 | FR-05, EC-02, EC-04 | `python yscb.py dev test ast -q` |
| **FT-06** | 單元測試 | 驗證 `BM25Engine._score_candidate_documents` 計分前預過濾、`SnippetExtractor` 帶 `mtime_ns` 鍵之檔案行快取（檔案修改後自動失效）、`compiler` `@lru_cache` Regex 與 `PlanVerifier` 預編譯佔位符 Regex | FR-06, EC-03, NFR-01, NFR-02 | `python yscb.py dev test knowledge-db -q && python yscb.py dev test agents-workflow -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core` 246/246 通過（含 `test_dev01_try_hot_dispatch_accepted_never_falls_back_to_cold`） | 2026-11-03 14:23 |
| **FT-02** | `Passed` | `core` 246/246 通過（含 `test_t22_parse_simple_semver_prerelease`） | 2026-11-03 14:23 |
| **FT-03** | `Passed` | `core` 246/246 通過（含 `test_t40_try_lock_fd_raises_on_unsupported_errno`） | 2026-11-03 14:23 |
| **FT-04** | `Passed` | `server` 54/54 通過、`dev` 86/86 通過（含 `test_t39_debounced_streamer_max_buffer_bytes`） | 2026-11-03 14:23 |
| **FT-05** | `Passed` | `ast` 25/25 通過（含 `TestASTEnginePolish` 4 項新測試） | 2026-11-03 14:26 |
| **FT-06** | `Passed` | `knowledge-db` 108/108 通過、`agents-workflow` 141/141 通過，`dev check --all` 7/7 Passed | 2026-11-03 14:26 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 確認 `sub_05_p3_polish` 之 19 項 P3 打磨與 `DEV-01` 實作及 6 模組共 660 項單元測試回歸結果（或指示建立臨時兄弟目錄進行端到端實測） | `[測試通過]` | 已於臨時兄弟目錄 `/workspace/yscb-uat-sub05` 完成 `UAT-1` ~ `UAT-5` 端到端實測並清除臨時目錄，開發者確認通過 |

