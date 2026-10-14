# 技術調研報告：全專案架構、原始碼、文檔、效能與下游 DX 深度審計報告 (含雙向驗證)

> 調研主題：全專案深度健康度審計與雙向驗證 (Project $\leftrightarrow$ Problems Bidirectional Audit)  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 調研狀態：Concluded  
> 模板版本：v1.0  

---

## 1. 審計方法論：雙向交叉驗證 (Bidirectional Audit Methodology)

本次審計採用嚴謹的**雙向交叉驗證（Two-Pass Bidirectional Verification）**：
1. **第一階段（Forward Pass：`Project -> Discover`）**：對 `yscb.py`、五大核心模組（`core`、`dev`、`server`、`knowledge-db`、`agents-workflow`）、`ys_codebase/config/`、`docs/` 與 `plans/roadmap/` 進行 100% 唯讀深度掃描，發掘所有潛在架構缺陷、隱性 Bug、效能瓶頸、註解/文檔失真與 DX 痛點。
2. **第二階段（Reverse Pass：`Problems -> Project`）**：針對第一階段發掘的每一項問題，反向查證全專案 `DESIGN_NOTES.md` (`DN-XX`)、`CHANGELOG.md`、歷史計畫決策 (`DR-XX`) 與全套 550 項單元測試，嚴格區分：
   - **`[CONFIRMED BUG]`（確鑿缺陷）**：實作錯誤或遷移遺漏，無過往設計衝突或測試鎖定，可直接修復。
   - **`[PARTIAL / NUANCED]`（需精緻化修復）**：缺陷確實存在，但周邊存在特定架構決策或單元測試契約約束；必須採用精緻化修復方案，避免破壞既有設計或引發測試回歸。
   - **`[INTENTIONAL / TEST-LOCKED]`（刻意設計或測試鎖定 — 排除代碼修改）**：經反向查證確認為過往明確的架構設計決策（或作為向後相容契約受單元測試鎖定），**嚴禁誤當作死碼或 Bug 修改代碼**（僅同步更新過時文檔說明）。

### 雙向驗證後之統計總覽

| 模組 / 領域 | `[CONFIRMED BUG]` | `[PARTIAL / NUANCED]` | `[INTENTIONAL / TEST-LOCKED]`<br/>*(排除代碼改動)* | 有效需修復總計 |
| :--- | :---: | :---: | :---: | :---: |
| **Host (`yscb.py`) & `core` 模組** | 6 | 4 | 2 *(7a, 10)* | **10** |
| **`dev` 模組** | 4 | 2 | 1 *(DN-DEV-02)* | **6** |
| **`server` 模組** | 3 | 1 | 0 | **4** |
| **`knowledge-db` 模組** | 3 | 2 | 1 *(Deprecated/Thesaurus 介面)* | **5** |
| **`agents-workflow` 模組** | 3 | 2 | 1 *(Computed Token / Manifest URI)* | **5** |
| **全專案知識庫 (`docs/` / `README` / `roadmap`)** | 12 *(Doc Drift)* | 0 | 0 | **12** |
| **合計** | **31** | **11** | **5 大類 (已精準剔除誤判)** | **42** |

---

## 2. 第二階段反向驗證 (`Problems -> Project`) 關鍵攔截與修正成果

> [!IMPORTANT]
> 透過 `Problems -> Project` 反向核對 `DESIGN_NOTES.md` 與 550 項單元測試，成功攔截了 **5 大類「表面看似死碼或 Bug、實為刻意設計或受測試鎖定」** 的項目，以及 **7 項「必須遵守特定設計/測試邊界」** 的精緻化修復約束：

### 2.1 確認為「過往刻意設計 / 測試鎖定」而排除代碼改動之項目 (`[INTENTIONAL / TEST-LOCKED]`)

| 編號 | 原疑似問題 | 反向查證證據 (`DESIGN_NOTES` / `tests/`) | 最終處置決策 |
| :---: | :--- | :--- | :--- |
| **REV-01** | `yscb.py:467-579` 未被 `main()` 呼叫之私有函式與 `core/contributes.py:print_global_help` 疑似死碼 | 1. `docs/core/DESIGN_NOTES.md` **`[DN-21]` 第 3 點**明載：「*向後相容最小安全代理：宿主保留對 `core.installer` 與 `core.events` 的薄代理函式*」。<br/>2. `test_restore_and_jit_modules.py`、`test_remote_zip_bootstrap.py`、`test_cli_router.py`、`test_contributes_help.py` 直接 import 並驗證這些代理函式。 | **[保留代碼]**<br/>屬 `[DN-21]` 刻意設計之相容契約，嚴禁刪除。 |
| **REV-02** | `core/semver.py` 中 `revision` 大小比較方向（`1.0.0.2 > 1.0.0.1`）及 `~=` 鎖定 Major 與 `DN-09` / `SEMVER.md` 矛盾 | `test_semver.py:72-76` 明確斷言 `compare_semver("1.0.0.2", "1.0.0.1") == 1`；`test_semver.py:125-127` 明確斷言 `~=` 鎖定 Major（同 `[DN-10]`）。代碼為正確設計，係文檔 `DN-09` 與 `SEMVER.md` 筆誤。 | **[保留比較邏輯 / 僅修文檔]**<br/>僅修正 `VersionTuple.__str__` 含 `prerelease` 時漏拼非零 `revision`，並於 `sub_04` 修正 `DN-09` 與 `SEMVER.md` 敘述。 |
| **REV-03** | `dev` 測試狀態為 `UNKNOWN` 時未保留沙盒，與 `DN-DEV-02` 文檔不符 | `dev/testing/case.py:149-160` 內含明確設計註解：`# 未明確標記 passed 也未失敗：安全清理沙盒`、`# 歸類為 UNKNOWN：嚴禁輸出 [Test Failed]`，避免沙盒洩漏與假警報；漏寫 `mark_passed()` 改由 `dev check` 靜態攔截。 | **[保留代碼 / 僅修文檔]**<br/>代碼為刻意演進設計，於 `sub_04` 更新 `docs/dev/DESIGN_NOTES.md` (`[DN-DEV-02]`)。 |
| **REV-04** | `knowledge-db` 標註 `[Deprecated]` 之 `scan`/`bundle`/`build_index` 方法、`thesaurus` 欄位與 `protocol.py` / `CallGraphNode` | 1. `test_engine.py`, `test_scanner.py`, `test_bundler.py` 直接呼叫並斷言 `scan`/`bundle`/`build_index`。<br/>2. `test_space.py:173-183` 直接斷言 `contributes/knowledge-db.json` 必須包含 `"languages"`, `"thesaurus"`, `"aliases"` 三個鍵。<br/>3. `test_graph.py:188-212, 278-291` 直接測試 `protocol.py` 與 `CallGraphNode`。 | **[保留 SDK 介面 / 僅清理無效配置與更新文檔]**<br/>保留代碼中受測試鎖定之介面，僅於 `sub_04` 更新 `docs/knowledge-db/` 移除過時的獨立 CLI 教學並標註 Deprecated。 |
| **REV-05** | `agents-workflow` 之 `DYNAMIC_CONTEXT_MAP`、`providers.py:get_dynamic_context_map`、`WORKFLOW_AUTO`、`MANIFEST_STORAGE_URI` | 1. `test_compiler.py:66, 172-187` 使用 `DYNAMIC_CONTEXT_MAP` 與 `providers:get_dynamic_context_map` 作為 `type: "computed"` 動態 Token 的基準測試。<br/>2. `test_auto_workflow.py:72` 斷言 `WORKFLOW_AUTO` 存在；`test_publisher.py:26` 直接引用 `MANIFEST_STORAGE_URI`。 | **[保留代碼與錨點]**<br/>全數保留以維持動態 Token 契約與測試基準。 |

---

### 2.2 經反向驗證確立之「精緻化修復約束」 (`[PARTIAL / NUANCED]`)

1. **`AUD-SRV-03` (`server` 背景服務 `ServiceManager` 架構真相)**：
   - **反向查證發現**：`master.py:120` 註解 `Master is pure control plane; domain services run in Worker pre-warm` 及 `CHANGELOG.md:162, 170` (`sub_08`/`sub_09`) 證實：**為了讓 `KnowledgeDBServiceWorker` 與 CLI 熱派發共享同一個 `WarmWorker` 內的 `KnowledgeEngine` 單例，並避免 Master 進程載入業務模組而無法熱重載，架構上已刻意將領域服務移至 `WarmWorker` 內啟動！**
   - **真正的缺陷**：目前 `knowledge-db/scripts/hook.server.py` 繞過 `ServiceManager` 手工啟動 `_watcher_instance`（Worker 結束時未執行 `stop_all()` 清理 `.watcher_active`），且未將服務狀態透過 IPC 回報給 `MasterSupervisor`，導致 `server status` 的 `Background Services` 永遠為 `None`。
   - **修正後修復方案**：**嚴禁在 Master 進程直接 import/啟動領域服務**！改由 `WarmWorker` 內建 `ServiceManager` 統一讀取 `contributes/server.json` 啟動服務，並在 `worker_ready` IPC 封包中將服務狀態同步給 `MasterSupervisor` 供 `/api/status` 展示；同時清理 `hook.server.py` 中重複的手工啟動邏輯。
2. **`AUD-KDB-04` (`act_callers` / `callees` / `impact` 首行呼叫 `self.search(limit=1)`)**：
   - **反向查證發現**：`test_graph.py:536` 在未建立索引的情況下直接呼叫 `engine.act_callers(...)`。原作者在首行寫 `self.search(query=target_query, limit=1)` 是為了**借用 `search()` 前半段的 JIT 懶索引建立與 `.watcher_dirty` 增量熱修補副作用**！若直接刪掉而不補齊 JIT 檢查，冷啟動呼叫 `act_callers` 或修改檔案後呼叫 `act_callers` 將無法觸發增量熱更新。
   - **修正後修復方案**：將 `search()` 前半段的 JIT 載入與增量自癒邏輯抽取為 `self._ensure_jit_index_ready(auto_rebuild=True, load_graph=True, load_vectors=False)`，供 `search` 與 `act_callers`/`callees`/`impact` 共用，既保留 100% JIT 自癒能力，又徹底消除無謂的 ONNX 向量推論與 BM25 檢索開銷。
3. **`AUD-KDB-01` (`patch_incremental` 的 `Path(p).name == sym_filename` 誤刪同名檔)**：
   - **反向查證發現**：`bundler.py:153` 將 `sym.file_path` 存為相對於 Space 根目錄的相對路徑（如 `"app.py"` 或 `"README.md"`），而 `scanner.check_invalidation()` 傳入的是完整絕對路徑；同時 `test_hot_reload.py:390` 手動傳入相對路徑 `dirty_file_paths={"src/beta.py"}`。
   - **修正後修復方案**：移除 `Path(p).name == sym_filename`；在 `bundler.py` 為 `UnifiedSymbol.metadata["canonical_path"]` 注入正規化完整路徑，於 `patch_incremental` 與 `hot_patch_unified_index` 優先比對 `canonical_path`，次級保留含目錄結構之相對路徑比對以相容 `test_hot_reload.py`。
4. **`AUD-CORE-01` (`ContributesAggregator` 跨模組 `commands` 同名覆蓋)**：
   - **反向查證發現**：`test_cli_router.py:107` 與 `test_contributes.py:87` 以舊式平鋪結構 mock/測試 `contributes.get("core", "commands")`。
   - **修正後修復方案**：保留 `contributes.get("core", "commands")` 頂層結構相容性，同時在聚合時於 `commands["__modules__"][donor_mod]` 保存各模組獨立指令定義；`core/providers.py` (`get_agents_cli_guild`) 優先遍歷 `__modules__`（並相容頂層平鋪 fallback），解決 `status`/`list`/`reload`/`release` 跨模組覆蓋污染。
5. **`AUD-CORE-05` (`_maybe_auto_spawn_server` 忽略 `config.local.json`)**：
   - **反向查證發現**：`test_core_commands.py:509-619` 直接傳入臨時目錄 `tmp_dir` 作為 `yscb_abs` 且未切換 `uri.yscb_scope`。
   - **修正後修復方案**：不可改調全域 `core.config.get()`，必須直接基於參數 `yscb_abs` 依序讀取 `config/server/config.project.json` 與 `config/server/config.local.json` 進行雙層合併。
6. **`AUD-DEV-05` (`Checker._check_cli_compliance` 對 `def process` 的豁免)**：
   - **反向查證發現**：`test_checker.py` 中 14 個測試案例使用的最小化 Mock 模組無 `contributes/core.json`，僅定義 `def process(args)`。
   - **修正後修復方案**：當模組存在 `contributes/core.json` 且宣告非空 `commands.cmd` 時，強制校驗所有葉節點具名函式（`-` 轉 `_`）且不允許單靠 `process` 豁免；若無 `commands.cmd` 則保留 `process(args)` 相容。
7. **`AUD-AW-04` (`Auto.md` 中的 `__${yscb.host://yscb.py}__`)**：
   - **反向查證發現**：`core` 實際已註冊 `yscb.host://` 協議（見 `uri list`），但 `compiler.py` 的 `_resolve_uri_to_physical` 在特定情境下對 `yscb.host://yscb.py` 報 warning，且 `test_auto_workflow.py:41` 明確斷言 `Auto.md` 源碼含 `"__${yscb.host://yscb.py}__"`。
   - **修正後修復方案**：在 `compiler.py:_resolve_uri_to_physical` 中完善對 `yscb.host://` 的正規解析（或統一轉譯為 `project://`），既消除編譯期 warning，又保持 `test_auto_workflow.py:41` 100% 通過。

---

## 3. 雙向驗證後之確鑿問題與修復對策總表 (Verified Findings & Remediation Matrix)

### 3.1 範疇 A：Host (`yscb.py`) 與 `core` 模組（對應 `sub_01`）

| 編號 | 驗證狀態 | 嚴重度 | 檔案位置與行號 | 驗證後之確鑿問題與精準修復對策 |
| :---: | :---: | :---: | :--- | :--- |
| **AUD-CORE-01** | `[PARTIAL / NUANCED]` | `CRITICAL` | `core/contributes.py:293-320`<br/>`core/providers.py:29-93`<br/>`core/engine.py:605, 993-1013` | **跨模組同名指令覆蓋污染 `yscb-cli-guild`**：<br/>於 `ContributesAggregator` 聚合 `core.commands` 時額外保留 `commands["__modules__"][donor]` 分桶（維持頂層平鋪相容 `test_cli_router.py`）；`core/providers.py` 遍歷各模組指令生成完整 CLI Guild（找回消失的 `core list`, `core status`, `knowledge-db status`, `core reload`, `agents-workflow release`）；修正 `engine.py` 讀取 `commands.get("cmd")`。 |
| **AUD-CORE-02** | `[CONFIRMED BUG]` | `HIGH` | `core/contributes/core.json:508-515`<br/>`core/scripts/cli.py:419-422` | **`contributes list --module=<mod>` 漏宣告 `args`**：<br/>於 `core.json` 補齊 `module` 選項之 `"args"` 定義，確保 `--module=core` / `-m core` 不再被轉為布林 `True`。 |
| **AUD-CORE-03** | `[CONFIRMED BUG]` | `HIGH` | `core/engine.py:249-252, 428, 648-755` | **`AtomicEngine` 108 行重複方法與 `mirror://` 快取穿透**：<br/>刪除 `engine.py` L249-252 與 L648-755 被遮蔽的重複方法；將 L428 的 `mirror://` 修正為 `module.mirror://`，恢復本地鏡像快取命中。 |
| **AUD-CORE-04** | `[PARTIAL / NUANCED]` | `HIGH` | `core/pip_manager.py:29-43, 215-259`<br/>`core/ide_projector.py:20-32` | **`PipManager` / `IdeProjector` 根路徑解析與 `.gitignore` 分叉**：<br/>`_resolve_yscb_root()` 優先委派 `core.uri._get_yscb_root()`；`PipManager._ensure_gitignore()` 委派 `installer.generate_internal_gitignore()`，避免抹除 `*.bak` 規則。 |
| **AUD-CORE-05** | `[PARTIAL / NUANCED]` | `HIGH` | `core/commands/dispatcher.py:191-207` | **`_maybe_auto_spawn_server` 忽略 `config.local.json`**：<br/>基於 `yscb_abs` 依序讀取 `config/server/config.project.json` 與 `config/server/config.local.json` 覆蓋合併（相容 `test_core_commands.py:509-619`）。 |
| **AUD-CORE-06** | `[CONFIRMED BUG]` | `HIGH` | `core/installer.py:287-302, 397-414, 495`<br/>`core/contributes/core.json:455-466` | **`Installer` 遠端清單、本地更新掃描與 `restore -p` 補齊**：<br/>實作 `cmd_list` 讀取 manifest 描述與 `--remote`/`--provider`；修正 `cmd_update` 本地 `.zip`/`index.json` 探測；補齊 `restore` 的 `provider` 選項宣告並修正預設 URL。 |
| **AUD-CORE-07b** | `[CONFIRMED BUG]` | `MEDIUM` | `yscb.py:77-98, 133, 152, 308, 349, 368` | **`yscb.py` 參數解析邊界與無效來源防呆**：<br/>支援 `init` / `self-update` 的 `--provider <val>`、`-p <val>`、`--url <val>` 空格與等號解析；為 `_fetch_and_extract_zip` 補上無效來源 `FileNotFoundError`（保留 L467-579 相容代理函式不動）。 |
| **AUD-CORE-08** | `[CONFIRMED BUG]` | `MEDIUM` | `core/uri.py:228-243, 379, 512, 584` | **`core.uri` 路徑邊界、`to_uri`、`config.reload` 與 `contributes.merged.json` 記憶體快取**：<br/>補齊 `target_base + os.sep` 檢查；`to_uri()` 納入已定義之 `config` 型別協議；`reconcile_undefined_uri()` 後呼叫 `config.reload()`；為 `_get_merged_uri_schemes` 加入基於 `(yscb_dir, mtime)` 的記憶體快取。 |
| **AUD-CORE-09** | `[PARTIAL / NUANCED]` | `MEDIUM` | `core/contributes/_format.json:5-7`<br/>`core/commands/registry.py:74, 84` | **`_format.json` 與 `CommandsRegistry` 對齊**：<br/>將 `_format.json:5` 的 `ArgDef.required` 改為 `"bool? = true"`（與 `registry.py` 及 `test_core_commands.py` 對齊）；`registry.py` 同時支援 `choice` 與 `choices`。 |
| **AUD-CORE-11** | `[CONFIRMED BUG]` | `LOW` | `core/__init__.py:29-100`<br/>`core/semver.py:26-30` | **PEP 562 匯出補齊與 `VersionTuple.__str__`**：<br/>將 `config`, `validator`, `providers`, `ide_projector` 納入 `core/__init__.py` 之 `_MODULE_MAP` 與 `__all__`；修正 `VersionTuple.__str__` 在含 `prerelease` 時保留非零 `revision`。 |

---

### 3.2 範疇 B：`dev` 模組與 `server` 模組（對應 `sub_02`）

| 編號 | 驗證狀態 | 嚴重度 | 檔案位置與行號 | 驗證後之確鑿問題與精準修復對策 |
| :---: | :---: | :---: | :--- | :--- |
| **AUD-DEV-01** | `[CONFIRMED BUG]` | `CRITICAL` | `dev/scripts/cli.py:83-85, 249-257` | **`get_option()` 誤用寫入 `CmdOption` 字串**：<br/>`create` (`--desc`) 與 `release-git` (`--msg`/`-m`) 改用 `bags.get_option_value()`。 |
| **AUD-DEV-02** | `[CONFIRMED BUG]` | `CRITICAL` | `dev/scripts/cli.py:293-297`<br/>`dev/dev/tester.py:161-166` | **`dev test -k <pattern>` 100% 失效**：<br/>於 `tester.py` 支援 `("-k=", "--k=", "--pattern=")`，確保 `-k` 過濾正常生效。 |
| **AUD-DEV-03** | `[CONFIRMED BUG]` | `CRITICAL` | `dev/dev/scaffold.py:29, 49-56, 74, 85-96` | **`dev create` 模組骨架三連敗**：<br/>更新 `scaffold.py`：`scripts/cli.py` 生成 `def hello(cmd_bags)`，`test_basic.py` 繼承 `YSCBTestCase` 並呼叫 `self.mark_passed()`，版本號改為 `"0.1.0.0"`（同時補齊 `case.py:create_mock_source_module` 的 `self.mark_passed()`）。 |
| **AUD-DEV-04** | `[CONFIRMED BUG]` | `HIGH` | `dev/contributes/core.json`<br/>`dev/dev/tester.py:176, 423`<br/>`dev/dev/releaser.py:56` | **`dev` CLI 選項宣告補齊、`--target` 修復與 `release-check --all`**：<br/>1. 於 `dev/contributes/core.json` 補齊 `test`（`-j`, `--target`, `--type`, `--sync`, `--keep-sandbox` 等）、`op-mksb`、`op-test`、`release-check`（`--all`）、`release-git`（`-m`/`--msg`）選項宣告。<br/>2. 修正 `tester.py`：無冒號 `--target=Class.method` 不覆蓋 `target_mod`；無位置參數 `--target=mod:Class.method` 自動提取 `target_mod` 避免全量 `build_all()`。<br/>3. 實作 `dev release-check --all` 批次預檢。 |
| **AUD-DEV-05** | `[PARTIAL / NUANCED]` | `MEDIUM` | `dev/dev/checker.py:571-595, 670-711`<br/>`dev/contributes/_manifest.md` | **`Checker` 具名指令校驗、Docstring 豁免與 `custom_checks` 接線**：<br/>1. 當 `contributes/core.json` 宣告非空 `commands.cmd` 時，強制校驗所有葉節點函式且不以 `process` 豁免（無 `commands.cmd` 時保留 `process` 相容 14 個單元測試）。<br/>2. `_check_source_files` 排除首行 Docstring AST 節點。<br/>3. 接線 `core.contributes.get("dev", "custom_checks")` 並補齊 `_manifest.md`。 |
| **AUD-SRV-01** | `[CONFIRMED BUG]` | `CRITICAL` | `server/server/master.py:72, 252-322, 586` | **`MasterSupervisor.dispatch_task` 無鎖並發讀寫 Worker stdio**：<br/>以 `self._dispatch_lock` 完整保護 Worker 存活檢查、stdin 寫入與 stdout 讀取迴圈，確保並發 HTTP 請求對單一 Worker IPC 嚴格序列化；清理未使用的 `_task_queue`。 |
| **AUD-SRV-02** | `[CONFIRMED BUG]` | `HIGH` | `server/server/master.py:357-366, 391-405` | **Worker `stderr=PIPE` 緩衝區死鎖風險與 Pipe FD 洩漏**：<br/>啟動背景 daemon 執行緒持續讀取 `proc.stderr` 寫入 `self.logger.error`，並於 `_kill_worker_locked` 安全關閉 `stdin`/`stdout`/`stderr` pipes。 |
| **AUD-SRV-03** | `[PARTIAL / NUANCED]` | `HIGH` | `server/server/worker.py:60-131`<br/>`server/server/master.py:120, 357`<br/>`knowledge-db/scripts/hook.server.py` | **Worker 端 `ServiceManager` 統一託管與巢狀子指令解析**：<br/>1. 遵守 `Master is pure control plane` 鐵律，在 `WarmWorker` 內透過 `ServiceManager` 動態載入 `contributes/server.json` 的 `services`（取代 `hook.server.py` 手工啟動的 `_watcher_instance`，並於 Worker 結束時 `stop_all()`），透過 IPC 將服務狀態同步至 `MasterSupervisor` 供 `/api/status` 展示。<br/>2. `WarmWorker` 改用 `registry.resolve_command_path()` 解析多層子指令（如 `plan status`）。 |
| **AUD-SRV-04** | `[CONFIRMED BUG]` | `MEDIUM` | `server/server/logger.py:27`<br/>`server/server/master.py:216-250`<br/>`server/tests/test_server*.py` | **`HIST_REGEX` 碰撞後綴、`restart_server` 與測試 `super()`**：<br/>更新 `HIST_REGEX` 支援 `(?:_\d{2,})?_log$`；移除 `restart_server` 對 `source/` 的違規 fallback；於 `test_server.py` 與 `test_server_logging.py` 補齊 `super().setUp()` / `super().tearDown()`；補上 `server start --ttl` 數值轉換防呆。 |

---

### 3.3 範疇 C：`knowledge-db` 模組與 `agents-workflow` 模組（對應 `sub_03`）

| 編號 | 驗證狀態 | 嚴重度 | 檔案位置與行號 | 驗證後之確鑿問題與精準修復對策 |
| :---: | :---: | :---: | :--- | :--- |
| **AUD-KDB-01** | `[PARTIAL / NUANCED]` | `CRITICAL` | `knowledge_db/bundler.py:163`<br/>`knowledge_db/retrieval.py:497-508`<br/>`knowledge_db/pipeline.py:451-462` | **增量熱修補 `Path(p).name` 連坐誤刪全庫同名檔**：<br/>於 `bundler.py` 為每個符號寫入 `metadata["canonical_path"]`；在 `patch_incremental` 與 `hot_patch_unified_index` 徹底移除 `Path(p).name == sym_filename`，優先比對 `canonical_path`，次級保留相對路徑後綴比對以相容 `test_hot_reload.py:390`。 |
| **AUD-KDB-02** | `[CONFIRMED BUG]` | `HIGH` | `knowledge_db/pipeline.py:768-785, 836-856`<br/>`knowledge_db/hybrid.py:80-166` | **`HybridSearchEngine` 未前置過濾 `spaces`/`kinds`/`languages`**：<br/>將 `QueryFilter(spaces, kinds, languages, ftypes)` 傳入 `HybridSearchEngine.search()`，在 BM25 與向量候選階段即執行 `filter_obj.matches()` 前置過濾，再進行 RRF 排名與 Top-K 截斷。 |
| **AUD-KDB-03** | `[CONFIRMED BUG]` | `HIGH` | `knowledge_db/embedding.py:394-396, 413-416`<br/>`knowledge_db/pipeline.py:528, 604-640` | **非 `mock_mode` 異常時回傳假向量污染快取，且 `clean()` 漏刪 `unified.vectors.bin.gz`**：<br/>1. `embed_texts` 僅在 `self.mock_mode is True` 時回傳 mock 向量，不可用或異常時回傳 `[]`。<br/>2. `clean()` 補刪 `unified.vectors.bin.gz` 並清空 `_GLOBAL_INDEX_CACHE` 與 `vector_index`；熱修補後同步更新 `_GLOBAL_INDEX_CACHE["vector_index"]`。 |
| **AUD-KDB-04** | `[PARTIAL / NUANCED]` | `HIGH` | `knowledge_db/pipeline.py:667-736, 978, 1030, 1082`<br/>`knowledge_db/retrieval.py:238, 725` | **抽取 `_ensure_jit_index_ready` 消除 `act_callers`/`callees`/`impact` 無謂向量推論**：<br/>將 `search()` 前半段 JIT 載入與增量熱修補邏輯抽取為 `_ensure_jit_index_ready(auto_rebuild=True, load_graph=True, load_vectors=False)` 供 `act_callers`/`callees`/`impact` 呼叫（保留 `test_graph.py:536` 冷啟動自癒，消除冗餘推論）；優化 `SnippetExtractor._resolve_path` 支援空間根目錄與單次請求檔案快取。 |
| **AUD-KDB-05** | `[CONFIRMED BUG]` | `MEDIUM` | `knowledge_db/service.py:190-226`<br/>`knowledge_db/formatter.py:911-916`<br/>`knowledge-db/contributes/core.json`<br/>`knowledge-db/contributes/agents-workflow.json` | **`.watcher_dirty` 競態、`callees -d` 重複印切片與 CLI 契約同步**：<br/>1. 將 `dirty_flag.unlink()` 移至熱修補完成後的 `finally` 區塊。<br/>2. 刪除 `formatter.py:914` 重複的 `node_lines.append(formatted_snip)`。<br/>3. 於 `contributes/core.json` 補齊 `search` (`kind`/`lang`) 與 `callers`/`callees`/`impact` (`limit`) 選項宣告；同步清理 `contributes/agents-workflow.json` 中已廢除之 `scan`/`bundle` 殘留。 |
| **AUD-AW-01** | `[CRITICAL]` | `CRITICAL` | `agents_workflow/publisher.py:151-207` | **Stage 0 指紋對所有 Skill 目錄算出空字串 SHA-1 致修改永不重編譯**：<br/>於 `_get_sources_digest()` 中若 `src` 為目錄 (`os.path.isdir`)，遞迴走訪目錄內所有檔案計算 SHA-1；同時將動態 Token 依賴之 `contributes` 資料摘要納入指紋。 |
| **AUD-AW-02** | `[CONFIRMED BUG]` | `HIGH` | `agents_workflow/compiler.py:456-483, 613-680`<br/>`agents_workflow/publisher.py:601-603`<br/>`agents-workflow/scripts/cli.py:251` | **Stage 2 URI 佔位符三大編譯缺陷與 `export.description` 未解算**：<br/>1. 修正 `compiler.py`：剝除 Markdown 連結目標 `](`...`)` 外層反引號；保留原始 URI 尾隨 `/`；僅對 `.md` 執行佔位符正則替換（跳過 `.py` 腳本）。<br/>2. 於 `publisher.py` 與 `cli.py:list` 對 `description`/`header` 執行 Stage 2 解算。 |
| **AUD-AW-03** | `[CONFIRMED BUG]` | `HIGH` | `agents_workflow/plans/verifier.py`<br/>`agents_workflow/plans/archiver.py` | **`PlanVerifier` 5 處實作與規範脫節**：<br/>修正模板動態編譯呼叫、`P00_discuss.md` 映射、納入 `計畫狀態` 與完整合法狀態集（`Discussing`, `Planning`, `Executing`, `Concluded` 等）、遞迴檢查子計畫巢狀深度（`> 2` 層報錯）、統一 fallback 封存路徑為 `plans/archived`。 |
| **AUD-AW-04** | `[PARTIAL / NUANCED]` | `HIGH` | `assets/skills/session-analysis/scripts/analyzer.py:31-35`<br/>`agents_workflow/compiler.py:530-575`<br/>`agents-workflow/contributes/core.json` | **`session-analysis` 路徑、URI warning 與 CLI 選項補齊**：<br/>1. `analyzer.py` 補入 `~/.gemini/antigravity/brain`。<br/>2. `compiler.py` 完善 `yscb.host://` 實體路徑解析以消除編譯期 warning（同時保持 `test_auto_workflow.py:41` 通過）。<br/>3. 修正 `agents-workflow list` 在 `core.json` 的錯誤描述，並補齊 `init` 與 `release-target` 漏宣告之選項。 |

---

### 3.4 範疇 D：全專案知識庫 (`docs/`)、模組 `README.md` 與 `plans/roadmap/`（對應 `sub_04`）

1. **`docs/_project/STANDARDS.md`、`docs/core/*.md`、`source/core/README.md`**：
   - 全面將舊版 `*.root://`、`temp://`、`mirror://` 協議表與範例更新為現行方案 B（`uri list` 18 項正式協議與 `@/` 自省語法）。
   - 修正 `STANDARDS.md` 中不存在的 `yscb.config.local.json` 與 `snapshot://` 敘述；修正 `source/core/README.md` 中 9 處舊版 `yscb_core.py`；修正 `docs/core/DESIGN_NOTES.md` (`DN-02/07/08/09/21/22`)、`SEMVER.md`、`SNAPSHOT_AND_ROLLBACK.md`、`MIGRATION_LADDER.md`、`ZIP_PACKAGE_SPEC.md`、`symbol_resolution.md`（移除 `./API_REFERENCE.md` 斷鏈）與 `platform.md`。
2. **`docs/dev/*.md`、`source/dev/README.md`、`yscb-module-dev` 技能手冊**：
   - 修正 `yscb-module-dev/references/cli_and_commands.md` 中錯誤的 `cmd_bags.args.get()`、`get_option()` 與 `raw_args` 範例。
   - 整併淘汰過時的孤兒文檔 `docs/dev/RELEASE_PIPELINE.md`；更新 `docs/dev/DESIGN_NOTES.md` (`DN-DEV-01/02/05`)；為 `docs/dev/` 補齊 YAML Frontmatter、將 ASCII 圖升級為 Mermaid 圖並補上 `[!CAUTION]`。
3. **`docs/server/*.md`、`source/server/README.md`**：
   - 新增 `ys_codebase/source/server/README.md`。
   - 更新 `docs/server/DESIGN_NOTES.md`、`daemon_architecture.md`、`hot_reload_architecture_migration.md`（對齊 Worker 端 `ServiceManager` 架構），並補齊 YAML Frontmatter、Mermaid 圖與 `[!CAUTION]`。
4. **`docs/knowledge-db/*.md`、`source/knowledge-db/README.md`**：
   - 修正 `README.md` 的 Python SDK 範例（`act_callers`, `act_callees`, `act_impact`, `ftype="py"`, `snippet=True`）。
   - 更新 `architecture.md`, `retrieval.md`, `tokenizer.md`, `bundler.md`, `contributes_guide.md`, `DESIGN_NOTES.md`，移除已刪除之 `bundle`/`scan` CLI 教學與 `384` 維度誤植（實為 `512` 維），補齊 `languages` 擴充說明並清理標題 Emoji。
5. **`docs/agents-workflow/*.md`、`documentation/SKILL.md`、`plans/roadmap/*.md`**：
   - 修復 `documentation/SKILL.md` 與 `docs/agents-workflow/README.md`、`user_guide.md` 的斷鏈與舊參數說明。
   - 將 `plans/roadmap/` 下已落地的 3 個項目狀態更新為 `Implemented`，清理斷鏈與 Emoji；於 `RoadmapManager` (`roadmap.py`) 支援解析 `> 狀態：` 並預設過濾 `Implemented`/`Completed` 項目。

---

## 4. 延伸子計畫 (`sub_05` 與 `sub_06`) 驗證與落地藍圖

1. **`sub_05_agents_workflow_skill_unification`（延伸 2.a：廢除 `workflow` 分類，全面遷移為 `skill`）**：
   - 在 `sub_03` 先行修復 `publisher.py` Stage 0 Skill 目錄指紋盲區後，於 `sub_05` 將 8 個模組級 Workflows（`ContextInit`, `NewPlan`, `Continue`, `Pause`, `Discuss`, `Research`, `Auto`, `Roadmap`）與專案級 `BumpRevision` 全面重構為標準 `skill`（`SKILL.md` 架構）。
   - 更新 `contributes/_format.json`、`agents-workflow.json`、`compiler.py`、`publisher.py`（自動清理舊 `.agents/workflows/`），並同步更新 `test_auto_workflow.py`、`test_compiler.py`、`test_publisher.py` 等單元測試。
2. **`sub_06_downstream_cli_ux_and_server_feedback`（延伸 2.b：下游 UX/DX 優化與指令反饋強化）**：
   - **`server` 啟停完整回饋**：`server start`（含背景與 `--console`）輸出結構化啟動橫幅（`Mode`, `Master PID`, `Worker PID`, `Endpoint`, `Workspace Root`, `Idle TTL`, `Modules Watcher`, `Background Services`, `Active Log`）；前台 `--console` 模式支援即時日誌回顯 (`console_echo=True`)；`server stop` 與前台 `Ctrl+C`/TTL 停機時輸出「本次運行總結報告」（`Uptime`, `Total Tasks Handled`, `Shutdown Reason`, `Archived Log Path`）。
   - **全生態系 CLI DX 強化**：`HelpRenderer` 全域 Help 補齊 `self-update` 並修正 `init [root]`；`uri` 與 `config` 接入統一 `HelpRenderer` 與未知子指令 `Did you mean` 建議；`dev test` Quick Re-run 提示帶上 `<module>` 參數。
