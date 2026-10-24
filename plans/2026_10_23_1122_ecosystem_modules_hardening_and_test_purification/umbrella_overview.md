# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 建立日期：2026-10-23  
> 計畫狀態：In Progress  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：依循微內核生態系拓撲依賴順序（`core -> dev -> server -> knowledge-db`），全面執行四大核心模組之架構純化、功能與契約缺陷修復，並將各模組測試集全面對齊「子系統 1:1 歸戶、100% 實質斷言、零自寫自驗、零環境殘留」標準，消除歷史任務碎片測試檔與潛伏盲區。
- **架構邊界**：
  - 涵蓋 `ys_codebase/source/{core,dev,server,knowledge-db}/` 四大模組之核心程式碼、`contributes/` 契約宣告、`scripts/` 入口與 Hook、`tests/` 測試套件，以及對應之模組 `README.md` 與 `docs/` 系統知識庫文檔。
  - 嚴格遵守「`.modules/` 運行時剛性隔離（嚴禁向 `sys.path` 注入 `source/`）」、「微內核零上層業務耦合」與「`CmdBags` 精確命令函式契約」三大架構紅線。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_microkernel_and_tests` | Full Track | `Completed` | **微內核地基純化與測試收斂** — 合併落實 [roadmap.md](sub_01_core_microkernel_and_tests/roadmap.md)：清除 `core` 內殘留之 `agents-workflow` 耦合 (`C-01`)、補齊 `contributes check` 對 `config://<target>/contribute.json` 專案級覆寫之檢驗 (`C-02`)、修復 `_try_hot_dispatch` 多層子命令陣列傳遞 (`C-03`)、實作 `list --remote` 與 `config list --local / inspect / unset` (`C-04`, `C-05`)、統一群組節點未知子命令攔截與 `HelpRenderer` 輸出 (`C-06`)；同步將 `core/tests/` 由 28 檔收斂為 20 檔 (`T-01`~`T-06`)。 |
| **sub_02** | `sub_02_dev_toolchain_and_tests` | Full Track | `Pending` | **開發與測試工具鏈基建加固** — 合併落實 [dev_toolchain_and_sandbox_hardening_roadmap.md](../roadmap/dev_toolchain_and_sandbox_hardening_roadmap.md) 與 [dev_test_suite_purification_roadmap.md](../roadmap/dev_test_suite_purification_roadmap.md)：修復 `dev test` / `op-test` / `op-mksb` 選項契約與 `-k/-v/-q` 子進程無損傳遞 (`D-01`)、升級 `Releaser` Gate 3 全庫最高版本防回退與 `git commit` 錯誤攔截 (`D-02`)、落實 `UNKNOWN` 測試剛性阻斷與 `_FailedTest` / `NETWORK` 保留 (`D-03`)、修復 `Checker` 跨模組自訂規則載入與 `module.source://` Schema 優先讀取 (`D-04`)、汰除 `process(args)` 遺留範本並校正 `yscb-module-dev` 手冊 (`D-05`~`D-08`)；同步將 `dev/tests/` 由 10 檔收斂為 7 檔 (`DT-01`~`DT-05`)。 |
| **sub_03** | `sub_03_server_hosting_ipc_and_tests` | Full Track | `Pending` | **常駐服務託管、IPC 隔離與測試純化** — 合併落實 [server_service_hosting_and_ipc_hardening_roadmap.md](../roadmap/server_service_hosting_and_ipc_hardening_roadmap.md) 與 [server_test_suite_purification_roadmap.md](../roadmap/server_test_suite_purification_roadmap.md)：修復 `server/service.py` 漏寫 `import os` 並接入 `core.contributes` 與 `.modules/<provider>` 動態路徑注入 (`S-01`, `S-02`)、實作 Worker `_ipc_stdout` 私有句柄隔離與 `_kill_worker_locked` 兩階段 `exit` 優雅停機握手 (`S-03`)、修正 `start_time` 持久化並移除 `source/` 路徑注入與死代碼 (`S-04`~`S-07`)；同步將 `server/tests/` 由 4 檔收斂為 3 檔並消滅「自寫自驗」測試 (`ST-01`~`ST-04`)。 |
| **sub_04** | `sub_04_knowledge_db_pipeline_and_tests` | Full Track | `Pending` | **知識庫檢索管線、熱修補圖譜保真與測試收斂** — 合併落實 [knowledge_db_retrieval_pipeline_and_purity_roadmap.md](../roadmap/knowledge_db_retrieval_pipeline_and_purity_roadmap.md) 與 [knowledge_db_test_suite_purification_roadmap.md](../roadmap/knowledge_db_test_suite_purification_roadmap.md)：解除 `pipeline.search()` 冷啟動向量載入死鎖 (`K-01`)、實作調用圖譜熱修補外部入度邊雙階重連 (`Identity Remap` + `TopologyLinker`, `K-02`)、移除 `hook.server.py` 私自啟動之第二個 Watcher 並單一收歸 `server.ServiceManager` 託管 (`K-03`)、修復 `--ftype=c,cpp,py` 多副檔名過濾與 `find_target_symbol` 快取重用 (`K-04`)、徹底清除 `thesaurus` 與 `protocol.py` 死代碼 (`K-05`~`K-08`)；同步將 `knowledge-db/tests/` 由 14 檔收斂為 12 檔 (`KT-01`~`KT-05`)。 |
| **sub_05** | `sub_05_ecosystem_integration_and_acceptance` | Full Track | `Pending` | **跨模組端到端二次驗收與儲備遷移結案**：針對 `sub_01` ~ `sub_04` 落地成果執行全生態系 `dev check --all`、`contributes check` 與 `dev test --all` 聯合回歸驗證、實機驗證常駐 Server 託管 `knowledge-db-watcher` 與多層子命令熱派發閉環、透過 `roadmap promote` 閉環遷移本主計畫所消費之 8 份 Roadmap 儲備，並完成全模組 `@build` 同步與三層文檔結案。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

> **[GLOBAL PRIORITY] 跨主計畫 4 階段 10 步全局落地順序（最高優先級執行軌道）**：
> - **Stage 1（研發憲法與儲備工具鏈先行 — `2026_10_23_1314` 核心層）**：`1. AW/sub_02` (`/todo` 與 `roadmap promote`) $\to$ `2. AW/sub_03` (`testing-sop` 六大鐵律 + Subagent 三支柱隔離)
> - **Stage 2（微內核與開發工具鏈加固 — 本主計畫地基層）**：`3. ECO/sub_01` (`core` 微內核與測試純化) $\to$ `4. ECO/sub_02` (`dev` 沙盒檢查與測試純化)
> - **Stage 3（常駐服務與檢索管線加固 — 本主計畫運行層與結案）**：`5. ECO/sub_03` (`server` 託管與測試純化) $\to$ `6. ECO/sub_04` (`knowledge-db` 管線與測試純化) $\to$ `7. ECO/sub_05` (四模組聯合驗收與 8 份 Roadmap `promote` 閉環結案)
> - **Stage 4（下游賦能與擴充造血收官 — `2026_10_23_1314` 擴充層與結案）**：`8. AW/sub_04` (`PROJECT_ROLE` + `/how-to-config-yscb` + `/how-to-yscb`) $\to$ `9. AW/sub_05` (`/skill-creator` 三軌擴充) $\to$ `10. AW/sub_06` (`agents-workflow/tests/` 純化與 6 份 Roadmap `promote` 閉環結案)

- [x] **里程碑 1 (`sub_01`) [Global Step 3]**：完成 `core` 微內核純化、CLI 驗證／熱派發修復與 `core/tests/` 20 檔純化收斂，通過單元測試並完成 `@build` 熱部署。
- [ ] **里程碑 2 (`sub_02`) [Global Step 4]**：完成 `dev` 工具鏈契約對齊、3-Gate 全庫防回退、`UNKNOWN` 測試剛性阻斷與 `dev/tests/` 7 檔純化收斂，通過單元測試並完成 `@build` 熱部署。
- [ ] **里程碑 3 (`sub_03`) [Global Step 5]**：完成 `server` 背景服務託管修復、Worker IPC 隔離、優雅停機握手與 `server/tests/` 3 檔純化收斂，通過單元測試並完成 `@build` 熱部署。
- [ ] **里程碑 4 (`sub_04`) [Global Step 6]**：完成 `knowledge-db` 冷啟動向量檢索修復、熱修補入度邊雙階保真、同義詞純化與 `knowledge-db/tests/` 12 檔純化收斂，通過單元測試並完成 `@build` 熱部署。
- [ ] **里程碑 5 (`sub_05`) [Global Step 7]**：完成四大模組端到端整合二次驗收、8 份 Roadmap 儲備閉環遷移、三層文檔對齊與最終結案。

