# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`module:gdrive-support` 模組骨架、組態映射與原子雲端操作 API/SDK (`sub_01_atomic_api_and_sdk`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 作為主計畫 `2026_11_04_0858_gdrive_bidirectional_sync_module` 之首個子計畫 `sub_01_atomic_api_and_sdk`，建立 `module:gdrive-support`（Python package `gdrive_support`，短別名 `gdrive`）模組骨架、組態與 `file-space` / `mapping` 路徑雙向映射（`config.py`）、雙模傳輸基座（`AbstractSyncTransport`、`LocalSandboxTransport`、`GoogleDriveApiTransport`）及獨立原子雲端操作 SDK 與 CLI（`ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`, `auth`, `status`），並確立自動化測試 100% 僅針對本地沙盒（`LocalSandboxTransport`）與組態邏輯撰寫（嚴禁對外 Google Drive API 寫入自動化 test case）。
- **核心目標**：
  1. **建立 `module:gdrive-support` 標準模組骨架與 Contributes 契約**：於 `ys_codebase/source/gdrive-support/` 建立 `manifest.json`、`.yscbignore`、`contributes/{_format.json,_manifest.md,core.json}`、`configurable/{_format.json,config.project.json}`、`gdrive_support/__init__.py` 與 `scripts/cli.py`，註冊模組短別名 `"module_alias": ["gdrive"]` 及 `auto_sync: false` 預設組態。
  2. **實作 `gdrive_support/config.py` 組態解析與空間映射驗證**：解析 `config://gdrive-support/` 與 `contributes` 之 `sync_spaces`；統一將 `FileSpaceManager` 產生之檔案路徑以 `abs_path.relative_to(project_root)` 正規化為 `project_rel_path`；驗證選填 `mapping: [{local, remote}]` 之 `mapping.local` 必須位於該 `space` 的 `include` 根路徑範圍內，並提供最長前綴雙向路徑轉換（`local_to_remote_rel` / `remote_to_local_rel`）。
  3. **實作 `gdrive_support/transport.py` 原子操作 API 基座與雙模傳輸驅動**：
     - 定義 `RemoteEntry` 與 `AbstractSyncTransport` 抽象基類，暴露獨立原子方法：`list_files(remote_path)`、`upload_file(local_path, remote_path, in_place_file_id=None)`、`download_file(remote_path, local_path)`、`trash_file(remote_path)`、`move_file(file_id, old_parent_id, new_parent_id)`、`mkdir(remote_path)`、`create_shortcut(target_id, remote_path)`。
     - 100% 保持原檔案類型（二進位與文字原樣傳輸，`md5` / `sha256` 對齊），不做 Google Workspace 雲端原生線上文件特化匯出轉檔（遇 `application/vnd.google-apps.*` 非 `folder`/`shortcut` 物件標記 `SKIPPED_UNSUPPORTED_MIME` 安全略過）；遇到 Shortcut (`application/vnd.google-apps.shortcut`) 時自動批次解析 `target_file_id` 與目標實體檔之 `(md5Checksum, size, modifiedTime)`。
     - 完整實作 `LocalSandboxTransport`（於本地檔案系統 100% 模擬雲端 `file_id`、`.trash/`、Shortcut JSON 描述檔與目錄結構，供離線沙盒與自動化測試使用）與 `GoogleDriveApiTransport`（純標準庫 `urllib.request` 對接 Google Drive REST API v3、OAuth2 Desktop Loopback 授權與 Service Account 載入、Resumable 上傳與 429 退避）。
  4. **暴露獨立原子 SDK 與 CLI 指令**：提供無須啟動背景服務即可手動調用之 CLI 子命令 `ls`、`get`、`put`、`rm`、`mkdir`、`shortcut`、`auth`、`status`（支援 `--sandbox-dir` 與 `--json`）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `module:file-space` 之 `FileSpaceManager` 解析 `space` 之 `include`/`exclude` 根路徑與檔案列舉。
  - 復用 `core.uri`、`core.vfs`、`core.platform.InterProcessLock` 與 `core.config`。
- **邊界排除 (Explicitly Excluded)**：
  - **測試鐵律**：`tests/` 下的自動化測試案例 **100% 僅測試 `LocalSandboxTransport`、`config.py` 與本地 CLI/SDK 邏輯**，**嚴禁為對外 `GoogleDriveApiTransport` 編寫自動化 test cases**（對外 API 實機驗證歸屬 `sub_03`）。
  - 雲端 `<root_folder_id>` 多分支管理（`init`、`branch`、`checkout`、`.yscb_gdrive.json`、`.history/` Copy-on-Write 與無引用自動回收）、三方對帳演算法（`reconciler.py`）、批次同步（`pull`/`push`/`sync`）與常駐背景服務（`service.py`）歸屬 `sub_02_branch_and_sync_engine`。
  - 零 `.gitignore` 耦合；不做 Google Workspace 原生線上文件特化匯出轉檔。
- **架構影響範圍**：
  - 新建 `ys_codebase/source/gdrive-support/`（`manifest.json`、`contributes/`、`configurable/`、`gdrive_support/{__init__,config,transport}.py`、`scripts/cli.py`、`tests/`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 模組識別符 `gdrive-support`、短別名 `gdrive` 與 `auto_sync: false` 預設組態**：
  - 模組名稱為 `gdrive-support`（套件 `gdrive_support`），於 `contributes/core.json` 宣告 `"module_alias": ["gdrive"]`；`config.json` 預設 `auto_sync: false`，確保安裝後預設作為純粹的手動原子上傳/下載工具運作。
- **[P00:DR-02] `config.py` 之 `file-space` 路徑正規化與 `mapping` 子集邊界校驗**：
  - 統一以 `abs_path.relative_to(project_root)` 正規化空間內檔案相對路徑；當 `sync_spaces` 條目提供 `mapping: [{local, remote}]` 時，強制驗證每個 `mapping.local` 解析後必須位於該 `space` 的 `include` 根目錄之下，否則立即拋出 `GDriveConfigError`。
- **[P00:DR-03] 100% 原檔案類型原子傳輸與 Shortcut 目標 Metadata 解析**：
  - `AbstractSyncTransport` 所有傳輸皆保持原檔案類型與原始位元組；`list_files` / `list_remote` 對 `application/vnd.google-apps.shortcut` 自動解析 `target_file_id` 與目標實體檔 `(md5, size, mtime_ns)`；對其他 `application/vnd.google-apps.*`（非 `folder`/`shortcut`）標記 `SKIPPED_UNSUPPORTED_MIME` 安全略過。
- **[P00:DR-04] 自動化測試 100% 鎖定本地沙盒 (`LocalSandboxTransport`)**：
  - 鑑於無法保證任何開發/測試環境皆具備使用者 Google 雲端金鑰，`tests/` 僅針對 `config.py`、`LocalSandboxTransport` 與 CLI/SDK 原子操作編寫單元與邊界測試；對外 `GoogleDriveApiTransport` 不撰寫自動化 test cases，交由 `sub_03` 執行實機功能驗證與修訂。

---

## 3. 開放議題與確認紀錄

- 子計畫 `sub_01_atomic_api_and_sdk` 需求與邊界已完全承接自主計畫 `P00_discuss.md` 與 `R01_gdrive_architecture_and_design.md`。

