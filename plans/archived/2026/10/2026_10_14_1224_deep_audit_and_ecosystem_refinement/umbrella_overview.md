# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 建立日期：2026-10-14  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：
  1. 透過全專案雙向深度體檢（`Project -> Discover` 正向探索 + `Problems -> Project` 反向核對 `DESIGN_NOTES` 與 550 項單元測試，審計成果完整收錄於 [R01_full_project_audit_report.md](./R01_full_project_audit_report.md)），精準剔除 5 大類刻意設計/測試鎖定之誤判，並徹底修復 **42 項確鑿缺陷與文檔失真**。
  2. 完成兩項核心架構與體驗演進延伸子計畫：
     - **資產分類純化 (`agents-workflow`)**：廢除獨立 `workflow` 資產分類，將既有 Workflows 全面遷移收斂為標準 `skill` 架構，實現單一擴充模型與目錄拓撲純化。
     - **下游 UX/DX 與 CLI 可觀測性升級**：全面強化各模組指令的終端即時反饋（特別是 `server` 啟動參數橫幅、Console 即時日誌回顯、停機運行統計總結，以及各模組 CLI 進度與操作回報）。
- **架構邊界**：
  - 涵蓋宿主腳本 `yscb.py`、五大核心模組（`core`、`dev`、`server`、`knowledge-db`、`agents-workflow`）、專案設定檔（`ys_codebase/config/`）、知識庫文檔（`docs/`）與策略路線圖（`plans/roadmap/`）。
  - 嚴格遵守「最多兩層約束」（主計畫 -> `sub_XX` 子計畫），各子計畫獨立經歷完整生命週期與測試守門。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

本主計畫依「問題類型、模組耦合邊界與影響幅度」切分為 **4 個審計修復子計畫 (`sub_01` ~ `sub_04`)** 與 **2 個架構演進延伸子計畫 (`sub_05` ~ `sub_06`)**，共計 **6 個子計畫 ($4 + 2$)**：

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_host_and_core_foundation_remediation` | Full Track | `Completed` | **Host 與 Core 基礎設施修復**：修復 `ContributesAggregator` 跨模組同名指令覆蓋污染（保留頂層平鋪相容 `test_cli_router.py`，新增 `__modules__` 分桶修復 `yscb-cli-guild`）、`AtomicEngine` 108 行重複定義與 `mirror://` 快取失效、`PipManager`/`IdeProjector` 根目錄與 `.gitignore` 分叉、`_maybe_auto_spawn_server` 基於 `yscb_abs` 雙層組態讀取、`contributes list --module`、`uri` 安全邊界與 `contributes.merged.json` 記憶體快取、`yscb.py` 參數解析（保留 `DN-21` 相容代理函式與 `semver` 測試鎖定行為不動）。 |
| **sub_02** | `sub_02_dev_and_server_reliability_remediation` | Full Track | `Completed` | **Dev 工具鏈與 Server 並發可靠性修復**：修復 `dev` 中 `get_option()` 誤用寫入物件字串、`dev test -k` / `--target` / `-j` 失效、`dev create` 骨架三連敗、`release-check --all` 對齊、`Checker` 具名指令校驗（保留無 `commands.cmd` 時 `process` 相容測試）與 `custom_checks` 接線；修復 `server` 中 `dispatch_task` 無鎖 IPC 競態、Worker `stderr` 管線滿溢死鎖與 FD 洩漏、在 `WarmWorker` 端透過 `ServiceManager` 統一託管 `contributes/server.json` 背景服務並經 IPC 回報狀態（遵守 Master 純控制平面鐵律）、巢狀子指令解析與 `ServerLogger` 歷史清理正則。 |
| **sub_03** | `sub_03_knowledge_db_and_workflow_engine_remediation` | Full Track | `Completed` | **Knowledge-DB 檢索正確性與 Workflow 編譯引擎修復**：修復 `knowledge-db` 增量修補 `Path(p).name` 連坐誤刪全庫同名檔（引入 `canonical_path` 並相容 `test_hot_reload.py`）、`HybridSearchEngine` 前置空間過濾、非 mock 模式假向量污染、`clean()` 漏刪向量快取、抽取 `_ensure_jit_index_ready` 消除 `act_callers`/`callees`/`impact` 無謂向量推論（保留受測試鎖定之 SDK Deprecated 方法與 `thesaurus`/`protocol.py` 不動）；修復 `agents-workflow` Stage 0 Skill 目錄 SHA-1 空字串盲區、Stage 2 連結反引號與尾斜線缺陷、`PlanVerifier` 校驗脫節與 `session-analysis` 路徑。 |
| **sub_04** | `sub_04_docs_standards_and_docstring_alignment` | Full Track | `Completed` | **全專案知識庫 (`docs/`)、模組 README、Docstring 與 Roadmap 對齊**：全面更新 `docs/_project/STANDARDS.md`、`docs/core/`（含 `DN-09`/`SEMVER.md` 筆誤修正）、`docs/dev/`（含 `DN-DEV-02` 與 `yscb-module-dev` `CmdBags` 範例修正）、`docs/server/`（新增 `source/server/README.md` 並對齊 Worker `ServiceManager` 架構）、`docs/knowledge-db/`、`docs/agents-workflow/`，淘汰舊版 `*.root://`/`temp://` 協議與 `bundle`/`scan` CLI 教學，補齊 YAML Frontmatter、Mermaid 圖表與 `[!CAUTION]`，更新 `plans/roadmap/` 已落地項目狀態並支援狀態過濾。 |
| **sub_05** | `sub_05_agents_workflow_skill_unification` | Full Track | `Completed` | **[延伸 2.a] `agents-workflow` 資產分類純化 (Workflow 全面遷移為 Skill)**：廢除 `workflow` 資產類型，將既有 8 個模組級 Workflows 與專案級 `BumpRevision` 全面重構遷移為標準 `skill`（`SKILL.md` 架構），更新 `_format.json`、`compiler`、`publisher`、`release_target` 投影、跨檔超連結、舊 `.agents/workflows/` 自動清理機制與對應單元測試。 |
| **sub_06** | `sub_06_downstream_cli_ux_and_server_feedback` | Full Track | `Completed` | **[延伸 2.b] 下游 UX/DX 優化與指令反饋強化**：全面升級 CLI 終端互動反饋；於 `server start`（含背景與 `--console`）回饋完整啟動橫幅與運行參數（Master/Worker PID、Port、TTL、Watcher、Services、Log 路徑），支援前台 Console 即時日誌回顯，於 `server stop` 及停機時輸出運行總結報告（Uptime、累計處理任務數、停機原因、歸檔日誌路徑）；同步優化 `core`、`dev`、`knowledge-db`、`agents-workflow` 的 Help 導引與操作反饋。 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 0**：完成全專案雙向深度審計（`Project <-> Problems`），產出 [R01_full_project_audit_report.md](./R01_full_project_audit_report.md) 與主計畫藍圖
- [x] **里程碑 1 (`sub_01`)**：完成 Host `yscb.py` 與 `core` 模組底層缺陷與效能修復
- [x] **里程碑 2 (`sub_02`)**：完成 `dev` 工具鏈與 `server` 常駐模組並發安全與契約修復
- [x] **里程碑 3 (`sub_03`)**：完成 `knowledge-db` 檢索管線與 `agents-workflow` 編譯/驗證引擎修復
- [x] **里程碑 4 (`sub_04`)**：完成全專案知識庫 `docs/`、模組 `README.md`、Docstring 與 `roadmap` 100% 對齊
- [x] **里程碑 5 (`sub_05`)**：完成 `agents-workflow` 分類純化（全面遷移 `workflow` 為 `skill`）
- [x] **里程碑 6 (`sub_06`)**：完成 `server` 與全生態系 CLI 指令反饋與下游 UX/DX 升級並結案驗收
