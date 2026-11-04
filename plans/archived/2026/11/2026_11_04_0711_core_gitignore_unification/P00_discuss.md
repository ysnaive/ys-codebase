# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`core.gitignore` 統一忽略規則收斂引擎與跨模組遷移 (`core_gitignore_unification`)  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 將散落於各模組（`core/installer.py`、`core/pip_manager.py`、`agents-workflow/publisher.py`、`vscode-support/schema_compiler.py`）之 `.gitignore` 生成與區塊維護邏輯統一抽離至 `core.gitignore`。
  - 由 `core` 原生提供宣告式 `contributes`（`gitignore` 擴充點）、SDK 介面（強制傳入 `module` 參數以支援 `# [<module>]` 分組註解）、生命週期事件與 `yscb.py gitignore <status|sync>` CLI，統一收斂並產出根目錄單一 `project://.gitignore`。
- **核心目標**：
  1. **單一正統引擎 (`core.gitignore`)**：消除全倉 4 處分散且重複的 `.gitignore` 讀寫與 Regex 替換邏輯，統一收斂至 `core/gitignore.py`。
  2. **根目錄單檔 SSOT (`project://.gitignore`)**：遵循 Monorepo 與現代專案最佳實踐，將所有靜態宣告（`contributes`）與執行期動態註冊（SDK）之語意 URI / Glob 規則自動換算為相對於 `project://` 的精確路徑，統一寫入 `project://.gitignore` 單一託管區塊，並清理過時的子目錄 `.gitignore`（如 `yscb://.gitignore` 與 `.vscode/schemas/.gitignore`）。
  3. **模組分組可觀測性 (`# [<module>]`)**：於單一託管區塊 `# === YSCB MANAGED GITIGNORE BEGIN ===` ~ `# === YSCB MANAGED GITIGNORE END ===` 內，強制按貢獻來源（`# [core]`、`# [vscode-support]`、`# [agents-workflow]`、`# [project]` 等）分組排序輸出；SDK 介面強制要求傳入 `module: str` 參數。
  4. **三維接口與自動生命週期連動**：提供 `core/contributes/_format.json` 之 `gitignore` 擴充點、`core.gitignore` SDK（`set_dynamic_patterns(module, patterns)`、`clear_dynamic_patterns(module)`、`sync()`、`status()`）、CLI `yscb.py gitignore <status|sync>`，以及隨 `reload` / `install` / `remove` / `restore` 自動收斂與卸載清理。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `core.uri` 進行語意 URI（如 `yscb://.venv/`、`project://.vscode/schemas/`）至 `project://` 相對路徑之動態解算與跨平台 `/` 正規化。
  - 復用 `core.vfs` (`vfs.read_text`, `vfs.write_text(..., atomic=True)`) 實現 Zero-Touch 比對與原子落盤。
  - 復用 `core.contributes` 之 `__providers__` 來源追蹤標記，自動識別靜態 `contributes` 規則所屬模組名稱。
- **邊界排除 (Explicitly Excluded)**：
  - 不建立獨立的 `module:git-support` 模組（僅針對 `.gitignore` 文字收斂，不涉及 `git commit` / `git tag` 子程序封裝或 `pre-commit` 守門）。
  - 不刪除或覆寫使用者在 `project://.gitignore` 託管區塊以外手寫之自訂規則（如母倉自訂的 `ys_codebase/release/**/*.zip` 與 `!**/configurable/*.local.json`）。
- **架構影響範圍**：
  - `core`：新增 `core/gitignore.py`、擴充 `contributes/_format.json` 與 `contributes/core.json`、更新 `installer.py` / `pip_manager.py` / `engine.py` / `commands/builtin.py`。
  - `agents-workflow`：重構 `ReleasePublisher.sync_gitignore` 委派 `core.gitignore` SDK 註冊動態規則並觸發同步。
  - `vscode-support`：於 `contributes/core.json` 宣告 `project://.vscode/schemas/` 靜態忽略規則，移除 `schema_compiler.py` 寫入子目錄 `.vscode/schemas/.gitignore` 之邏輯並於 `sync` / `revert` 時自動清理舊子目錄 `.gitignore`。
  - `docs/`：同步更新 `docs/core/`、`docs/vscode-support/` 與 `docs/agents-workflow/` 相關說明。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 統一收斂至根目錄單一 `project://.gitignore` 與舊版區塊無縫遷移**：
  - 全系統統一維護單一 `project://.gitignore`。凡規則以語意 URI（如 `yscb://.venv/`、`project://.vscode/schemas/`）宣告者，`core.gitignore` 自動將其解析並轉換為相對於 `project://` 之錨定路徑（例如在子目錄拓撲下 `yscb://.venv/` 轉為 `/ys_codebase/.venv/`；在 `yscb:// == project://` 同根拓撲下轉為 `/.venv/`）。
  - 首次同步時，自動吸收並移除 `project://.gitignore` 中舊版的 `# === YSCB INTERNAL IGNORE BEGIN ===`、`# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===` 與 `# YS-Codebase Autonomous Internal Ignore Rules` 遺留段落（同時完整保留非標準之母倉自訂行如 `ys_codebase/release/**/*.zip`、`!**/configurable/*.local.json`），並自動清理已廢棄之子目錄 `yscb://.gitignore`（當 `yscb:// != project://` 且該檔僅含舊版 YSCB 託管內容時）與 `project://.vscode/schemas/.gitignore`。
- **[P00:DR-02] 單一託管區塊與 `# [<module>]` 強制分組標頭（SDK 強制傳入 `module` 參數）**：
  - 託管區塊外層統一使用 `# === YSCB MANAGED GITIGNORE BEGIN ===` 與 `# === YSCB MANAGED GITIGNORE END ===`。
  - 區塊內部依模組名稱（`core` 置頂，其餘模組按字母序，`project` 置底）輸出 `# [<module>]` 分組註解與去重排序後之規則。
  - `core.gitignore` 提供之動態規則註冊 SDK（如 `register_dynamic(module: str, patterns: Iterable[str], sync_now: bool = True)` / `clear_dynamic(module: str, sync_now: bool = True)`，持久化於 `cache://core/gitignore_dynamic.json`）強制要求呼叫端傳入非空之 `module` 識別名稱。
- **[P00:DR-03] 跨模組全面收斂（`core` + `agents-workflow` + `vscode-support`）與卸載自癒**：
  - `core`、`agents-workflow` 與 `vscode-support` 全部收斂至 `core.gitignore`。
  - 當執行 `yscb remove <mod>` 或 `engine.act_delete(<mod>)` 時，自動清除該模組於 `cache://core/gitignore_dynamic.json` 之動態項目並重新執行 `core.gitignore.sync()`，確保已卸載模組之靜態與動態忽略規則 100% 從 `project://.gitignore` 託管區塊中移除。
- **[P00:DR-04] 開放三維接口（Contributes + SDK + CLI `yscb.py gitignore <status|sync>`）**：
  - 於 `core/contributes/_format.json` 新增 `"gitignore"` 擴充點；於 `core/contributes/core.json` 新增 `gitignore` CLI 指令（`status` / `sync`）與 `on_gitignore_synced` 事件。

---

## 3. 開放議題與確認紀錄

- **Q1：維度 A 採用根目錄單檔 `project://.gitignore` 還是子目錄拆檔？**
  - **A1（已確認）**：採用根目錄單一 `project://.gitignore`（自動依語意 URI 換算相對於 `project://` 之路徑）。
- **Q2：維度 B 託管區塊內部是否加 `# [module]` 註解分組？**
  - **A2（已確認）**：是，單一託管區塊內按 `# [module]` 註解分組，且 SDK 介面需強制傳入 `module` 參數。
- **Q3：`vscode-support` 與頂層 CLI 是否一併收斂與提供？**
  - **A3（已確認）**：`vscode-support` 一併透過 `contributes` 收斂至 `core.gitignore`（移除 `.vscode/schemas/.gitignore` 子目錄寫法），並提供 `yscb.py gitignore <status|sync>` CLI、SDK 與事件連動。

