# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：新世代全量複檢收尾與發布前最終打磨 (Global Step 1~13 Pre-Release Polish)  
> 建立日期：2026-10-25  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 API 規格書與受影響檔案清單中有完整對應
- [x] **邊界防護**：EC-01 ~ EC-03 有具體錯誤處理與單元測試驗證策略
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-02 指標約束，零外部新依賴

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md`, `docs/knowledge-db/README.md` | Modify | 更新 `DN-01 ~ DN-13`、移除舊 `workflow.*://` 特判描述與失效 `tokenizer.md` 連結 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | None | 已於 `sub_09` 對齊，無需額外變更 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md`, `docs/dev/DESIGN_NOTES.md` | Modify | 補充 `[DN-AW-12]`、`[DN-AW-15]` 演進說明，並於 `[DN-DEV-03]` 補充平行沙盒鎖與子沙盒免 prune 機制 |
| **微觀註解** | `sandbox.py`, `verifier.py`, `pipeline.py` | Modify | 同步更新關鍵方法 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 修正 `sub_08` 測試檔名並記錄本次全量複檢收尾打磨摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若單獨呼叫 `SandboxProvisioner.prune_sandboxes()` 的單元測試預期預設 `max_keep=3` 怎麼辦？  
> [*] **防護解法**：檢查 `dev/tests/test_testing_infra.py` 中對 `prune_sandboxes` 的呼叫方式；若測試未顯式傳入 `max_keep`，或顯式傳入 `max_keep=2/3`，確保 `prune_sandboxes` 在非 `YSCB_TEST_SANDBOX` 或顯式指定 `sandbox_parent_dir` 時完全相容既有測試斷言，僅在 `create_sandbox()` 自動觸發時避免子沙盒互刪並使用 `max_keep=8`。

> [?] **尖銳問題 2**：`knowledge-db/contributes/core.json` 新增頂層 `"hooks"` 與 CLI 選項後，是否會影響 `dev check knowledge-db` 或 `contributes check`？  
> [*] **防護解法**：`hooks` 指向的 `scripts/hook.dev.py` (`on_test_setup`, `on_test_teardown`) 與 `scripts/hook.server.py` (`server_worker_warming`) 均已存在且實作完畢；補齊宣告後將執行 `contributes check` 與 `dev check --all` 實機驗證。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (`dev` 平行沙盒修復)**：修改 `ys_codebase/source/dev/dev/testing/sandbox.py` 與 `tester.py`，加入 `_SANDBOX_LOCK`、`_project_venv` `realpath` 解析、子沙盒跳過自動 `prune_sandboxes`，以及平行 worker 統一收尾清理。
2. **TASK-02 (`agents-workflow` 章節匹配修復)**：修改 `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`，實作 `_is_header_match` 防範否定詞前綴子字串誤配。
3. **TASK-03 (`knowledge-db` 契約與 `ftypes` 補齊)**：修改 `pipeline.py`、`config.py`、`contributes/core.json` 與 `tests/test_graph_and_impact.py`，落實 `K-04`、`K-06`、`K-07`、`K-08`。
4. **TASK-04 (`server` 測試純化收尾)**：修改 `ys_codebase/source/server/tests/test_server.py` 與 `test_server_logging.py`，合併重複測項並移除靜態 manifest 測項。
5. **TASK-05 (三層文檔對齊與 `@build` 同步驗證)**：更新 `docs/agents-workflow/DESIGN_NOTES.md`、`docs/dev/DESIGN_NOTES.md`、`docs/core/README.md`、`docs/knowledge-db/README.md` 與 `CHANGELOG.md`，重新安裝 `@build` 並執行 `contributes check`、`dev check --all`、`dev test --all -q` 全綠驗證。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 為確保 `dev/tests/test_testing_infra.py` 中直接測試 `prune_sandboxes` 預設參數之向下相容性，`prune_sandboxes(max_keep: int = 3, ...)` 保留簽名預設值 `3`，而由 `create_sandbox()`（僅限非 `YSCB_TEST_SANDBOX == "1"`）與 `tester.py` 呼叫時傳入 `max_keep=8`，並在 `_run_single_module_worker` 中移除執行中途的 `prune_sandboxes` 呼叫。

