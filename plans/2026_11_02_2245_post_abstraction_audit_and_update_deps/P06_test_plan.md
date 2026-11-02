# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：post_abstraction_audit_and_update_deps  
> 建立日期：2026-11-02  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元/整合測試 | `Installer.cmd_update` 更新已安裝模組時，自動解析新版新增之未安裝相依模組（`dep_new`）並自動升級不滿足新約束之既有相依模組（`dep_base` `1.0.0.0` $\to$ `1.2.0.0`）。 | FR-01 | `python yscb.py dev test core -q` (`TestCoreEngine.test_update_and_reconcile_dependencies_self_heal_and_conflict_rollback`) |
| **FT-02** | 單元/整合測試 | `AtomicEngine.reconcile_installed_dependencies` 與 `act_reload` Stage 1.5 於相依模組未註冊時自動拉取、註冊並物化補齊。 | FR-02 | `python yscb.py dev test core -q` (`TestCoreEngine.test_update_and_reconcile_dependencies_self_heal_and_conflict_rollback`) |
| **FT-03** | 單元測試 | `file_space.providers.get_knowledge_db_spaces` 與 `knowledge_db.providers.get_knowledge_db_spaces` 正確委派並渲染 Markdown 空間表；`knowledge_db` 與 `ast_engine` 透過 PEP 562 `__getattr__` 無損導出所有公開符號。 | FR-03, NFR-02 | `python yscb.py dev test file-space -q` & `python yscb.py dev test ast -q` & `python yscb.py dev test knowledge-db -q` |
| **FT-04** | 單元測試 | `knowledge_db.__version__ == "1.2.0.0"`、`ast_engine.__version__ == "1.0.0.0"`，且 `Checker._check_package_dunder_version` 對一致版號通過、不一致版號回報 `MANIFEST` `FAIL`。 | FR-04 | `python yscb.py dev test dev -q` (`TestDevChecker.test_checker_package_dunder_version_mismatch_detected`) |
| **FT-05** | 靜態/文檔驗證 | 根目錄 `README.md` 與 `docs/README.md` 完整反映 7 大模組與 `file-space -> ast -> knowledge-db` 三階 DAG，且 `agents-workflow release --force` 渲染 `.agents/skills/knowledge-db-search/references/registered-spaces.md` 完整三空間表。 | FR-05 | `python yscb.py agents-workflow release --force` |
| **ET-01** | 邊界測試 | 當兩個模組（`app_mod` 與 `peer_mod`）對同一相依模組（`dep_base`）要求無交集之版本約束（`>=1.3.0.0` vs `==1.2.0.0`）時，`cmd_update` 拋出衝突阻斷並透過 `act_restore_snapshot` 100% 回滾至更新前版號。 | EC-01 | `python yscb.py dev test core -q` (`TestCoreEngine.test_update_and_reconcile_dependencies_self_heal_and_conflict_rollback`) |
| **ET-02** | 邊界測試 | `@build`（`X.Y.Z.build`）模式下執行 `install`/`reload`/`update` 時，正確剝除 `.build` 比對基底版號相容性且不覆蓋本地 `@build` 模組。 | EC-02 | `python yscb.py dev test core -q` |
| **ET-03** | 邊界/效能測試 | 於屏蔽 `networkx` 與 `fastembed`（`sys.modules["networkx"] = None`, `sys.modules["fastembed"] = None`）環境下匯入 `knowledge_db`、`ast_engine` 及執行 `get_knowledge_db_spaces()` 100% 零崩潰且耗時 `< 20ms`。 | EC-03, NFR-01 | `python yscb.py dev test knowledge-db -q` (`TestKnowledgeDbFileSpace.test_et_03_providers_and_lazy_init_without_networkx_or_fastembed`) |
| **ET-04** | 邊界測試 | 模組未宣告 `__version__` 時 `dev check` 不誤報；宣告不一致字串常數時精準攔截。 | EC-04 | `python yscb.py dev test dev -q` (`TestDevChecker.test_checker_package_dunder_version_mismatch_detected`) |
| **RT-01** | 全量回歸測試 | 5 個受影響模組（`file-space`、`ast`、`knowledge-db`、`dev`、`core`）全量合規檢查與單元測試 100% 通過。 | FR-01 ~ FR-05 | `python yscb.py dev check <mod>` & `python yscb.py dev test <mod> -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `core` 測試集 221/221 (100.0%) 通過：`cmd_update` 自動補裝 `dep_new@1.0.0.0` 並將 `dep_base` 由 `1.0.0.0` 升級至 `1.2.0.0`。 | 2026-11-02 |
| **FT-02** | `Passed` | `core` 測試集 221/221 (100.0%) 通過：`act_reload` Stage 1.5 自動偵測並補回遭移除註冊之 `dep_new@1.0.0.0`。 | 2026-11-02 |
| **FT-03** | `Passed` | `file-space` 15/15 (100.0%)、`ast` 19/19 (100.0%)、`knowledge-db` 104/104 (100.0%) 通過。 | 2026-11-02 |
| **FT-04** | `Passed` | `dev` 測試集 83/83 (100.0%) 通過，且全模組 `dev check` 100% `[PASS]`。 | 2026-11-02 |
| **FT-05** | `Passed` | `agents-workflow release --force` 成功發布 72 檔，`registered-spaces.md` 完整包含 `docs`、`plans`、`source` 三空間表。 | 2026-11-02 |
| **ET-01** | `Passed` | `app_mod@1.2.0.0` (`dep_base>=1.3.0.0`) 與 `peer_mod@1.0.0.0` (`dep_base==1.2.0.0`) 無交集衝突時回傳 `rc=1` 並回滾至 `app_mod@1.1.0.0` 與 `dep_base@1.2.0.0`。 | 2026-11-02 |
| **ET-02** | `Passed` | `core@1.2.2.build`、`dev@1.1.3.build`、`file-space@1.0.0.build`、`ast@1.0.0.build`、`knowledge-db@1.2.0.build` 熱部署與相依解析全綠通過。 | 2026-11-02 |
| **ET-03** | `Passed` | 屏蔽 `networkx` 與 `fastembed` 下匯入 `knowledge_db`、`ast_engine` 與呼叫 `get_knowledge_db_spaces()` 通過且耗時 `< 5ms`。 | 2026-11-02 |
| **ET-04** | `Passed` | `TestDevChecker.test_checker_package_dunder_version_mismatch_detected` 驗證不一致報錯與修正後通過。 | 2026-11-02 |
| **RT-01** | `Passed` | 5 模組共 442 項測試（`core`: 221, `knowledge-db`: 104, `dev`: 83, `ast`: 19, `file-space`: 15）100.0% 通過，0 失敗、0 跳過。 | 2026-11-02 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `yscb.py update` / `act_reload` 相依交集自癒與無交集衝突回滾、`knowledge_db`/`file_space` 零第三方依賴空間表渲染、`dev check` `__version__` 守門，以及 `README.md` / `docs/README.md` 七大模組三階 DAG 文檔更新是否符合預期。 | `[跳過/免測]` | 開發者指示免測 |
