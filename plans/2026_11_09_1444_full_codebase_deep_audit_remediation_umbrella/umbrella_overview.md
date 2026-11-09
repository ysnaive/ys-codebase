# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 建立日期：2026-11-09  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：將 2026-11-09 針對 `ys-codebase` 全倉（[`yscb.py`](https://drive.google.com/file/d/1t7Y-e98hP8W2c-51S87gN-fO4Q-7x24o/view?usp=drivesdk) 及 `core`、`ast`、`knowledge-db`、`server`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 八大活躍模組，共 218 個生產源碼/組態檔、10 個審計單元 `Unit 01` ~ `Unit 10`）執行之八維度單點序列深度審計報告（[`R01_full_codebase_deep_audit_report.md`](./R01_full_codebase_deep_audit_report.md)）檢出的全部 **67 項問題（4 P0 + 26 P1 + 26 P2 + 11 P3）** 全量轉化為 5 個職責正交之子計畫（`sub_01` ~ `sub_05`），徹底消除跨執行緒死鎖、增量熱修補資料抹除、常駐 Worker 管道阻塞、Symlink 憑證越界洩漏及三平台（Linux / Windows / macOS）邊界缺陷。
- **架構邊界**：
  - **對外公開介面與 CLI 契約 100% 向下相容（Mode B）**：不破壞既有模組 `contributes` Schema、CLI 參數簽名或公開類別方法契約；內部無外部呼叫端之私有實作細節採單一正統入口收斂（Mode A）。
  - **零第三方核心依賴與靜態守門合規**：所有修補 100% 遵守 `module:dev` 單次 AST 遍歷 13 項靜態守門規則（A1~F13 `0 FAIL, 0 WARN`），並通過全倉單元測試與 `0 ResourceWarning` 檢核。
  - **五階段正交子計畫拓撲推進順序（`sub_01` ~ `sub_05`）**：
    1. **`sub_01_core_bootstrap_and_space_remediation`（`Unit 01` & `Unit 02`）**：加固 `yscb.py` Bootstrap 與 `module:core` 跨行程鎖、回滾韌性、VFS/SpaceScanner Symlink 循環防護與 Windows 日誌輪替退避（共 10 項：`CORE-AUD-01` ~ `CORE-AUD-10`）。
    2. **`sub_02_ast_engine_and_parsers_remediation`（`Unit 03` & `Unit 04`）**：根除 `GrammarProvisioner` 全域鎖跨越 `pip install` 阻塞（P0 `AST-AUD-01`）、`ASTExtractor` 實例快取跨執行緒競態、`SemanticBridge` JSON-RPC 雙重讀取死鎖、UTF-8 多位元組偏移切片與多語言邊界解析缺陷（共 16 項：`AST-AUD-01` ~ `AST-AUD-16`）。
    3. **`sub_03_knowledge_db_pipeline_and_sqlite_remediation`（`Unit 05` & `Unit 06`）**：修復 `hot_patch_unified_index` C# `partial class` 連帶抹除主檔案非 partial 符號（P0 `KDB-AUD-01`）、`QueryService` 唯讀連線執行寫入、`DatabaseManager` 跨執行緒關閉連線競態、SQLite 999 參數批次切分與 FTS5 特殊字元轉義（共 14 項：`KDB-AUD-01` ~ `KDB-AUD-14`）。
    4. **`sub_04_server_dev_and_vscode_remediation`（`Unit 07` & `Unit 08`）**：建立 `MasterSupervisor` 單一擁有者背景 `stdout` 分流讀取器根除閒置 Pipe 死鎖（P0 `SRV-AUD-01`）、任務超時淘汰污染 Slot、修復 `CoreSpaceWatcher` 執行緒洩漏、`dev/checker.py` 巢狀作用域全域突變檢測與 `tester.py` 孤兒行程清理（共 12 項：`SRV-AUD-01` ~ `SRV-AUD-14`）。
    5. **`sub_05_agents_workflow_and_gdrive_remediation`（`Unit 09` & `Unit 10`）**：修復 `gdrive-support` 空間掃描與敏感憑證攔截之 Symlink 真實路徑解析漏洞（P0 `WF-AUD-01`）、OAuth2 Token 並發刷新鎖、`.yscb_gdrive.json` CAS 衝突重試、`agents-workflow` 孤兒編譯產物清理與 `SessionTraceManager` 並發寫入保護（共 13 項：`WF-AUD-01` ~ `WF-AUD-13`）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_bootstrap_and_space_remediation` | Full Track | `Completed` | `Unit 01` & `Unit 02`（`yscb.py` + `module:core`）：全量收斂 `CORE-AUD-01` ~ `CORE-AUD-10`（0 P0, 2 P1, 5 P2, 3 P3，共 10 項） |
| **sub_02** | `sub_02_ast_engine_and_parsers_remediation` | Full Track | `Completed` | `Unit 03` & `Unit 04`（`module:ast`）：全量收斂 `AST-AUD-01` ~ `AST-AUD-16`（1 P0, 7 P1, 5 P2, 3 P3，共 16 項） |
| **sub_03** | `sub_03_knowledge_db_pipeline_and_sqlite_remediation` | Full Track | `Completed` | `Unit 05` & `Unit 06`（`module:knowledge-db`）：全量收斂 `KDB-AUD-01` ~ `KDB-AUD-14`（1 P0, 6 P1, 5 P2, 2 P3，共 14 項） |
| **sub_04** | `sub_04_server_dev_and_vscode_remediation` | Full Track | `Completed` | `Unit 07` & `Unit 08`（`module:server`, `module:dev`, `module:vscode-support`）：全量收斂 `SRV-AUD-01` ~ `SRV-AUD-14`（1 P0, 6 P1, 6 P2, 1 P3，共 14 項） |
| **sub_05** | `sub_05_agents_workflow_and_gdrive_remediation` | Full Track | `Completed` | `Unit 09` & `Unit 10`（`module:agents-workflow`, `module:gdrive-support`）：全量收斂 `WF-AUD-01` ~ `WF-AUD-13`（1 P0, 5 P1, 5 P2, 2 P3，共 13 項） |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0（全倉深度審計與調研報告 `R01` 定稿）**：完成 `Unit 01` ~ `Unit 10` 共 218 個生產檔案之八維度單點序列深度審計與三步自我反駁（67 項問題 + 38 項 RFP），產出 [`R01_full_codebase_deep_audit_report.md`](./R01_full_codebase_deep_audit_report.md) 並完成 `sub_01` ~ `sub_05` 全量規格與測試計畫建檔。
- [x] **里程碑 1（`sub_01` 核心基座與空間掃描修補）**：完成 `CORE-AUD-01` ~ `CORE-AUD-10` 源碼修補與 `core` 單元測試驗收。
- [x] **里程碑 2（`sub_02` AST 引擎與多語言解析器修補）**：完成 `AST-AUD-01` ~ `AST-AUD-16` 源碼修補與 `ast` 單元測試驗收。
- [x] **里程碑 3（`sub_03` Knowledge-DB 管線與 SQLite 儲存層修補）**：完成 `KDB-AUD-01` ~ `KDB-AUD-14` 源碼修補與 `knowledge-db` 單元測試驗收。
- [x] **里程碑 4（`sub_04` Server 常駐管線、Dev 守門與 VSCode 支援修補）**：完成 `SRV-AUD-01` ~ `SRV-AUD-14` 源碼修補與 `server`/`dev`/`vscode-support` 單元測試驗收。
- [x] **里程碑 5（`sub_05` Agents-Workflow 與 GDrive 同步安全修補）**：完成 `WF-AUD-01` ~ `WF-AUD-13` 源碼修補、全倉 `dev check --all` 零違規與全倉單元測試 100% 通過結案。
- [x] **里程碑 6（模擬新環境全量部署與全 CLI 實機驗收結案）**：於乾淨沙盒環境自本地 Provider 執行 `yscb.py init` 與 9 大模組全量安裝，完成 75 項跨模組 CLI 指令（冷啟動與 `server` 熱 IPC 雙模式，含 `gdrive` 本地沙盒分支與同步）100% 通過驗收，並收斂新環境初始化之 5 項邊界問題（`knowledge_db/service.py` `_WORKER_LOCK` 可重入鎖、`gdrive_support/service.py` 與 `server/service.py` 未綁定 `project://` 安全待機、`core/contributes.py` 暫存目錄過濾與 `pip_manager.py` 離線快速退避、`agents-workflow` `init --default -y` 正交選項分組、`gdrive` 熱 IPC `get_virtual_cwd()` 相對路徑解析），全數子計畫進入 `P07` 結案（`Completed`）。

---

## 6. 第二輪九維度全量深度審計 (`R03`) 修復與新環境驗證閉環

- **第二輪九維度審計報告**：[`R03_round2_full_codebase_9d_deep_audit_report.md`](./R03_round2_full_codebase_9d_deep_audit_report.md)（雲端連結：[`R03_round2_full_codebase_9d_deep_audit_report.md`](https://drive.google.com/file/d/15XURUEyXkqMa3jv7lBy0U7MQcb_wbyFx/view?usp=drivesdk)）
- **審計與收斂規模**：針對第一輪修復後浮現之深層次交互邊界與 C9 架構演進技術債（A1~A5 & D1~D5），全倉 12 個審計分組共檢出 **94 項真實問題（14 P0 + 33 P1 + 31 P2 + 16 P3）** 及 **S1~S6 六大 Mode A 根因架構重構手術**，加上模擬新環境 78 項全 CLI 實機驗證揭露之 **2 項部署邊界問題**（共 **96 項**），已於五軌子計畫（`sub_01` ~ `sub_05`）100% 完成根因修復：
  - **`sub_01`（`yscb.py` + `core`）**：完成 `S1` 執行期 Context 傳遞純化（廢止 `os.environ["YSCB_CALLER_CWD"]` 行程汙染，改由 `ExtensionContext.caller_cwd` 顯式傳遞）、`InstallerEngine` 失敗自動回滾與 `--offline` 網路隔離、`RegistryClient` 20 MiB 串流下載上限與路徑穿越攔截、`VFS` 空字串與 Windows UNC 跨磁碟機攔截、`EventBus.wait_for` 執行緒安全喚醒與 `Logger` 輪替失敗冷卻退避（`core` **293/293** 測試通過）。
  - **`sub_02`（`ast`）**：完成 `S2` 跨模組共享契約（公開 `ast_engine.formatting.format_symbol_card` 供 `knowledge-db` 單一正統呼叫，消除雙重 AST 格式化）、`ASTEngine` 50 MiB 大檔防護、Tree-sitter 10 MiB 截斷與 5 秒解析逾時、`Wheelhouse` 50 MiB 串流下載與 `RECORD` SHA-256 強校驗、`ASTExtractor._ast_cache` 實例級 `RLock` 與 64 筆上限（`ast` **53/53** 測試通過）。
  - **`sub_03`（`knowledge-db`）**：完成 `S3` 索引器雙軌合一（刪除 `indexer.py` 內聯 `_parse_note_file` 重複邏輯，統一委派 `NoteParser`）、`VectorStore` 維度遷移時同步清空 `chunks_vec_meta` 觸發全量重算、WAL 模式下連接池 `busy_timeout` 與背景執行緒優雅釋放、`search_hybrid` 停用詞過濾與單詞 OR 降級、`cmd_rebuild` 失敗時保留舊快照（`knowledge-db` **117/117** 測試通過）。
  - **`sub_04`（`server` + `dev` + `vscode-support`）**：完成 `S4` 雙語系 IPC 與靜態守門收斂（`dev check` `RuleH14` 自動重用 `ast_engine.parsers` 檢查 `.ts/.js` 裸 `JSON.parse` 與 `fs.writeFileSync`）、`Server` Unix Domain Socket `0o600` 原子權限與 `SO_PEERCRED` 同 UID 驗證、Windows Named Pipe `FILE_FLAG_FIRST_PIPE_INSTANCE` 防劫持、`Worker` `sys.stdout` 執行緒隔離與 `ModulesWatcher.refresh_snapshot()` 手動 `reload` 快照同步（`server` **67/67**、`dev` **120/120**、`vscode-support` **23/23** 測試通過）。
  - **`sub_05`（`agents-workflow` + `gdrive-support`）**：完成 `S5` 上帝物件職責拆解（將 `gdrive_support/coordinator.py` 拆分為 `incremental_cache.py`、`ledger.py`、`readme_sync.py`；將 `transport.py` 拆分為 `sandbox_transport.py`、`auth_flow.py`；抽離 `agents_workflow/plans/state_machine.py`）與 `S6` 雙重 JSON 解析消除，並修復 `gdrive` 沙盒目錄位於 `project://` 內部時之自我遞迴排除防護（`agents-workflow` **147/147**、`gdrive-support` **37/37** 測試通過）。
- **全量驗證指標**：
  - `python3 yscb.py dev check`：**9/9 Modules PASS (`0 Warnings, 0 Failed`)**
  - `python3 -W error::ResourceWarning yscb.py dev test --all --no-build`：**869/869 Tests PASS (`0 Failed, 0 Skipped, 0 ResourceWarning`)**
  - 模擬全新部署環境（`sim_deploy_env_r2`）：**78/78 全 CLI 指令實機測試 100% PASS**

