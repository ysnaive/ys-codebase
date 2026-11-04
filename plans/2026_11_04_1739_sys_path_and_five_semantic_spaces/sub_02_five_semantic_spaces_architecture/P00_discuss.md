# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_five_semantic_spaces_architecture  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「1. ".config.local" & ".storage.local"」
  - 「sub 02: 五大語意空間重構」
  - 「方案 B（同步升級 engine.py 之 act_migrate），如無必要絕對不將版本債殘留近業務中」
- **核心目標**：
  1. **五大語意資料空間正交化**：將模組資料空間依「語意職責（組態 vs 資料狀態）」、「Git 版本控制政策（團隊共享 vs 本機私有忽略）」與「硬體持久性（實體磁碟持久 vs `tmpfs` 揮發快取）」擴充為五大語意 URI 協議：
     - `config://` $\to$ `yscb://config/<mod>/`（Git Tracked 團隊共享設定與 `contribute.json`，納入 `snapshot://`）
     - `config.local://` $\to$ `yscb://.config.local/<mod>/`（Git Ignored 本機私有設定 `config.local.json` 與機密憑證 `credentials.json`/`token.json`，實體磁碟持久，納入 `snapshot://`）
     - `storage://` $\to$ `yscb://storage/<mod>/`（Git Tracked 團隊持久化資料資產，納入 `snapshot://`）
     - `storage.local://` $\to$ `yscb://.storage.local/<mod>/`（Git Ignored 本機持久化狀態帳本、語意模型權重與本地索引庫，實體磁碟持久、絕不掛載於 `tmpfs`，且**排除於 `act_snapshot` 之外**）
     - `cache://` $\to$ `yscb://.cache/<mod>/`（Git Ignored 純揮發性快取、跨進程鎖檔、日誌與測試沙盒，可安全掛載於 `tmpfs` 記憶體磁碟，排除於 `act_snapshot` 之外）
  2. **預設 `.gitignore` 與安全邊界保護**：於 `core/contributes/core.json`、`core/gitignore.py` 與 `core/installer.py` 將 `yscb://.config.local/` 與 `yscb://.storage.local/` 納入核心預設 Git 忽略清單（使 `yscb://config/` 與 `yscb://storage/` 成為 100% 純淨的 Git Tracked 目錄）。
  3. **`core.config` 雙軌空間純淨分離與 `act_migrate` 多段式增量遷移升級**：
     - `ConfigManager.get_config_path(module, local=False)`：100% 純淨路由，`local=False` 指向 `config://{module}/config.project.json`；`local=True` 指向 `config.local://{module}/config.local.json`，**絕不在核心業務邏輯或常態 `hook.core.py` 殘留舊版相容技術債**。
     - 升級 `AtomicEngine.act_migrate`：突破過去僅支援第 2 段 `{major}.{minor}.x.py` 的限制，擴充支援第 3 段 `{major}.{minor}.{patch}.x.py`（如 `1.2.7.x.py`）與第 4 段 `{major}.{minor}.{patch}.{rev}.py` 階梯遷移腳本，並於 `Installer.cmd_restore` 覆寫升級既有模組時同步觸發 `act_migrate`。
     - 於 `ys_codebase/source/core/scripts/migrations/1.2.7.x.py` 實作遷移腳本（配合 `core` `manifest.json` 推進至 `1.2.7.0`）：當 `core` 升級至 `1.2.7.*` 時，自動將全模組舊版 `config://<mod>/config*.local.json` 無損遷入 `config.local://<mod>/config*.local.json` 並刪除舊檔。
  4. **快照與模組移除生命週期治理 (`core/engine.py`)**：
     - `act_snapshot` / `act_restore_snapshot`：納入 `config://`、`config.local://`、`storage://` 與 `module://`，**明確排除 `storage.local://` 與 `cache://`**。
     - `act_delete(..., purge=True)`：當指定 `--purge` 時，一併清理 `storage://`、`storage.local://`、`config://` 與 `config.local://` 四大持久化空間。
  5. **開發工具鏈與 IDE 支援對齊 (`vscode-support` & `dev`)**：
     - `vscode-support`：`SchemaCompiler` 為 `uri` / `path` 補齊 `config.local://` 與 `storage.local://` 自動完成片段（`defaultSnippets`），並將 `**/.config.local/<mod>/config.*.json` 納入模組組態 Schema 之 `fileMatch`；`SettingsProjector` 將 `**/.config.local/**` 與 `**/.storage.local/**` 納入 `ANALYSIS_EXCLUDE_PATTERNS`。
     - `dev`：`SandboxContext.set_module_config` 根據檔名是否為 `*.local.json` 自動分流寫入沙盒之 `.config.local/<mod>/` 或 `config/<mod>/`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用並擴充 `core/uri.py`、`core/config.py`、`core/engine.py`、`core/gitignore.py`、`core/installer.py`、`vscode_support/schema_compiler.py`、`vscode_support/projector.py` 與 `dev/testing/sandbox.py`。
- **邊界排除 (Explicitly Excluded)**：
  - 各業務模組（`gdrive-support`、`knowledge-db`、`ast`、`file-space`、`agents-workflow`）內部業務資產之路徑改寫與實體搬遷歸屬 `sub_03_ecosystem_modules_space_alignment`。
- **架構影響範圍**：
  - `core`：`core/uri.py`、`core/contributes/core.json`、`core/gitignore.py`、`core/installer.py`、`core/config.py`、`core/engine.py`、`core/commands/dispatcher.py`、`core/manifest.json`、`core/scripts/migrations/1.2.7.x.py` 及 `core/tests/{test_uri.py,test_config.py,test_engine.py,test_gitignore.py,test_locale.py,test_core_commands.py}`
  - `vscode-support`：`vscode_support/schema_compiler.py`、`vscode_support/projector.py` 及 `vscode-support/tests/test_vscode_support.py`
  - `dev`：`dev/testing/sandbox.py`
  - `docs`：`docs/_project/STANDARDS.md`、`docs/core/README.md`、`docs/core/DESIGN_NOTES.md`、`docs/core/lifecycle_and_hooks.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 五大語意空間命名與物理路徑定錨**：
  - `config://` $\to$ `yscb://config/`
  - `config.local://` $\to$ `yscb://.config.local/`
  - `storage://` $\to$ `yscb://storage/`
  - `storage.local://` $\to$ `yscb://.storage.local/`
  - `cache://` $\to$ `yscb://.cache/`
- **[P00:DR-02] 升級 `act_migrate` 支援多段式遷移腳本並以 `1.2.7.x.py` 執行舊版 `config.local.json` 遷移（零業務版本債）**：
  - 採納開發者裁定：「方案 B（同步升級 `engine.py` 之 `act_migrate`），如無必要絕對不將版本債殘留進業務中」。
  - `core/config.py`、`core/engine.py`、`core/commands/dispatcher.py` 維持 100% 純淨新路徑定址；升級 `AtomicEngine.act_migrate` 支援 `{major}.{minor}.x.py`、`{major}.{minor}.{patch}.x.py` 與 `{major}.{minor}.{patch}.{rev}.py` 三種粒度之遷移腳本，並在 `cmd_restore` 升級既有模組時同步調用 `act_migrate`；舊版 `config://<mod>/config*.local.json` 遷移獨立收斂於 `source/core/scripts/migrations/1.2.7.x.py`。
- **[P00:DR-03] 快照 (`act_snapshot`) 與模組清除 (`act_delete --purge`) 邊界策略**：
  - `act_snapshot` 備份 `yscb.config.json`、`config://`、`config.local://`、`storage://` 與 `module://`；**排除 `storage.local://` 與 `cache://`**。
  - `act_delete(module_name, purge=True)` 清除該模組於 `storage://`、`storage.local://`、`config://`、`config.local://` 四大持久化空間的所有資料。

---

## 3. 開放議題與確認紀錄

- 開發者已確認採納方案 B（同步升級 `engine.py` 之 `act_migrate` 支援多段式版號遷移腳本 `1.2.7.x.py`，絕不將版本債殘留於業務邏輯中），並完成 `/blind-subagent` 審查收斂。
