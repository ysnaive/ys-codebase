# 需求規格說明書 (Requirements Specification)

> 功能名稱：新世代全量複檢收尾與發布前最終打磨 (Global Step 1~13 Pre-Release Polish)  
> 建立日期：2026-10-25  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `dev` 平行沙盒生命週期與執行緒鎖防護 | 於 `SandboxProvisioner` (`sandbox.py`) 引入 `_SANDBOX_LOCK` 保護 `create_sandbox`、`prune_sandboxes` 與 `cleanup_sandbox`；將 `prune_sandboxes` 預設 `max_keep` 提升至 `8`（大於平行模組數 5）；當 `os.environ.get("YSCB_TEST_SANDBOX") == "1"` 時跳過 `create_sandbox()` 內部的 `prune_sandboxes`；且於 `tester.py` `_run_single_module_worker` 結束時不提前觸發跨模組 `prune_sandboxes`，統一由 `_run_parallel_test` 彙整結束後執行 `prune_sandboxes(max_keep=8)` | P0 | [P00:DR-02] |
| **FR-02** | `agents-workflow` 章節標題否定詞前綴防誤配 | 於 `PlanVerifier._is_header_match(exp_norm, dh)` (`verifier.py`) 實作章節正規化標題匹配輔助方法：當較長標題包含較短標題（如 `exp_norm="非功能需求"` vs `dh="功能需求"`），但較長標題在較短標題前緊接否定前綴（`非`、`不`、`無`、`未`）時，判定為語意相反之不同章節並回傳 `False` | P0 | [P00:DR-03] |
| **FR-03** | `knowledge-db` 符號定位 `ftypes` 透傳與配置降級提示對齊 (`K-04`, `K-07`) | 1. `knowledge_db/pipeline.py` 之 `act_callers`、`act_callees`、`act_impact` 呼叫 `self.find_target_symbol(target_query, space=space, ftypes=ftypes)` 補傳 `ftypes=ftypes`<br/>2. `knowledge_db/pipeline.py` 向量檢索降級提示統一改為 `python yscb.py config set knowledge-db enable_vector_search false`<br/>3. `knowledge_db/config.py` 移除讀取根目錄舊版 `yscb.config.json` 內嵌 `knowledge-db` 區塊之遺留分支 | P0 | [P00:DR-01] |
| **FR-04** | `knowledge-db/contributes/core.json` 完整契約對齊 (`K-06`, `K-08`) | 1. 補齊頂層 `"hooks"` 宣告區塊（`dev: on_test_setup / on_test_teardown` 與 `server: server_worker_warming`）<br/>2. `status` 補宣告 `--all` (`-a`)、`--space`、`--json` 並移除描述中殘留之「同義詞」字眼<br/>3. `search` 補宣告 `--kind`、`--lang`<br/>4. `callers`/`callees`/`impact` 補宣告 `--limit`，並移除 `impact` 無效之 `-s`/`--preview` 選項 | P0 | [P00:DR-01] |
| **FR-05** | `server/tests/test_server.py` 測試純化收尾 (`ST-01~ST-03`) | 合併 `test_server.py` 中 3 組重複測項（`test_worker_pool_saturation`、`test_ipc_large_payload_64kb`、`test_daemon_lifecycle`），並移除靜態字面量檢查 `test_server_manifest_metadata` 與 `test_server_logging.py` 重複之手動模擬寫入測項 | P1 | [P00:DR-01] |
| **FR-06** | 三層知識庫文檔與 `CHANGELOG.md` 同步對齊 | 1. `docs/agents-workflow/DESIGN_NOTES.md`：更新 `[DN-AW-12]` 與 `[DN-AW-15]` 說明於 `sub_09` (`[DN-AW-16]`) 之演進<br/>2. `CHANGELOG.md`：修正 `sub_08` 6 檔測試清單檔名（`test_targets.py, test_roadmap.py`）<br/>3. `docs/core/README.md`：更新 `DN-01 ~ DN-13` 並移除舊 `workflow.*://` 特判敘述<br/>4. `docs/knowledge-db/README.md`：移除已刪除之 `tokenizer.md` 連結 | P1 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `dev test --all -q` 平行執行時，`core` 內部 `ISOLATED_SANDBOX` 測項在子行程內再次呼叫 `SandboxProvisioner.create_sandbox()` | 子行程 (`YSCB_TEST_SANDBOX == "1"`) 內建立獨立沙盒時，不觸發全域 `prune_sandboxes`，且投影 `.venv` 時若當前 `host_yscb_d/.venv` 本身為指向宿主 `.venv` 的 Junction/Symlink，解析其真實目標路徑（`os.path.realpath`）再建立新沙盒 Junction，杜絕巢狀 Junction 失效或父沙盒解綁影響 |
| **EC-02** | `PlanVerifier` 比對 `## 1. 功能需求清單` 與 `## 3. 非功能需求` 時，正規化字串分別為 `功能需求` 與 `非功能需求` | `_is_header_match("非功能需求", "功能需求")` 檢測到較長字串前綴為 `"非"` + `"功能需求"`，精準攔截並回傳 `False`，不產生假陽性匹配 |
| **EC-03** | `knowledge-db callers/callees/impact` 指定 `--ftype=py` 時同名符號存在於多個檔案類型 | `find_target_symbol` 接收 `ftypes=ftypes` 後過濾候選符號，僅匹配指定副檔名之目標符號 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 測試與靜態檢查守門 | `python yscb.py contributes check`、`python yscb.py dev check --all`、`python yscb.py agents-workflow plan verify --all` 與 `python yscb.py dev test --all -q` 100% 零錯誤通過 |
| **NFR-02** | 發布邊界控制 | 完成本計畫所有實作與驗證後，不主動執行 `/bump-revision` 或 `dev release` |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Windows Junction 巢狀投影與清理陷阱 (`docs/dev/DESIGN_NOTES.md` `[DN-DEV-03]`)**：在平行沙盒或子行程建立巢狀 `ISOLATED_SANDBOX` 時，務必使用 `os.path.realpath(host_venv_dir)` 取得實體 `.venv` 路徑建立 Junction，並避免子行程執行 `prune_sandboxes` 刪除平行執行中之兄弟模組沙盒。
- **`[!IMPORTANT]` Contributes Hook 命名對齊 (`docs/knowledge-db/DESIGN_NOTES.md`)**：`knowledge-db` 同時監聽 `dev` (`on_test_setup`, `on_test_teardown`) 與 `server` (`server_worker_warming`)，必須於 `contributes/core.json` 頂層 `"hooks"` 完整註冊。

