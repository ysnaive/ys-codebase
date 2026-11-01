# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：core / dev / server 基礎設施韌性、跨分支 cmd_restore 自癒與 Windows 句柄釋放加固  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將 `TODO-03, TODO-07, TODO-11, TODO-12` 打包為 `sub_02` 子計畫，確立 `P00_discuss.md` 後交由子代理以 `/auto` 平行推進。
- **核心目標**：
  1. **跨分支 `cmd_restore` 版本號比對修復 (`TODO-12`)**：
     - 修正 `yscb.py` 與 `ys_codebase/source/core/core/installer.py` 中 `cmd_restore`（及 `_restore_module_package`）的跳過條件：不再僅檢查 `.modules/<name>/manifest.json` 檔案存在即跳過，而是讀取已安裝 `manifest.json` 比對 `installed_ver == ver`；當版本號不符（如跨分支切換或執行期降級/升級後觸發 auto-restore）時，自動執行覆寫還原，根治跨分支 `auto-restore` 死迴圈。
  2. **`pip_manager` `ensure_venv` 與 `_bootstrap_pip` 改拋 `PipInstallError` (`TODO-07`)**：
     - 將 `ys_codebase/source/core/core/pip_manager.py` 中 `ensure_venv` 與 `_bootstrap_pip` 拋出之 `RuntimeError` 統一改為 `PipInstallError`，使 `installer.sync_pip_dependencies` 能一致攔截並降級為 Warning，避免在無 `ensurepip` 的受限環境下連帶阻斷零依賴模組（如 `core`、`agents-workflow`）冷啟動自舉。
  3. **報錯尾端 `[Agent Directive]` 技能路由注入、Windows 安裝前通知 Server 釋放句柄與 `.old_*` 延遲清理及 VFS 註解收斂 (`TODO-11`)**：
     - 於 `ys_codebase/source/core/core/validator.py`（`contributes check` 失敗時）與 `ys_codebase/source/dev/dev/checker.py`（`dev check` 失敗時）報錯輸出尾端注入 `[Agent Directive]`，明確指引 Agent 查閱 `yscb-module-dev` 或對應規範。
     - 於 `installer.py` 執行模組安裝/更新/移除前，若偵測到目標模組含原生擴充或處於 Windows 環境且常駐 Server 正在運行，主動通知或協調釋放 Worker 模組句柄，並於 `engine.py` / `installer.py` 清理 `.old_*` 備份目錄時採用非阻塞容錯延遲回收（若當下仍被鎖定則留待下次啟動/安裝時順手清理，不拋出致命異常中斷安裝）。
     - 清理 `ys_codebase/source/core/core/vfs.py` 中不切實際之 `MemoryBackend` 過時註解，並完成 `TODO-03` 於 `docs/core/README.md` 與 `docs/core/uri_protocols.md` 明確記載 `core.vfs` 為具 `guard.py` 權限守衛之本地實體檔案代理層及遠端快取物化邊界。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改 `core/locale.py`（歸屬 `sub_03`）與 `knowledge-db`（歸屬 `sub_01`）。
- **架構影響範圍**：
  - `yscb.py`、`ys_codebase/source/core/core/{pip_manager.py,installer.py,validator.py,engine.py,vfs.py}`、`ys_codebase/source/dev/dev/checker.py`、`ys_codebase/source/{core,dev}/tests/` 與 `docs/core/{README.md,uri_protocols.md}`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** **`cmd_restore` 精確版號比對契約**：在 `yscb.py` 與 `installer.py` 檢查已安裝模組時，讀取 `manifest.json` 的 `"version"` 欄位與 `yscb.config.json` 鎖定之目標 `ver` 比對（若目標為 `@build` 或版號完全一致才跳過，否則強制由 `.mirror/` 重新解壓覆寫）。
- **[P00:DR-02]** **Windows `.old_*` 非阻塞延遲清理與 Server 句柄釋放**：在 `engine.py` / `installer.py` 替換模組目錄時，先嘗試清除歷史遺留之 `.old_*`；對本次替換產生之 `.old_*` 若因 Windows 檔案鎖定導致 `shutil.rmtree` 拋出 `OSError`，捕獲並忽略以確保主安裝交易成功，待後續操作再行回收。
- **[P00:DR-03]** **`PipInstallError` 異常繼承與降級**：`ensure_venv` 與 `_bootstrap_pip` 統一拋出 `PipInstallError`，對齊 `sync_pip_dependencies` 的 `except PipInstallError` 容錯邊界。

---

## 3. 開放議題與確認紀錄

- 全數為確定性修復項目，已獲開發者確認直接交由子代理以 `/auto` 推進。

