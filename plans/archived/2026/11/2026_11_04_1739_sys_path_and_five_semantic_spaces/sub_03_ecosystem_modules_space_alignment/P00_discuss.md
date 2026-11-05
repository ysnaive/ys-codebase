# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：全生態系模組五大語意空間映射對齊與既有資產無損遷移 (Ecosystem Modules Five Semantic Spaces Alignment)  
> 建立日期：2026-11-05  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Medium)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：承主計畫 `[P00:DR-04]` 裁決與 `sub_02` 已落地的五大語意空間引擎（`config://`、`config.local://`、`storage://`、`storage.local://`、`cache://`），透過 4 分區盲眼子代理地毯式審查全倉 9 大模組、母倉組態、Skills 與文檔，將全生態系模組（`gdrive-support`、`knowledge-db`、`ast`、`file-space`、`agents-workflow`、`core`、`dev`、`server`、`vscode-support`）之本機憑證（`credentials.json`、`token.json`、`config.local.json`）、模型權重（`models/`）、索引圖譜、同步狀態帳本（`sync_state.json`、`readme_sync_state.json`）、發布清冊與動態 `.gitignore` 帳本全面對齊遷移至 `config.local://` 與 `storage.local://`，保留純揮發性快取與進程鎖檔於 `cache://`，不留任何角落殘留，並於 `sub_03` 將 `core`（推進至 `"1.2.7.0"`）與其餘受影響模組一同晉升版本。
- **核心目標**：
  1. 將全生態系模組之 URI 註冊 (`manifest.json` 與 `contributes/core.json`)、組態預設值、儲存路徑解析與測試沙盒初始化 (`hook.dev.py` / `sandbox.py`) 全面對齊五大語意空間。
  2. 將跨進程鎖檔（`sync.lock`、`.kdb_index.lock`、`.ast_index.lock`）與揮發性日誌/狀態（`sync.log`、`daemon.json`）留駐於 `cache://`，並確保單元測試傳入自訂沙盒目錄時鎖檔跟隨沙盒隔離而不污染宿主 `.cache/`。
  3. 實作本機既有舊路徑資產（`config/core/config.local.json`、`config/gdrive-support/credentials.json`、`.cache/gdrive-support/*`、`.cache/knowledge-db/*`、`.cache/ast/*`、`.cache/file-space/*`、`.cache/agents-workflow/*`、`.cache/core/gitignore_dynamic.json`）向新語意空間之冪等無損自動遷移，並將 `ys_codebase/.config.local` 與 `ys_codebase/.storage.local` 補入母倉 `config/file-space/contribute.json` 之 `cloud` 空間排除清單及 `AGENTS.md` 黑盒清單。
  4. 同步全模組隨包指南 (`assets/config_guide.md`、`assets/usage_guide.md`)、Skills (`how-to-config-yscb`、`how-to-yscb`、`yscb-module-dev`) 與 `docs/` 系統知識庫，重新編譯發布工作流產物，並協同推進模組版本號（含 `core` 晉升至 `"1.2.7.0"`）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `sub_02` 於 `core.uri`、`core.vfs` 與 `core.config` 實作之 `config.local://` (`yscb://.config.local/`) 與 `storage.local://` (`yscb://.storage.local/`) 協議解析與 `act_migrate` 升級框架。
  - 復用 `core.platform.lock.InterProcessLock` 進行跨進程鎖管理。
- **邊界排除 (Explicitly Excluded)**：
  - 五大語意空間底層 URI 解析引擎與 `core.config` 雙軌讀寫機制本體（已於 `sub_02` 完成）。
  - 全模組 `sys.path` 派發注入與 `dev/checker.py` 靜態 AST 守門（已於 `sub_01` 完成）。
- **架構影響範圍**：`gdrive-support`、`knowledge-db`、`ast`、`file-space`、`agents-workflow`、`core`、`dev`、`server`、`vscode-support`、母倉 `ys_codebase/config/` 及系統知識庫 `docs/`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 全生態系模組五大語意空間精確歸屬、鎖檔沙盒隔離與盲審死角清零**：
  1. **`gdrive-support`**：
     - `manifest.json:23-25` (`uris.storage`) 與 `contributes/core.json:2-9` (`gdrive-support.storage`)：`cache://gdrive-support` $\to$ `storage.local://gdrive-support/`。
     - `configurable/_format.json:4-5`、`configurable/config.project.json:4-5`、母倉 `ys_codebase/config/gdrive-support/config.project.json:4-5`、`gdrive_support/config.py:200-201,514-517`：`credentials_uri` 與 `token_uri` 預設值統一改為 `config.local://gdrive-support/{credentials,token}.json`。
     - `gdrive_support/config.py:307-332` (`is_sensitive_credential_path`)：納入 `ys_codebase/.config.local/` 與 `ys_codebase/.storage.local/`。
     - `gdrive_support/coordinator.py:171-175,305-309,320-324`：`sync_state.json` 與 `readme_sync_state.json` 預設改為 `storage.local://gdrive-support/...`；`sync.lock` 與 `sync.log` (`L310-319`) **留駐 `cache://gdrive-support/`**。
  2. **`file-space`、`ast`、`knowledge-db`**：
     - **`file-space`**：`manifest.json:20-22`、`contributes/core.json:3-14` (`file-space.storage`)、`file_space/manager.py:151-165` (`storage_root`)、`scripts/hook.dev.py:21-25` 全面對齊 `storage.local://file-space/` (`.storage.local/file-space`)；`file-space.cache` 維持 `cache://file-space/`。
     - **`ast`**：`manifest.json:33-35`、`contributes/core.json:3-14` (`ast.storage`)、`ast_engine/bundler.py:439-460` (`_resolve_default_ast_storage_dir`)、`scripts/hook.dev.py:11-24` 全面對齊 `storage.local://ast/` (`.storage.local/ast`)；`ast_engine/engine.py:542-548` 之 `.ast_index.lock` 於預設儲存模式下分離至 `cache://ast/.ast_index.lock`（測試顯式注入自訂 `storage_dir`/`project_root` 時跟隨沙盒目錄隔離）。
     - **`knowledge-db`**：`manifest.json` 補齊 `"uris": {"storage": "storage.local://knowledge-db"}`；`contributes/core.json:3-8` (`knowledge.storage` $\to$ `storage.local://knowledge-db/`，並新增 `knowledge.cache` $\to$ `cache://knowledge-db/`)；`knowledge_db/pipeline.py:49-69` (`_resolve_default_knowledge_storage_dir`)、`knowledge_db/embedding.py:66` (`models/` 預設路徑)、`scripts/hook.dev.py:24-28`、`tests/test_cli.py:308-310` 對齊 `storage.local://knowledge-db/`；`knowledge_db/config.py:208-209` 對齊 `config://knowledge-db/config.project.json` 與 `config.local://knowledge-db/config.local.json`；`pipeline.py:440-447` 之 `.kdb_index.lock` 於預設儲存模式下分離至 `cache://knowledge-db/.kdb_index.lock`（測試自訂 `storage_dir` 時跟隨沙盒隔離）。
  3. **`agents-workflow`、`core`、`dev`、`server`、`vscode-support`**：
     - **`agents-workflow`**：`publisher.py:30-32` (`PROJECT_MANIFEST_CACHE_URI`, `LOCAL_MANIFEST_CACHE_URI`, `SHA1_CACHE_URI`) 改為 `storage.local://agents-workflow/...`，並將原位於業務代碼 `publisher.py:130-156` 之 `_migrate_legacy_manifest` 歷史遷移分支拔除收斂至 `scripts/migrations/`；`publisher.py:619` 提示訊息與 `plans/session_trace.py:85-90` 降級讀檔納入 `config.local://agents-workflow/config.local.json`；`compiler.py:4,678`、`contributes/core.json:312`、`tests/test_compiler.py:73` 清除殘留舊詞 `cache.root://` 對齊為 `cache://`。
     - **`core`**：`core/gitignore.py:27,189-215,470` (`DYNAMIC_CACHE_URI`) 改為 `storage.local://core/gitignore_dynamic.json`；`core/engine.py`、`core/contributes/core.json`、`core/contributes/_manifest.md` 補齊 `config.local://` 與 `storage.local://` 描述。
     - **`dev`**：`dev/testing/sandbox.py:80-86` 沙盒預建目錄補齊 `engine/.config.local`、`engine/storage`、`engine/.storage.local`。
     - **隨包指南與系統文檔**：同步更新 `core`、`dev`、`server`、`knowledge-db`、`gdrive-support`、`vscode-support` 之 `assets/{config_guide,usage_guide}.md`、`yscb-module-dev/SKILL.md`、`how-to-config-yscb/SKILL.md`、`ys_codebase/config/agents-workflow/snippets/project_role.md` 與 `docs/{_project,core,agents-workflow,knowledge-db,gdrive-support}/`。
- **[P00:DR-02] 業務程式碼零歷史債鐵律與版本晉升 Hook (`scripts/migrations/`) 自癒升級**：
  1. **業務程式碼零歷史債鐵律**：各模組運行時業務代碼（`gdrive_support/config.py`、`gdrive_support/coordinator.py`、`file_space/manager.py`、`ast_engine/bundler.py`、`knowledge_db/pipeline.py`、`agents_workflow/publisher.py`、`core/gitignore.py`）**嚴禁塞入針對舊路徑（`config://` 舊憑證或 `cache://` 舊帳本/索引/清冊）的運行期 Fallback 或隱式自癒分支**，並同步拔除 `agents_workflow/publisher.py` 既有 `_migrate_legacy_manifest` 執行期遷移包袱，維持業務邏輯 100% 純淨對齊五大語意空間。
  2. **統一收斂於版本晉升 Migration Hook (`scripts/migrations/`)**：所有舊路徑資產搬移與舊預設組態升級（含 `config/core/config.local.json`、`config/gdrive-support/credentials.json`、`config/gdrive-support/config.project.json` 內舊預設 `credentials_uri`/`token_uri` 字串、`.cache/gdrive-support/{token,sync_state,readme_sync_state}.json`、`.cache/file-space/{snapshots,cursors}`、`.cache/ast/{indices,bundles}`、`.cache/knowledge-db/{models,indices,bundles}`、`.cache/agents-workflow/*.json` 及 `.cache/core/gitignore_dynamic.json`），一律透過各模組 `scripts/migrations/*.py` 在版本晉升 (`act_migrate`) 時一次性冪等完成。
  3. **母倉 `cloud` 同步空間排除清單防護**：於 `ys_codebase/config/file-space/contribute.json:58-70` 之 `cloud.exclude` 補入 `"ys_codebase/.config.local"` 與 `"ys_codebase/.storage.local"`，防止雲端同步誤掃描百 MB 級模型/索引與同步狀態帳本。
  4. **全模組版本號協同晉升**：統一將 `core` 推進至 `"1.2.7.0"`，並協同遞增本次涉及空間遷移與修改之各生態系模組版本號，藉由版本晉升觸發 `act_migrate` 完成全倉既有資產自癒升級與驗證。

---

## 3. 開放議題與確認紀錄

- 全倉 4 分區盲眼地毯式盤點已完成並收斂入 `[P00:DR-01]` 與 `[P00:DR-02]`，無待決開放議題。
