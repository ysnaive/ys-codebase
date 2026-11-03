# 需求規格說明書 (Requirements Specification)

> 功能名稱：2026_11_03_1701_vscode_support_module_and_core_ide_decoupling  
> 建立日期：2026-11-03  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **`core` 零 IDE 假設剝離、`on_env_synced` 事件廣播與測試/清冊對齊** | 1. 物理刪除 `ys_codebase/source/core/core/ide_projector.py` 與 `ys_codebase/source/core/tests/test_ide_projector_cross_platform.py`，並自 `core/__init__.py` 移除 `ide_projector` 公開匯出（`[P01:DR-01]`）。<br/>2. 於 `core/installer.py:sync_pip_dependencies()` 結尾移除 `IdeProjector` 匯入與呼叫，改為廣播 `events.broadcast("on_env_synced", ExecutionContext("core", "env_sync", []), emit_module="core")`，並於 `core/contributes/core.json` 之 `events` 清冊同步登錄 `on_env_synced`。<br/>3. 同步更新 `ys_codebase/source/core/tests/test_venv_core.py`，移除頂層 `from core.ide_projector import IdeProjector`，並將 `test_ft_08_installer_sync_pip_dependencies` 改為斷言 `events.broadcast("on_env_synced", ...)` 被呼叫。 | P0 | [P00:DR-01] |
| **FR-02** | **修補 `ContributesValidator._parse_default_literal` 支援浮點數與負數 (`[TODO-18]`)** | 於 `core/validator.py:ContributesValidator._parse_default_literal(def_str)` 擴充數值字面量解析：支援帶正負號之十進位整數（如 `"-1"`、`"0"`、`"42"` 解析為 `int`）與十進位浮點數（如 `"1.0"`、`"-0.5"`、`"900.0"` 解析為 `float`，且不影響布林值或版本號字串如 `"1.0.0"` 之字串回退），使 `"float? = 1.0"` 或 `"int? = -1"` 的 `parse_type_signature` 輸出正確數值型別 `default`。 | P0 | [P00:DR-01], [TODO-18] |
| **FR-03** | **新建 `module:vscode-support` 與 `yscb.venv://current-site-packages` 穩定目錄連結** | 1. 建立 `ys_codebase/source/vscode-support/`（內部套件 `vscode_support`，`__version__ = "1.0.0.0"`，依賴 `core >= 1.2.5`）。<br/>2. `SettingsProjector.ensure_stable_site_packages_link()` 先確保目標 `site-packages` 實體目錄存在（若無 `pip_dependencies` 尚未初始化微環境則主動 `os.makedirs(target_site_pkg, exist_ok=True)` 防範懸空連結），再於 `yscb.venv://current-site-packages` 建立指向當前 Python 版本 `site-packages` 目錄之連結（POSIX 採用 `os.symlink`，Windows 優先採用 `os.symlink` 或免管理員權限之 `cmd /c mklink /J` Directory Junction）（`[P01:DR-02]`）。<br/>3. 成功建立連結時，注入 `.vscode/settings.json` 之 `python.analysis.extraPaths` 恆定為單一路徑 `["./<rel_to_yscb>/.venv/current-site-packages"]`，確保切換本機 Python 版本時 `settings.json` 零變動。 | P0 | [P00:DR-04] |
| **FR-04** | **自動建立 `project://.vscode/` 與 `settings.json` 軟合併（含 `json.schemas` 直接綁定）** | 1. 當已安裝 `vscode-support` 並執行同步時，若 `project://.vscode/` 不存在則自動建立該目錄（`[P00:DR-05]`）。<br/>2. 於 `.vscode/settings.json` 軟合併 `python.analysis.extraPaths`、`python.analysis.exclude`、`files.exclude`、`search.exclude`、`files.watcherExclude` 與 **`json.schemas`**（將各模組與元 Schema 之 `{"fileMatch": [...], "url": "./.vscode/schemas/..."}` 注入 `json.schemas`），並將所有託管項目完整記錄於 `_yscb_managed`（含 `extraPaths`、`excludes`、`analysisExclude`、`jsonSchemas`），100% 保留使用者自訂之非託管設定與自訂 `json.schemas` 條目（`[P01:DR-03]`）。<br/>3. 生成之 Schema 檔案統一存放於 `project://.vscode/schemas/`，並於 `project://.vscode/schemas/.gitignore` 寫入 `*` 達成 100% 自我忽略（不修改 `project://.gitignore`）。 | P0 | [P00:DR-03], [P00:DR-05] |
| **FR-05** | **單檔級 JSON Schema 編譯器 (`SchemaCompiler`)、`uri`/`path` 型別、`@desc(...)` 屬性與同構 `configurable/_format.json`（嚴守 Zero-Probing）** | 1. `vscode-support/contributes/_format.json` 開放 `json_schemas` 擴充點（支援 `file_match`、`schema_source: enum(contributes_format, configurable_template, static_file)`、`schema_path`、`description`）；業務代碼嚴守 `dev check` 之 Zero-Probing 規則（**0 處 `module.source://` 存取**，`[P01:DR-04]`）。<br/>2. **型別簽名擴充 (`uri`/`path` 與 `@desc(...)`)**：`ContributesValidator.parse_type_signature` 原生支援 `uri`/`path` 一等公民型別與 `@<attr>(<平衡括號內容>)`（含 `@desc(...)`）正交屬性語法；`SchemaCompiler` 自動為 `uri`/`path` 注入全系統已註冊語意 URI 協議前綴之 VS Code `defaultSnippets`，並將 `@desc(...)` 轉譯為 `description` / `markdownDescription`。<br/>3. **擴充點 Schema (`schemas/contributes/<mod>.schema.json`)**：掃描已安裝模組 `module://<mod>/contributes/_format.json`，轉譯為 JSON Schema Draft-07（`_types` $\to$ `"$defs"`，支援自遞迴 `$Ref`、枚舉 `enum`、`default`、合併策略 `markdownDescription`，固定鍵物件設 `additionalProperties: false` 並以 `patternProperties: {"^__.*__$": {}}` 放行 `__provider__`/`__providers__`）；頂層支援直接放置擴充點鍵或外層包裹 `{"<mod>": ...}`（相容 `config/<mod>/contribute.json` 雙結構），綁定 `["**/contributes/<mod>.json", "**/config/<mod>/contribute.json"]`。<br/>4. **同構組態 Schema (`schemas/config/<mod>.schema.json`)**：可組態模組於 `configurable/_format.json` 定義同構契約（`core/engine.py` 於安裝時保留 `module://<mod>/configurable/_format.json`），`SchemaCompiler` 優先讀取 `module://<mod>/configurable/_format.json` 並結合 `module.mirror://<mod>/<ver>.zip` 內之 `configurable/config.*.json` 提取預設值（無 `_format.json` 時自動由範例值推導型別），綁定 `["**/config/<mod>/config.*.json", "**/source/<mod>/configurable/config.*.json", "**/<mod>/configurable/config.*.json"]`。<br/>5. **元 Schema (`schemas/meta/{format-meta,manifest}.schema.json`)**：自注入校驗 `**/contributes/_format.json`、`**/configurable/_format.json` 與 `**/manifest.json`。 | P0 | [P00:DR-02], [P00:DR-03], [P00:DR-06] |
| **FR-06** | **生命週期 Hook 防重觸發、完全可逆拆卸 (`on_remove`) 與 CLI 指令** | 1. `scripts/hook.core.py` 僅訂閱 `on_env_synced` 與 `on_reload`（避免在單次 `install`/`update` 中與 `on_installed`/`on_update` 重複觸發 3 次 I/O，`[P01:DR-05]`）。<br/>2. 響應 `on_remove`（當 `ctx.args` 包含 `"vscode-support"` 時）或執行 `python yscb.py vscode-support revert` 時，依據 `_yscb_managed` 100% 剔除注入之 `extraPaths`、`excludes`、`analysisExclude` 與 `json.schemas`，並物理清除 `project://.vscode/schemas/` 與 `yscb.venv://current-site-packages`。<br/>3. 提供 `python yscb.py vscode-support <status|sync|revert>` 三個標準 CLI 指令，並於 `contributes/agents-workflow.json` 注入 `/how-to-yscb` 與 `/how-to-config-yscb` 導覽卡。 | P0 | [P00:DR-01], [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **`.vscode/settings.json` 含 JSONC 註解或尾隨逗號（非標準 JSON）** | 讀取失敗時向 `stderr` 輸出 `[vscode-support] Warning` 並安全略過修改 `settings.json`，絕不覆寫或損毀使用者既有設定檔。 |
| **EC-02** | **檔案系統或權限不支援建立 `current-site-packages` Symlink / Junction，或所有模組皆無 `pip_dependencies` 導致 `site-packages` 尚未建立** | 建立連結前主動確保目標 `site-packages` 目錄存在（防止懸空連結）；若建立連結拋出 `OSError` / `SubprocessError`，自動靜默降級（Fallback）為既有跨平台實際路徑列表（`./ys_codebase/.venv/<py_tag>/...`）。 |
| **EC-03** | **使用者在 `.vscode/settings.json` 自訂了其他 `json.schemas` 或 `extraPaths`** | 僅依據 `_yscb_managed["jsonSchemas"]`（比對受託管之 `url` 集合）與 `_yscb_managed["extraPaths"]` 執行差集更新與還原，100% 保留使用者自訂條目。 |
| **EC-04** | **`contributes/_format.json` 含自遞迴型別（如 `core` 之 `$CommandNode`）、混合萬用鍵 `"*"` 或 `config/<mod>/contribute.json` 採用外層包裹 `{"<mod>": ...}`** | `$CommandNode` 轉譯為 `{"$ref": "#/$defs/CommandNode"}` 避免展開無限遞迴；同時含固定鍵與 `"*"` 之字典將固定鍵放入 `properties`、`"*"` 規則放入 `additionalProperties`；頂層 `properties` 同步允許 `"<mod>"` 包裹鍵（指向自身擴充點物件定義），完美相容 `contribute.json` 兩種合法寫法。 |
| **EC-05** | **模組被移除（如移除某業務模組）後殘留舊 Schema 檔案** | 每次 `sync` 時比對當前應生成之 Schema 集合，自動清理 `.vscode/schemas/` 下已不再安裝之模組舊 `.schema.json` 並同步更新 `settings.json` 之 `json.schemas`，維持確定性狀態。 |
| **EC-06** | **模組無 `configurable/`（如 `ast`、`file-space`、`dev`）或 `.mirror` 壓縮包不存在** | 當模組於 `module.mirror://<mod>/<installed_ver>.zip` 內無 `configurable/config.*.json` 時，跳過生成 `schemas/config/<mod>.schema.json`，不報錯。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **零外部依賴、Zero-Probing 合規與確定性輸出** | `module:vscode-support` 100% 使用 Python 標準庫實作（`pip_dependencies: {}`），100% 通過 `dev check vscode-support`（0 `module.source://` Probing 違規）；在相同已安裝模組清單下，生成之 `.vscode/settings.json` 與 `.schema.json` 內容 100% 確定（Zero-Touch 內容相等時不重寫磁碟、不觸動 mtime）。 |
| **NFR-02** | **執行效能** | 單次 `vscode-support sync`（含全倉 8 個模組 Schema 編譯與 Zero-Touch 比對）本機耗時 $\le 100\text{ms}$。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` `[P01:DR-01]` `core` 版號遞增與測試/事件清冊同步**：移除 `core.ide_projector` 並新增 `on_env_synced` 事件與 `validator.py` 修正後，將 `core/manifest.json` 遞增至 `1.2.5.0`（`core/__init__.py` 無 `__version__`），於 `core/contributes/core.json` 登錄 `on_env_synced`，並同步更新 `core/tests/test_venv_core.py`。
- **`[!NOTE]` `[P01:DR-02]` Python `os.path.lexists` 與目錄連結更新**：在更新 `yscb.venv://current-site-packages` 時，由於目標為目錄 Symlink 或 Windows Junction，不可使用 `shutil.rmtree` 直接刪除連結本身，POSIX 應使用 `os.unlink()`，Windows Junction 應使用 `os.rmdir()` 或 `os.unlink()` 安全移除舊連結點後重建，並確保目標 `site-packages` 目錄預先存在。
- **`[!NOTE]` `[P01:DR-03]` `.vscode/schemas/` 單一集中路徑**：採用做法 B 直接於 `.vscode/settings.json` 綁定 `json.schemas`，將生成的 Schema 置於 `project://.vscode/schemas/`（內含 `project://.vscode/schemas/.gitignore` 寫入 `*`）。
- **`[!NOTE]` `[P01:DR-04]` 嚴守 `dev check` Zero-Probing 與同構組態 `_format.json` 規範**：`dev/checker.py:983` 禁止非 `core`/`dev` 模組在業務代碼中出現 `"module.source://"`；針對可組態模組，同步於 `dev/checker.py:773` 與 `core/engine.py:1800` 開放 `configurable/_format.json` 同構組態契約並保留於 `module://<mod>/configurable/_format.json`，使 `SchemaCompiler` 100% 從 `module://<mod>/` 與 `module.mirror://<mod>/<ver>.zip` 讀取，絕不存取 `module.source://`。
- **`[!NOTE]` `[P01:DR-05]` 避免單次安裝重複觸發 3 次 Hook**：`installer.py` 在 `install`/`update`/`remove`/`reload`/`restore` 結尾均會呼叫 `sync_pip_dependencies()`（觸發 `on_env_synced`），故 `vscode-support/scripts/hook.core.py` 僅需訂閱 `on_env_synced`、`on_reload` 與 `on_remove`，不必訂閱 `on_installed` / `on_update`。
