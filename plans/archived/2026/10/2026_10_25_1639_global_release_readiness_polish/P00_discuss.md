# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：新世代全量複檢收尾與發布前最終打磨 (Global Step 1~13 Pre-Release Polish)  
> 建立日期：2026-10-25  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對新世代版本翻新（Global Step 1 ~ 13）全量複檢所揭露之底層平行測試競爭、章節模糊匹配誤判、`knowledge-db`/`server` 微觀契約遺漏與知識庫文檔微幅出入，直接開立一個收尾修訂計畫完成全數打磨，但完成後先不要急著執行正式發布（`/bump-revision`）。
- **核心目標**：
  1. **平行沙盒互刪競爭修復 (`dev`)**：修復 `SandboxProvisioner` (`sandbox.py`) 與 `TestRunner` (`tester.py`) 在 `dev test --all` 平行啟動 5 個模組 worker 與子行程 `ISOLATED_SANDBOX` 時，因無鎖與 `prune_sandboxes(max_keep=3)` 過小導致平行執行中沙盒被誤刪之問題。
  2. **章節名稱子字串誤判修復 (`agents-workflow`)**：修復 `PlanVerifier` (`verifier.py`) 在比對模板章節時，`功能需求` 因是 `非功能需求` 的子字串而產生否定詞誤匹配的問題。
  3. **`knowledge-db` (`sub_04`) 與 `server` (`sub_03`) 微觀缺口補齊**：
     - `K-04`：`knowledge_db/pipeline.py` 之 `act_callers` / `act_callees` / `act_impact` 呼叫 `find_target_symbol` 補傳 `ftypes=ftypes`。
     - `K-06` / `K-08`：`knowledge-db/contributes/core.json` 補齊頂層 `"hooks"`（`dev` 與 `server` hooks），並對齊 `status` (`--all`/`--space`/`--json`)、`search` (`--kind`/`--lang`)、`callers`/`callees`/`impact` (`--limit`，移除 `impact` 無效 `-s`) CLI 宣告。
     - `K-07`：`knowledge_db/pipeline.py` 降級提示改為 `python yscb.py config set knowledge-db enable_vector_search false`，並清理 `knowledge_db/config.py` 讀取根目錄舊版 `yscb.config.json` 之殘留分支。
     - `ST-01~ST-03`：合併 `server/tests/test_server.py` 殘留重複測項並移除 `test_server_manifest_metadata` 靜態字面量檢查。
  4. **三層文檔與 `CHANGELOG.md` 同步對齊**：修正 `docs/agents-workflow/DESIGN_NOTES.md` (`[DN-AW-12]`、`[DN-AW-15]`)、`CHANGELOG.md` (`sub_08` 測試檔名)、`docs/core/README.md` (`DN-01 ~ DN-13` 與移除 `workflow.*://` 特判舊述) 及 `docs/knowledge-db/README.md` (移除失效 `tokenizer.md` 連結)。
- **邊界排除 (Explicitly Excluded)**：
  - 本計畫結案後**嚴禁主動觸發 `/bump-revision` 或 `dev release`**，僅將全模組打磨至 100% 測試與靜態檢查全綠狀態，靜候開發者後續指令。
- **架構影響範圍**：
  - `ys_codebase/source/dev/dev/{tester.py,testing/sandbox.py}`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`
  - `ys_codebase/source/knowledge-db/{contributes/core.json,knowledge_db/pipeline.py,knowledge_db/config.py}`
  - `ys_codebase/source/server/tests/test_server.py`
  - `docs/{agents-workflow/DESIGN_NOTES.md,core/README.md,knowledge-db/README.md}` 與根目錄 `CHANGELOG.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 計畫分流模式裁定 (Full Track)**：因涉及跨 4 個核心模組（`dev`、`agents-workflow`、`knowledge-db`、`server`）之底層 Bug 修復、Contributes 契約補齊與文檔同步，且總變更行數超過 Fast Track 100 行上限、包含業務邏輯錯誤修復（不適用僅限非業務表層調整的 Revision 模式），裁定採用 **標準開發計畫 (Full Track)**。
- **[P00:DR-02] 平行沙盒生命週期與執行緒安全守衛**：於 `SandboxProvisioner` 引入 `_SANDBOX_LOCK = threading.RLock()` 保護沙盒建立、註冊與清理；將預設 `max_keep` 調升至 `8`（大於全系統平行模組數 5），且當處於 `YSCB_TEST_SANDBOX == "1"` 子行程內或平行 worker 執行中途，禁止觸發跨沙盒 `prune_sandboxes` 誤刪兄弟模組沙盒，統一由 `_run_parallel_test` 彙整完畢後集中清理。
- **[P00:DR-03] 模板章節正規化否定前綴防誤配**：於 `PlanVerifier` 章節標題模糊匹配（`exp_norm in dh or dh in exp_norm`）加入否定詞前綴守衛（當較長字串以 `非`、`不`、`無`、`未` 緊接較短字串起始時，例如 `"非" + "功能需求"`，視為相反語意章節不予匹配）。
- **[P00:DR-04] 發布守門邊界**：依開發者明確指示，本計畫完成並通過 `dev check --all`、`contributes check`、`plan verify --all` 與 `dev test --all -q` 全綠驗收後即停駐，不執行版本號遞增與正式發布。

---

## 3. 開放議題與確認紀錄

- 全部複檢項目與邊界已於前置審查對齊確認，無未決開放議題。

