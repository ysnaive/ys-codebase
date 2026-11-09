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
