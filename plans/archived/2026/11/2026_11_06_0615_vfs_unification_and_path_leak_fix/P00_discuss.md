# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：跨模組路徑洩漏根治、背景執行緒 URI 上下文固化與 VFS 原子寫入收口  
> 建立日期：2026-11-06  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 「檢查一下我發現下游使用在 project 目錄產出 .cache/file-space，是不是有路徑洩漏？」
  2. 「等等，為什麼不能統一用 core.vfs ?」
  3. 「先對其他也有寫檔行為的模組做一次完整檢查，產出問題清單」
  4. 「直接立項修復 A + B + C 全數問題，但我已經推送，因此你先修復問題就好」
- **核心目標**：
  1. **根治路徑洩漏（Category A）**：徹底拔除 `file-space`、`ast`、`knowledge-db`、`agents-workflow` 中所有繞過 `core.uri` / `core.vfs` 或在退避（Fallback）時硬編碼 `project_root / ".cache/..."`、`project_root / ".storage.local/..."`、`project_root / "ys_codebase/..."`、`project_root / ".modules/..."` 之行為，確保下游專案 `project://` 業務根目錄 100% 零污染。
  2. **固化背景執行緒 URI 上下文（Category B）**：於 `server` 模組 `WarmWorker.__init__()` / `pre_warm()` 啟動背景服務（`file-space-watcher`、`knowledge-db-worker`、`gdrive-sync`）前，預先將 `YSCB_ROOT_DIR` 與 `YSCB_HOST_DIR` 寫入 `os.environ`，消除背景子執行緒因 `threading.local()` (`_URI_TLS`) 為空而解析失敗並跌入退避分支的根因。
  3. **統一收口至 `core.vfs` 原子寫入（Category C）**：將 `file-space`、`ast`、`knowledge-db`、`agents-workflow` 中自造之 `.tmp` + `os.replace` 原子寫入輔助函式統一委派至 `core.vfs`（`write_bytes` / `write_text` / `write_json(..., atomic=True)`），消除跨模組重複造輪子。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 全面復用 `core.uri.resolve()`、`core.uri.resolve_yscb_root()` 與 `core.vfs`（`read_json`、`write_json`、`write_text`、`write_bytes`、`remove`、`is_file`、`is_dir`）作為全生態系唯一路徑解析與原子讀寫 SSOT。
- **邊界排除 (Explicitly Excluded)**：
  - **不包含版本號遞增 (`dev bump-*`)、正式打包 (`dev release`)、Git Commit / Tag 變更或 Google Drive 同步**：使用者已明確指示「但我已經推送，因此你先修復問題就好」，故僅執行源碼修復、沙盒測試與 `@build` 本機熱部署驗證，絕不觸碰 `release/` 或 Git 遠端同步。
- **架構影響範圍**：
  - `ys_codebase/source/file-space/` (`service.py`, `scanner.py`, `manager.py`, `tests/`)
  - `ys_codebase/source/server/` (`worker.py`, `tests/`)
  - `ys_codebase/source/ast/` (`bundler.py`, `engine.py`, `tests/`)
  - `ys_codebase/source/knowledge-db/` (`pipeline.py`, `config.py`, `service.py`, `tests/`)
  - `ys_codebase/source/agents-workflow/` (`compiler.py`, `publisher.py`, `roadmap.py`, `plans/verifier.py`, `plans/session_trace.py`, `plans/_verifier_healer.py`, `tests/`)

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 語意 URI 優先與 `uri.resolve_yscb_root()` 保底退避鐵律**：
  - 所有內部快取 (`cache://` / `<mod>.cache://`)、本機持久儲存 (`storage.local://` / `<mod>.storage://`)、模組安裝空間 (`module://`) 與設定空間 (`config://` / `config.local://`) 一律優先透過 `core.vfs` / `core.uri.resolve(..., interactive=False)` 解析；當無 `yscb.config.json` 之純單元測試環境觸發退避時，強制以 `core.uri.resolve_yscb_root()` 推導 `<yscb_root>/.cache/<mod>` 或 `<yscb_root>/.storage.local/<mod>`，**嚴禁拼接 `project_root` 或 `Path.cwd()`**。
- **[P00:DR-02] `file-space` Watcher 狀態與活性探針支援顯式 `storage_root` / `state_file` 沙盒隔離**：
  - `FileSpaceWatcherServiceWorker._resolve_watcher_state_path()` 與 `scanner._read_watcher_state_file()` 優先使用 `core.uri.resolve("file-space.cache://watcher_state.json")`（寫於 `<yscb_root>/.cache/file-space/watcher_state.json`）；若於單元測試沙盒中顯式傳入自訂 `storage_root`（不在 `.storage.local` 下）或 `context["state_file"]`，則支援以該隔離沙盒目錄讀取/寫入，絕不觸碰 `project_root / ".cache"`。
- **[P00:DR-03] `WarmWorker` 啟動期環境變數錨定**：
  - `WarmWorker.__init__()` 初始化時即計算 `yscb_root` 與對應 `host_dir`（含 `yscb.config.json` 之宿主目錄），並寫入 `os.environ["YSCB_ROOT_DIR"]` 與 `os.environ[GUARD_ENV_HOST]`，確保 `pre_warm()` 啟動之所有背景 Daemon 執行緒跨執行緒呼叫 `core.uri.resolve()` 時 100% 命中正確宿主與工具庫根目錄。
- **[P00:DR-04] 原子寫入統一委派 `core.vfs`**：
  - `file-space` (`_atomic_write_bytes`)、`ast` (`_atomic_write_meta`)、`knowledge-db` (`write_worker_state`) 與 `agents-workflow` (`compiler._write_cache_file`、`publisher._write_text_atomic`、`roadmap._atomic_write_text`、`_verifier_healer._atomic_write_text`) 全面委派至 `core.vfs.write_bytes` / `write_text` / `write_json(..., atomic=True)`。

---

## 3. 開放議題與確認紀錄

- 開發者已於對話中確認：「直接立項修復 A + B + C 全數問題，但我已經推送，因此你先修復問題就好」。無待決開放議題。
