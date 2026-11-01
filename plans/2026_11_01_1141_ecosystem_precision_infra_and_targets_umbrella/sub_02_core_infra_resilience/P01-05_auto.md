# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：core / dev / server 基礎設施韌性、跨分支 cmd_restore 自癒與 Windows 句柄釋放加固  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 跨分支 `cmd_restore` 精確版本號比對與覆寫還原 | 修正 `yscb.py` 與 `ys_codebase/source/core/core/installer.py` 之 `cmd_restore`（含 `_restore_module_package`）：檢查 `.modules/<name>/manifest.json` 存在時，必須讀取其 `"version"` 並與 `yscb.config.json` 鎖定之目標 `ver` 比對；唯有目標為 `@build` 或 `installed_ver == ver` 才跳過，否則強制由 `.mirror/` 執行覆寫還原，根治跨分支 `auto-restore` 死迴圈。 | P0 | [P00:DR-01] |
| **FR-02** | `pip_manager` `ensure_venv` 與 `_bootstrap_pip` 統一拋出 `PipInstallError` | 將 `ys_codebase/source/core/core/pip_manager.py` 中 `ensure_venv` 與 `_bootstrap_pip` 原拋出之 `RuntimeError` 統一改為 `PipInstallError`，使 `installer.sync_pip_dependencies` 能一致攔截並降級為 Warning，不阻斷零依賴模組冷啟動自舉。 | P0 | [P00:DR-03] |
| **FR-03** | 報錯尾端 `[Agent Directive]` 技能路由注入 | 於 `ys_codebase/source/core/core/validator.py`（`contributes check` 失敗時）與 `ys_codebase/source/dev/dev/checker.py`（`dev check` 失敗時）報錯輸出尾端注入 `[Agent Directive]`，明確指引 Agent 查閱 `yscb-module-dev` 技能手冊與規範。 | P0 | [P00:DR-02] |
| **FR-04** | Windows 安裝前主動通知 Server 釋放句柄與 `.old_*` 非阻塞延遲清理 | 於 `installer.py` 執行模組安裝/更新/移除前，主動通知或協調運行中之常駐 Server 釋放 Worker 模組句柄；於 `engine.py` 與 `installer.py` 替換模組目錄時，先嘗試清理歷史遺留之 `.old_*`，對本次替換產生之 `.old_*` 若因 Windows 檔案鎖定導致 `shutil.rmtree` 拋出 `OSError`，捕獲並忽略以確保主安裝交易成功。 | P0 | [P00:DR-02] |
| **FR-05** | `core.vfs` 過時註解清理與本地代理/遠端快取邊界文檔化 | 清理 `ys_codebase/source/core/core/vfs.py` 中不切實際之 `MemoryBackend` 過時註解，並於 `docs/core/README.md` 與 `docs/core/uri_protocols.md` 明確記載 `core.vfs` 為具 `guard.py` 權限守衛之本地實體檔案代理層及未來雲端來源之本地快取物化解析器。 | P1 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 已安裝模組之 `.modules/<name>/manifest.json` 損毀或無法解析 JSON | 視為版本不符 (`installed_ver != ver`)，觸發由 `.mirror/` 重新解壓覆寫修復。 |
| **EC-02** | 受限環境無 `ensurepip` 或建立虛擬環境失敗時執行 `restore` / `install` | `ensure_venv` / `_bootstrap_pip` 拋出 `PipInstallError`，由 `sync_pip_dependencies` 攔截並輸出 `[WARN]`，不中斷零依賴或已具備環境之模組安裝流程。 |
| **EC-03** | Windows 環境下常駐 Server 或外部行程鎖定 `.pyd`/`.dll` 導致 `.old_*` 刪除拋出 `PermissionError` / `OSError` | 安裝前先嘗試通知 Server 停止/重載以釋放句柄；清理 `.old_*` 失敗時靜默容錯（或記錄非致命提示）保留至下次生命周期操作時順手清除，絕不中斷當前安裝交易。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 依賴與相容性 | `core` 維持 100% Python 標準庫零第三方依賴；跨平台（Windows / POSIX）路徑與檔案操作完全相容。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `yscb.py` 為獨立 Bootstrap 腳本，包含精簡版自舉還原邏輯，與 `core/installer.py` 的完整版 `cmd_restore` 必須保持一致的版本比對語意。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[yscb.py / core.installer.cmd_restore]
  ├── 讀取 yscb.config.json (module -> target_ver)
  ├── 檢查 .modules/<name>/manifest.json -> installed_ver
  │     └── 若 target_ver != "@build" 且 installed_ver != target_ver -> 執行覆寫還原
  ├── [Windows Handle Release & .old_* Cleanup]
  │     ├── 變異前嘗試通知常駐 Server 釋放句柄
  │     ├── 預先掃描清理殘留之 .old_* 目錄 (忽略 OSError)
  │     └── 原子替換後清理本次 .old_* (忽略 OSError 延遲回收)
  └── [core.pip_manager]
        └── ensure_venv / _bootstrap_pip 失敗 -> 拋出 PipInstallError -> installer 降級為 WARN
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 修正自舉 `cmd_restore` 檢查已安裝模組 `manifest.json` 的 `version == ver` 比對邏輯 |
| `ys_codebase/source/core/core/installer.py` | Modify | 修正 `_restore_module_package` / `cmd_restore` 版本號比對、安裝前通知 Server 釋放句柄、以及 `.old_*` 非阻塞延遲清理 |
| `ys_codebase/source/core/core/engine.py` | Modify | 加固模組熱替換時對歷史與當下 `.old_*` 目錄之非阻塞容錯清理邏輯 |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | 將 `ensure_venv` 與 `_bootstrap_pip` 拋出之 `RuntimeError` 統一改為 `PipInstallError` |
| `ys_codebase/source/core/core/validator.py` | Modify | 於 `contributes check` 失敗報錯尾端注入 `[Agent Directive]` 技能路由提示 |
| `ys_codebase/source/core/core/vfs/vfs.py` | Modify | 清理過時之 `MemoryBackend` 註解，對齊本地實體代理與權限守衛定位 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | 於 `dev check` 失敗報錯尾端注入 `[Agent Directive]` 技能路由提示 |
| `ys_codebase/source/core/tests/test_installer.py` | Modify | 新增跨分支 `cmd_restore` 版本不符覆寫、損毀 `manifest.json` 覆寫與 Server 句柄釋放通知容錯單元測試 |
| `ys_codebase/source/core/tests/test_venv_core.py` | Modify | 新增 `_bootstrap_pip` 與 `ensure_venv` 拋出 `PipInstallError` 及 `sync_pip_dependencies` 降級 Warning 測試 |
| `ys_codebase/source/core/tests/test_validator.py` | Modify | 驗證 `validator.py` 報錯尾端之 `[Agent Directive]` 輸出 |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 驗證 `checker.py` 報錯尾端之 `[Agent Directive]` 輸出 |
| `docs/core/README.md` | Modify | 記載 `core.vfs` 為具 `guard.py` 權限守衛之本地實體檔案代理層及遠端快取物化邊界 |
| `docs/core/uri_protocols.md` | Modify | 補充 `core.vfs` 本地實體代理定位與未來雲端來源之本地快取物化解析器說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** **雙端 `cmd_restore` 版本比對一致性**：`yscb.py` 與 `core/installer.py` 均採用讀取 `.modules/<name>/manifest.json` 內 `"version"` 與目標 `ver` 比對（`ver == "@build"` 或 `installed_ver == ver` 始跳過），確保冷啟動自舉與一般還原行為一致。
- **[P02:DR-02]** **無侵入式 Server 句柄釋放與 `.old_*` 垃圾回收**：於 `installer.py` 變異模組前檢查是否存在運行中之 Server PID/Socket 並嘗試發送停機/釋放通知（失敗不阻斷）；於 `engine.py` 與 `installer.py` 執行目錄替換時，順手掃除同層級既有 `.old_*` 殘留目錄並對當前 `.old_*` 的 `rmtree` 加上 `OSError` 容錯。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/pip_manager.py
def ensure_venv(self, py_tag: Optional[str] = None) -> str: ...
def _bootstrap_pip(self, venv_dir: str, site_pkg: str, py_exec: str) -> None: ...

# ys_codebase/source/core/core/installer.py
def _notify_server_release_handles(yscb_root: Optional[str] = None) -> bool: ...
def _cleanup_stale_old_dirs(parent_dir: str) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `ensure_venv` 與 `_bootstrap_pip`：當 `venv` 建立失敗或 `ensurepip` 執行失敗時，拋出 `PipInstallError`（繼承自 `YscbError` / `Exception`）。
  - `_cleanup_stale_old_dirs` 與 `.old_*` 刪除：捕獲 `OSError` 並靜默忽略，確保 Windows 句柄鎖定時不拋出未處理例外。
- **階段決策紀錄**：`[P03:DR-01]` 維持既有公開 CLI 與函式簽名相容，僅精煉內部輔助函式與異常型別。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-03 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 指標約束
- **靈魂拷問與防護解法**：若 `.modules/<name>/manifest.json` 存在但內容格式損毀，`json.loads` 將拋出 `Exception`，必須在 `try...except` 中將 `installed_ver` 設為 `None`，從而自動觸發重新解壓覆寫修復。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 明確記載 `core.vfs` 為具 `guard.py` 權限守衛之本地實體檔案代理層與遠端快取邊界 |
| **專題手冊** | `docs/core/uri_protocols.md` | Modify | 定義 `core.vfs` 本地實體檔案代理定位與未來雲端來源之本地快取物化解析器架構 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 既有設計筆記已涵蓋，本次主要同步專題與模組手冊 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 清理 `vfs.py` 過時註解並同步更新 `pip_manager.py` / `installer.py` Docstrings |
| **發布日誌** | `CHANGELOG.md` | Modify | 於主計畫結案時統一記錄發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認無破壞性 API 變更，直接進入實作與測試驗證。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `yscb.py` 與 `core/installer.py` 跨分支 `cmd_restore` 版本號比對修復 (`TODO-12`)
- [x] **TASK-02**：實作 `core/pip_manager.py` 之 `ensure_venv` 與 `_bootstrap_pip` 改拋 `PipInstallError` (`TODO-07`)
- [x] **TASK-03**：實作 `core/validator.py` 與 `dev/checker.py` 報錯尾端 `[Agent Directive]` 注入、Windows Server 句柄釋放通知、`.old_*` 非阻塞延遲清理及 `vfs.py` 註解清理 (`TODO-11`)
- [x] **TASK-04**：編寫與更新 `core` 與 `dev` 單元測試與邊界測試，並通過 `dev check`、`dev test` 與 `@build` 安裝驗證
- [x] **TASK-DOC**：更新 `docs/core/README.md` 與 `docs/core/uri_protocols.md` (`TODO-03`)

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
