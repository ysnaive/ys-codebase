# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：全生態系模組五大語意空間映射對齊與既有資產無損遷移 (Ecosystem Modules Five Semantic Spaces Alignment)  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Medium)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `gdrive-support` 五大語意空間與敏感路徑對齊 | 1. `manifest.json` 之 `uris.storage` 與 `contributes/core.json` 之 `gdrive-support.storage` 對齊為 `storage.local://gdrive-support/`。<br>2. `configurable/_format.json`、`configurable/config.project.json`、母倉 `ys_codebase/config/gdrive-support/config.project.json` 與 `gdrive_support/config.py` (`GDriveConfig` 及 `load_gdrive_config`) 之 `credentials_uri` 與 `token_uri` 預設值統一為 `config.local://gdrive-support/{credentials,token}.json`。<br>3. `is_sensitive_credential_path` 納入 `ys_codebase/.config.local/` 與 `ys_codebase/.storage.local/`。<br>4. `gdrive_support/coordinator.py` 之 `sync_state.json` 與 `readme_sync_state.json` 預設路徑對齊為 `storage.local://gdrive-support/{sync_state,readme_sync_state}.json`；`sync.lock` 與 `sync.log` 留駐於 `cache://gdrive-support/`。 | P0 | [P00:DR-01] |
| **FR-02** | `file-space`、`ast`、`knowledge-db` 儲存空間與鎖檔分離對齊 | 1. `file-space`：`manifest.json` (`uris.storage`)、`contributes/core.json` (`file-space.storage`)、`file_space/manager.py` (`storage_root`) 與 `scripts/hook.dev.py` 對齊為 `storage.local://file-space/` (`.storage.local/file-space`)；`file-space.cache` 維持 `cache://file-space/`。<br>2. `ast`：`manifest.json` (`uris.storage`)、`contributes/core.json` (`ast.storage`)、`ast_engine/bundler.py` (`_resolve_default_ast_storage_dir`) 與 `scripts/hook.dev.py` 對齊為 `storage.local://ast/` (`.storage.local/ast`)；`ast_engine/engine.py` 之 `.ast_index.lock` 於預設儲存模式下分離至 `cache://ast/.ast_index.lock`，於顯式自訂 `storage_dir`/`project_root` 沙盒模式下派生於該測試沙盒內。<br>3. `knowledge-db`：`manifest.json` 補齊 `uris.storage` 為 `storage.local://knowledge-db`；`contributes/core.json` 將 `knowledge.storage` 對齊為 `storage.local://knowledge-db/` 並新增 `knowledge.cache` (`cache://knowledge-db/`)；`knowledge_db/pipeline.py` (`_resolve_default_knowledge_storage_dir`)、`knowledge_db/embedding.py` (`models/` 預設路徑)、`scripts/hook.dev.py` 對齊為 `storage.local://knowledge-db/`；`knowledge_db/config.py` 對齊 `config://knowledge-db/config.project.json` 與 `config.local://knowledge-db/config.local.json`；`pipeline.py` 之 `.kdb_index.lock` 於預設模式下分離至 `cache://knowledge-db/.kdb_index.lock`，於自訂 `storage_dir` 沙盒模式下派生於該沙盒內。 | P0 | [P00:DR-01] |
| **FR-03** | `agents-workflow`、`core`、`dev` 持久帳本與沙盒對齊 | 1. `agents-workflow`：`publisher.py` 之 `PROJECT_MANIFEST_CACHE_URI`、`LOCAL_MANIFEST_CACHE_URI`、`SHA1_CACHE_URI` 對齊為 `storage.local://agents-workflow/{project_release_manifest,release_manifest,source_sha1_cache}.json`，拔除業務代碼內 `_migrate_legacy_manifest` 歷史分支；`publisher.py` 提示與 `plans/session_trace.py` 降級讀檔納入 `config.local://agents-workflow/config.local.json`；`compiler.py` 與 `contributes/core.json` 清除 `cache.root://` 舊詞對齊為 `cache://`。<br>2. `core`：`core/gitignore.py` 之 `DYNAMIC_CACHE_URI` 對齊為 `storage.local://core/gitignore_dynamic.json`；更新 `core/engine.py`、`core/contributes/core.json`、`core/contributes/_manifest.md` 說明。<br>3. `dev`：`dev/testing/sandbox.py` 之 `create_sandbox` 預建 `engine/.config.local`、`engine/storage`、`engine/.storage.local`。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-04** | 版本晉升 Hook (`scripts/migrations/`) 自癒升級與母倉組態防護 | 1. 業務代碼維持 0 舊路徑執行期 Fallback。<br>2. 於 `core` (`1.2.7.x.py`)、`gdrive-support` (`1.0.1.x.py`)、`file-space` (`1.0.1.x.py`)、`ast` (`1.0.1.x.py`)、`knowledge-db` (`1.2.1.x.py`)、`agents-workflow` (`1.2.4.x.py`) 之 `scripts/migrations/` 實作版本晉升冪等搬移：將舊路徑下之 `config.local.json`、`credentials.json`、`token.json`、`sync_state.json`、`readme_sync_state.json`、`snapshots/`、`cursors/`、`indices/`、`bundles/`、`models/`、發布清冊與 `gitignore_dynamic.json` 原子搬移至新空間並清理舊檔，同時將 `config/gdrive-support/config.project.json` 內舊預設 URI 自動升級為 `config.local://`。<br>3. 母倉 `ys_codebase/config/file-space/contribute.json` 之 `cloud.exclude` 補入 `"ys_codebase/.config.local"` 與 `"ys_codebase/.storage.local"`；母倉實體 `ys_codebase/config/core/config.local.json` 與 `ys_codebase/config/gdrive-support/credentials.json` 遷移至 `.config.local/`。<br>4. 協同推進受影響模組之 `manifest.json` 版本號（`core` `1.2.7.0`、`gdrive-support` `1.0.1.0`、`file-space` `1.0.1.0`、`ast` `1.0.1.0`、`knowledge-db` `1.2.1.0`、`agents-workflow` `1.2.4.0`、`server` `1.0.4.6`、`dev` `1.0.3.2`、`vscode-support` `1.0.0.4`）。 | P0 | [P00:DR-02] |
| **FR-05** | 隨包指南、Skills、系統文檔同步與工作流重發布 | 同步更新各模組 `assets/{config_guide,usage_guide}.md`、`README.md`、`yscb-module-dev/SKILL.md`、`how-to-config-yscb/SKILL.md`、`ys_codebase/config/agents-workflow/snippets/project_role.md` 及 `docs/{_project,core,agents-workflow,knowledge-db,gdrive-support}/`，並執行 `agents-workflow release` 更新根目錄 `AGENTS.md` 與 `.agents/skills/`。 | P1 | [P00:DR-01] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 單元測試顯式傳入自訂 `storage_dir` 或自訂 `project_root` 時之鎖檔隔離 | `ASTEngine` (`.ast_index.lock`) 與 `IndexingPipeline` (`.kdb_index.lock`) 偵測到呼叫端顯式傳入自訂 `storage_dir` 時，鎖檔派生於該自訂沙盒目錄下，絕不跨沙盒爭搶宿主全域 `cache://` 鎖檔。 |
| **EC-02** | 版本晉升 Migration Hook 執行時新路徑已存在目標檔案或舊路徑不存在 | 各模組 `scripts/migrations/*.py` 嚴格具備冪等性：若舊路徑不存在則靜默跳過；若新路徑已存在目標檔案，保留新路徑檔案並安全移除舊路徑殘留檔，返回 `True`。 |
| **EC-03** | `cloud` 同步空間 (`include: ["project://"]`) 掃描母倉時遭遇 `.config.local` 與 `.storage.local` | `ys_codebase/config/file-space/contribute.json` 之 `cloud.exclude` 明確排除 `ys_codebase/.config.local` 與 `ys_codebase/.storage.local`，且 `is_sensitive_credential_path` 雙重攔截敏感路徑，杜絕憑證外洩與同步狀態帳本無限自我觸發。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構純淨度 | 業務生產代碼 0 舊路徑執行期 Fallback、0 工單註解殘留、0 跨模組非法 `sys.path` 注入，全數通過 `python yscb.py dev check`。 |
| **NFR-02** | 容器持久性與 `tmpfs` 相容 | 清空 `ys_codebase/.cache/` 後，OAuth 憑證 (`config.local://`)、同步帳本、向量模型、索引圖譜、發布清冊與動態 `.gitignore` 帳本 (`storage.local://`) 100% 完好留存。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 遵守 `[DN-19]` 業務代碼零遷移包袱原則**：所有舊路徑檔案與組態遷移一律收斂於 `scripts/migrations/*.py`，禁止在運行期讀取函式塞入雙路徑探測。
- **`[!IMPORTANT]` 鎖檔沙盒隔離**：`InterProcessLock` 在預設工作區模式下寫入 `cache://<mod>/.*.lock`，但在單元測試傳入 `storage_dir=tmp_dir` 時必須綁定於該 `tmp_dir` 內部，防止平行測試鎖衝突或污染宿主環境。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[yscb:// (ys_codebase/)]
 ├── config/ (config://)               [Git Tracked]  團隊共享組態 (config.project.json, contribute.json)
 ├── .config.local/ (config.local://)  [Git Ignored]  本機私有組態 (config.local.json) + 敏感憑證 (credentials.json, token.json)
 ├── storage/ (storage://)             [Git Tracked]  團隊共享模組持久資產
 ├── .storage.local/ (storage.local://)[Git Ignored]  本機持久資產與帳本 (Disk Persistent, Excluded from Snapshots):
 │    ├── core/gitignore_dynamic.json
 │    ├── gdrive-support/{sync_state.json, readme_sync_state.json}
 │    ├── file-space/{snapshots/*.yfp2.bin, cursors/*.json}
 │    ├── ast/{indices/unified.{symbols,graph}.bin.gz, bundles/}
 │    ├── knowledge-db/{models/, indices/unified.{index,vectors}.bin.gz}
 │    └── agents-workflow/{project_release_manifest.json, release_manifest.json, source_sha1_cache.json}
 └── .cache/ (cache://)                [Git Ignored]  純揮發性快取與跨進程鎖 (tmpfs Ready):
      ├── .yscb.lock
      ├── core/{update_check.json, telemetry.jsonl}
      ├── server/{daemon.json, daemon.lock, spawn_probe.json, log}
      ├── gdrive-support/{sync.lock, sync.log}
      ├── ast/.ast_index.lock
      ├── knowledge-db/.kdb_index.lock
      └── agents-workflow/resolved_contents/
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/manifest.json` | Modify | 版本推進至 `1.2.7.0` |
| `ys_codebase/source/core/core/gitignore.py` | Modify | `DYNAMIC_CACHE_URI` 改為 `storage.local://core/gitignore_dynamic.json` |
| `ys_codebase/source/core/core/engine.py` | Modify | 同步更新快照、組態部署與 `act_delete` Docstring 涵蓋 `config.local://` 與 `storage.local://` |
| `ys_codebase/source/core/contributes/core.json` | Modify | 更新 `remove --purge` 描述涵蓋五大空間 |
| `ys_codebase/source/core/contributes/_manifest.md` | Modify | 補列 `config.local://`、`storage.local://` 與 `gitignore` 指令 |
| `ys_codebase/source/core/assets/config_guide.md` | Modify | 對齊 `config.local://core/config.local.json` 與五大空間 URI |
| `ys_codebase/source/core/assets/usage_guide.md` | Modify | 補齊五大空間 URI 說明 |
| `ys_codebase/source/core/scripts/migrations/1.2.7.x.py` | Modify | 擴充遷移 `.cache/core/gitignore_dynamic.json` 至 `.storage.local/core/gitignore_dynamic.json` |
| `ys_codebase/source/core/tests/test_gitignore.py` | Modify | 新增預設工作區 `storage.local://core/gitignore_dynamic.json` 持久化測試 |
| `ys_codebase/source/core/tests/test_migration_ladder.py` | Modify | 新增 `1.2.7.x.py` 對 `config*.local.json` 與 `gitignore_dynamic.json` 遷移測試 |
| `ys_codebase/source/core/tests/test_installer.py` | Modify | 擴充 `test_remove_lifecycle_cache_cleaning_and_purge` 驗證 `config.local://` 與 `storage.local://` |
| `ys_codebase/source/dev/manifest.json` | Modify | 版本推進至 `1.0.3.2` |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | 沙盒 `create_sandbox` 預建 `engine/.config.local`、`engine/storage`、`engine/.storage.local` |
| `ys_codebase/source/dev/assets/config_guide.md` | Modify | 對齊 `config.local://dev/config.local.json` |
| `ys_codebase/source/dev/assets/skills/yscb-module-dev/SKILL.md` | Modify | 補列 `config.local://` 與 `storage.local://` |
| `ys_codebase/source/server/manifest.json` | Modify | 版本推進至 `1.0.4.6` |
| `ys_codebase/source/server/assets/config_guide.md` | Modify | 對齊 `config.local://server/config.local.json` |
| `ys_codebase/source/vscode-support/manifest.json` | Modify | 版本推進至 `1.0.0.4` |
| `ys_codebase/source/vscode-support/assets/usage_guide.md` | Modify | 補列 `.config.local/<mod>/config.*.json` 與 `core.gitignore` 納管說明 |
| `ys_codebase/source/vscode-support/README.md` | Modify | 對齊 `core.gitignore` 納管說明 |
| `ys_codebase/source/gdrive-support/manifest.json` | Modify | 版本推進至 `1.0.1.0`，`uris.storage` 改為 `storage.local://gdrive-support` |
| `ys_codebase/source/gdrive-support/contributes/core.json` | Modify | `gdrive-support.storage` 改為 `storage.local://gdrive-support/` |
| `ys_codebase/source/gdrive-support/configurable/_format.json` | Modify | `credentials_uri` 與 `token_uri` 預設改為 `config.local://gdrive-support/{credentials,token}.json` |
| `ys_codebase/source/gdrive-support/configurable/config.project.json` | Modify | `credentials_uri` 與 `token_uri` 預設改為 `config.local://gdrive-support/{credentials,token}.json` |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | `GDriveConfig` 與 `load_gdrive_config` 預設對齊 `config.local://`；`is_sensitive_credential_path` 納入 `.config.local` 與 `.storage.local` |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | `sync_state.json` 與 `readme_sync_state.json` 對齊 `storage.local://gdrive-support/`；`sync.lock` 與 `sync.log` 維持 `cache://` |
| `ys_codebase/source/gdrive-support/scripts/cli.py` | Modify | 更新 Docstring 為 `storage.local://gdrive-support/readme_sync_state.json` |
| `ys_codebase/source/gdrive-support/scripts/migrations/1.0.1.x.py` | New | 版本晉升 Hook：遷移舊 `credentials.json`、`token.json`、`sync_state.json`、`readme_sync_state.json` 並升級 `config.project.json` 舊預設 URI |
| `ys_codebase/source/gdrive-support/README.md` | Modify | 對齊 `config.local://` 與 `storage.local://` |
| `ys_codebase/source/gdrive-support/assets/config_guide.md` | Modify | 對齊 `config.local://gdrive-support/config.local.json` |
| `ys_codebase/source/gdrive-support/tests/test_atomic_api_and_config.py` | Modify | 驗證新預設 URI、敏感路徑防護與 `1.0.1.x.py` 遷移腳本 |
| `ys_codebase/source/file-space/manifest.json` | Modify | 版本推進至 `1.0.1.0`，`uris.storage` 改為 `storage.local://file-space` |
| `ys_codebase/source/file-space/contributes/core.json` | Modify | `file-space.storage` 改為 `storage.local://file-space/` |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | `storage_root` fallback 對齊 `storage.local://file-space/` 與 `.storage.local/file-space` |
| `ys_codebase/source/file-space/scripts/hook.dev.py` | Modify | 沙盒初始化建立 `.storage.local/file-space` 與 `.cache/file-space` |
| `ys_codebase/source/file-space/scripts/migrations/1.0.1.x.py` | New | 版本晉升 Hook：遷移 `.cache/file-space/{snapshots,cursors}` 至 `.storage.local/file-space/` |
| `ys_codebase/source/ast/manifest.json` | Modify | 版本推進至 `1.0.1.0`，`uris.storage` 改為 `storage.local://ast` |
| `ys_codebase/source/ast/contributes/core.json` | Modify | `ast.storage` 改為 `storage.local://ast/` |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | `_resolve_default_ast_storage_dir` 對齊 `storage.local://ast` 與 `.storage.local/ast` |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | `.ast_index.lock` 於預設模式下分離至 `cache://ast/.ast_index.lock`（自訂沙盒時留於沙盒內） |
| `ys_codebase/source/ast/scripts/hook.dev.py` | Modify | 沙盒初始化建立 `.storage.local/ast` 與 `.cache/ast` |
| `ys_codebase/source/ast/scripts/migrations/1.0.1.x.py` | New | 版本晉升 Hook：遷移 `.cache/ast/{indices,bundles}` 至 `.storage.local/ast/` |
| `ys_codebase/source/knowledge-db/manifest.json` | Modify | 版本推進至 `1.2.1.0`，新增 `uris.storage` 為 `storage.local://knowledge-db` |
| `ys_codebase/source/knowledge-db/contributes/core.json` | Modify | `knowledge.storage` 改為 `storage.local://knowledge-db/`，新增 `knowledge.cache` (`cache://knowledge-db/`) |
| `ys_codebase/source/knowledge-db/contributes/_manifest.md` | Modify | 對齊 `storage.local://knowledge-db/` 與 `.storage.local/knowledge-db/` |
| `ys_codebase/source/knowledge-db/knowledge_db/config.py` | Modify | 對齊 `config://knowledge-db/config.project.json` 與 `config.local://knowledge-db/config.local.json` |
| `ys_codebase/source/knowledge-db/knowledge_db/embedding.py` | Modify | 預設 `cache_dir` 對齊 `_resolve_default_knowledge_storage_dir() / "models"` |
| `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Modify | `_resolve_default_knowledge_storage_dir` 對齊 `storage.local://knowledge-db/`；`.kdb_index.lock` 於預設模式下分離至 `cache://knowledge-db/.kdb_index.lock` |
| `ys_codebase/source/knowledge-db/knowledge_db/service.py` | Modify | 更新 Docstring 為 `.storage.local/` |
| `ys_codebase/source/knowledge-db/scripts/hook.dev.py` | Modify | 沙盒初始化建立 `.storage.local/knowledge-db` 與 `.cache/knowledge-db` |
| `ys_codebase/source/knowledge-db/scripts/migrations/1.2.1.x.py` | New | 版本晉升 Hook：遷移 `.cache/knowledge-db/{models,indices,bundles}` 至 `.storage.local/knowledge-db/` |
| `ys_codebase/source/knowledge-db/tests/test_cli.py` | Modify | `test_hook_lifecycle` 斷言對齊 `.storage.local/knowledge-db/indices` |
| `ys_codebase/source/knowledge-db/README.md` | Modify | 對齊 `config.local://knowledge-db/config.local.json` |
| `ys_codebase/source/knowledge-db/assets/config_guide.md` | Modify | 對齊 `config.local://knowledge-db/config.local.json` |
| `ys_codebase/source/agents-workflow/manifest.json` | Modify | 版本推進至 `1.2.4.0` |
| `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Modify | 三大清冊常數改為 `storage.local://agents-workflow/...`，拔除 `_migrate_legacy_manifest`，更新提示訊息為 `config.local://` |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | Docstring `cache.root://` 對齊為 `cache://` |
| `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` | Modify | 降級讀檔納入 `config.local://agents-workflow/config.local.json` |
| `ys_codebase/source/agents-workflow/contributes/core.json` | Modify | `compile` 描述 `cache.root://` 對齊為 `cache://` |
| `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md` | Modify | 對齊 `config.local://<mod>/config.local.json` 與忽略規則檢查 |
| `ys_codebase/source/agents-workflow/scripts/migrations/1.2.4.x.py` | New | 版本晉升 Hook：遷移舊 `storage://` 或 `cache://agents-workflow/{project_release_manifest,release_manifest,source_sha1_cache}.json` 至 `storage.local://` |
| `ys_codebase/source/agents-workflow/tests/test_publisher.py` | Modify | 對齊 `storage.local://` 斷言與 `1.2.4.x.py` 遷移測試 |
| `ys_codebase/source/agents-workflow/tests/test_compiler.py` | Modify | Docstring 對齊 `cache://` |
| `ys_codebase/config/file-space/contribute.json` | Modify | `cloud.exclude` 補入 `"ys_codebase/.config.local"` 與 `"ys_codebase/.storage.local"` |
| `ys_codebase/config/gdrive-support/config.project.json` | Modify | `credentials_uri` 與 `token_uri` 對齊為 `config.local://gdrive-support/{credentials,token}.json` |
| `ys_codebase/config/agents-workflow/snippets/project_role.md` | Modify | 黑盒清單補入 `ys_codebase/.config.local/` 與 `ys_codebase/.storage.local/` |
| `docs/_project/STANDARDS.md` | Modify | 對齊五大語意空間描述與 `knowledge.storage://` 映射 |
| `docs/core/{API_REFERENCE.md,README.md,DESIGN_NOTES.md,SNAPSHOT_AND_ROLLBACK.md,ZIP_PACKAGE_SPEC.md}` | Modify | 同步 `gitignore_dynamic.json`、快照範圍與組態部署說明 |
| `docs/agents-workflow/{README.md,FACTORY_PIPELINE.md,DESIGN_NOTES.md,user_guide.md}` | Modify | 同步 `storage.local://` 發布清冊與 `config.local://` 覆寫說明 |
| `docs/knowledge-db/{README.md,architecture.md,DESIGN_NOTES.md,call_graph_and_reference_index.md,incremental_hot_reload.md,retrieval.md}` | Modify | 同步 `storage.local://` 與 `config.local://` 說明 |
| `docs/gdrive-support/README.md` | Modify | 同步 `storage.local://gdrive-support/readme_sync_state.json` 說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 預設跨進程鎖分離至 `cache://` 與測試沙盒隔離雙模解析**：`ASTEngine` 與 `IndexingPipeline` 記錄構造時是否由呼叫端顯式傳入自訂 `storage_dir`（`self._custom_storage_dir: bool`）。當 `not self._custom_storage_dir` 時，鎖檔解析至 `cache://{ast,knowledge-db}/.{ast,kdb}_index.lock`；當測試顯式注入 `storage_dir` 時，鎖檔建立於 `self.indices_dir / ".{ast,kdb}_index.lock"`，兼顧生產環境 `tmpfs` 純淨度與平行單元測試沙盒封閉性。
- **[P02:DR-02] 業務邏輯零遷移包袱與 `scripts/migrations/*.py` 單一收斂**：拔除所有執行期舊路徑探測（含 `agents_workflow/publisher.py` 既有 `_migrate_legacy_manifest`），將舊路徑檔案搬移統一交由各模組 `scripts/migrations/<ver>.x.py` 於版本晉升時執行。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/*/scripts/migrations/<ver>.x.py
def migrate(context: dict[str, str]) -> bool: ...

# ys_codebase/source/ast/ast_engine/engine.py
class ASTEngine:
    def _resolve_index_lock_path(self) -> Path: ...

# ys_codebase/source/knowledge-db/knowledge_db/pipeline.py
class IndexingPipeline:
    def _resolve_index_lock_path(self) -> Path: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `migrate(context: dict[str, str]) -> bool`：接收 `act_migrate` 傳入之 `context`（含 `host_dir`, `yscb_dir`, `config_dir`, `config_local_dir`, `storage_dir`, `storage_local_dir`, `old_version`, `target_version`），冪等執行舊資產搬移與舊組態預設值升級，成功回傳 `True`；若發生未預期 I/O 失敗則拋出例外由 `AtomicEngine` 觸發快照回滾。
- **階段決策紀錄**：`[P03:DR-01]` 各模組新增之遷移腳本統一採用 Patch 級通用萬用字元檔名（`1.2.7.x.py`, `1.0.1.x.py`, `1.2.1.x.py`, `1.2.4.x.py`），使跨 Triplet 之 `@build` 同步（如 `1.0.0.build -> 1.0.1.build`）與正式版安裝（`1.0.0.0 -> 1.0.1.0`）皆能自動觸發。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與異動清單中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-03 皆有具體錯誤攔截與沙盒隔離策略
- [x] **依賴純淨**：100% 符合 NFR-01 ~ NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *問題 1*：若開發者本機同時在舊路徑 `.cache/knowledge-db/models/` 與新路徑 `.storage.local/knowledge-db/models/` 都有部分檔案，遷移腳本直接 `os.replace` 目錄在非空目標目錄下會拋出 `OSError`？
  - *解法*：遷移腳本針對目錄型資產採用逐項遞迴合併搬移：若目標子路徑不存在則直接 `shutil.move`，若目標檔案已存在則保留新檔並清理舊檔，最後清理空舊目錄，保證 100% 跨平台與非空目錄安全。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/{_project,core,agents-workflow,knowledge-db,gdrive-support}/README.md` | Modify | 對齊五大語意空間路徑映射與組態覆寫說明 |
| **專題手冊** | `docs/core/{API_REFERENCE,SNAPSHOT_AND_ROLLBACK,ZIP_PACKAGE_SPEC}.md`, `docs/agents-workflow/{FACTORY_PIPELINE,user_guide}.md`, `docs/knowledge-db/{architecture,call_graph_and_reference_index,incremental_hot_reload,retrieval}.md` | Modify | 全面將持久帳本、模型與索引路徑更新為 `storage.local://`，本機組態與憑證更新為 `config.local://` |
| **設計決策** | `docs/{core,agents-workflow,knowledge-db}/DESIGN_NOTES.md` | Modify | 更新 `DN-17`、`DN-19`、`DN-AW-09`、`DN-AW-18`、`DN-01` 反映五大空間與版本晉升 Hook 遷移 |
| **微觀註解** | 各模組源碼 Docstrings 與隨包 `README.md` / `assets/` | Modify | 同步更新所有殘留舊 URI 描述並重發布 Skills |
| **發布日誌** | `CHANGELOG.md` | Modify | 於主計畫結案時統一記錄五大語意空間與全模組版本晉升摘要 |

- **決策定稿**：**[P04:DR-01]** 確認以零執行期歷史包袱、全數收斂於 `scripts/migrations/*.py` 之方案推進實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core`、`dev`、`server`、`vscode-support` 空間對齊、遷移腳本擴充 (`1.2.7.x.py`)、隨包指南更新、版本遞增與單元測試
- [x] **TASK-02**：實作 `gdrive-support` 空間對齊 (`config.local://` 憑證與 `storage.local://` 同步帳本)、`1.0.1.x.py` 遷移腳本、母倉組態遷移、版本遞增與單元測試
- [x] **TASK-03**：實作 `file-space`、`ast`、`knowledge-db` 儲存空間對齊 (`storage.local://`)、鎖檔分離 (`cache://`)、沙盒 `hook.dev.py`、遷移腳本 (`1.0.1.x.py` / `1.2.1.x.py`)、母倉 `cloud.exclude` 防護、版本遞增與單元測試
- [x] **TASK-04**：實作 `agents-workflow` 清冊空間對齊 (`storage.local://`)、拔除 `_migrate_legacy_manifest`、新增 `1.2.4.x.py` 遷移腳本、更新 Skills/Snippets、版本遞增與單元測試
- [x] **TASK-DOC**：同步更新 `docs/{_project,core,agents-workflow,knowledge-db,gdrive-support}/` 知識庫文檔，執行全模組 `--sync` 安裝、本機資產無損遷移與 `agents-workflow release` 驗證

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01 / 02 / 03** | Minor | 同步更新 `vscode_support/__init__.py`、`ast_engine/__init__.py`、`knowledge_db/__init__.py`、`gdrive_support/__init__.py` 之 `__version__` 以通過 `dev check`，並於 `core/engine.py` (`act_solve_deps`) 補齊對已安裝 `@build` 相依模組之版本保持邏輯 | 已同步寫入並通過全模組 `dev check` 與 `dev test -q --sync` |

