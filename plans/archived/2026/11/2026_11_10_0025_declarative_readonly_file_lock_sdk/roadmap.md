# 技術路線圖：宣告式受控檔案唯讀鎖定 SDK 與 VFS 透明穿隧防護機制 (Roadmap)

> 主題：宣告式受控檔案唯讀鎖定 SDK 與 VFS 透明穿隧防護機制 (`declarative_readonly_file_lock_sdk`)  
> 歸檔日期：2026-11-05  
> 狀態：Completed
> 目標範疇：`core` (`file_lock` / `vfs` / `space`) 與各模組 CLI 受控資產（物化產物、歷史歸檔與帳本檔）之作業系統級唯讀保護  
> 前置解鎖條件：[Tier 1 - 排序 #1] 已透過 `roadmap promote` 啟動立項（作為後續 `declarative_dev_changeset_and_auto_bump` 鎖定 `manifest.json`/`index.json` 與物化目錄防護之底層基石；已吸收 `git-support` 受保護檔案防誤改需求）  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **純提示詞自律無法物理阻斷對受控資產之誤改**：隨著生態系演進，專案中由 CLI 專責編譯、聚合或維護之全託管檔案持續增加，涵蓋二層物化產物（如 `.agents/`、`.modules/`、`.mirror/`、`.snapshots/`、`.vscode/schemas/`）與結構化帳本/凍結歸檔（如 `plans/*/changelog.md`、`plans/archived/**`、`plans/roadmap/TODO.md`）。然而該類檔案在作業系統層面仍維持一般可寫權限（`0o644`），一旦 AI 代理於長對話上下文壓縮後遺忘規範並直接調用宿主寫檔工具，或人類開發者於編輯器中誤觸修改，極易造成結構損毀、校驗失效或於下次 CLI 執行時遭無預警覆寫。
  - **缺乏統一且正交之檔案權限治理基座**：若由各模組各自散落實作 `os.chmod` 權限切換，將導致跨平台相容性（POSIX 權限位元 vs Windows 唯讀屬性）、跨分支同步（如 Git 檢出與雲端雙向同步落盤）及異常中斷時的權限恢復邏輯高度重複且難以維護。
- **長期願景與目標定位**：
  - 於 `core` 微內核建立統一之**宣告式受控檔案唯讀鎖定 SDK（`core.file_lock`）**，100% 對齊 `spaces.gitignore` 範式，結合 `contributes/core.json` 之 `spaces.readonly` 擴充空間、`on_register_file_spaces` 動態空間註冊與 `core.vfs` 寫入管線透明穿隧，將所有 CLI 受控資產平時恆定維持於**作業系統級唯讀狀態（`0o444`/`0o555` / Read-Only）**，從物理層面攔截外部工具或人工之非授權直接覆寫，同時確保透過官方 CLI 與 VFS 進行之受控更新 100% 無感順暢。
- **範疇與邊界約束**：
  - 涵蓋 `core` 受控唯讀鎖定 SDK、`spaces.readonly` 宣告契約（由 `SpaceRegistry` 合成為 `/readonly`）、`core.vfs` 寫前解鎖與寫後自動重鎖整合、全域逃生閥 CLI 指令（`yscb core file-lock <status|sync|lock|unlock>`），以及 `core`（`module://`, `module.mirror://`, `snapshot://`）、`agents-workflow`（`workflow.plans://**/changelog.md`, `workflow.archived://**`, `workflow.roadmap://TODO.md` 及動態 `.agents/` 受管資產）、`vscode-support`（`project://.vscode/schemas/**`）之受管路徑掛載與 `dev`、`gdrive-support` 之 VFS 穿隧相容修繕。
  - `dev` 模組之發布與版本描述檔（`module.release://*/index.json`、`manifest.json`、`yscb.config.json`）留待 `declarative_dev_changeset_and_auto_bump` 管線計畫由 `dev` 模組統一納管。
  - 僅鎖定檔案本身（`0o444`/`0o555`）而不鎖定父目錄（維持 `0o755`），確保同目錄臨時檔原子替換（`os.replace`）與 Git 分支切換不受阻礙。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **靜止態預設唯讀不變量 (Read-Only at Rest)**：凡經模組透過靜態 `spaces.readonly` 或 `on_register_file_spaces` 動態註冊納入 `/readonly` 空間範圍之全託管檔案，於磁碟靜止狀態下一律強制剝除寫入位元（設為 `0o444`，若原具執行位元則保留為 `0o555`），使任何繞過 YSCB VFS 之外部直接寫入（如宿主 `edit_file`/`write_file` 或 IDE 手動存檔）直接由作業系統以 `PermissionError` 剛性攔截。
  - **VFS 受控寫入透明穿隧不變量 (Transparent VFS Tunneling)**：模組內部透過 `core.vfs`（`write_text`、`write_json`、`atomic_write`、`robust_replace`、`copy`、`move`）或專用受控寫入上下文（`writable_scope`）更新受保護檔案時，底層自動處理既有目標檔之唯讀剝離、同目錄暫存檔原子替換，並於收尾階段自動將新落盤檔案重新鎖回 `0o444`/`0o555` 唯讀狀態，業務層零樣板代碼負擔。
  - **純 `spaces.readonly` 宣告式正交歸屬不變量 (Pure `spaces.readonly` Ownership)**：微內核不硬編碼特定業務模組之檔案路徑，亦不另立冗餘 Schema 欄位；各模組統一透過 `contributes/core.json` 之 `spaces.readonly`（及 `on_register_file_spaces` 動態註冊 `<owner>/readonly`）自主宣告其管轄之唯讀語意 URI 或 Glob 模式，由 `SpaceRegistry` 統一編譯合成為 `/readonly`。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **跨平台檔案唯讀鎖定 SDK (`core.file_lock`)**：提供 `is_protected(uri_or_path)`、`inspect_path(uri_or_path)`、`lock_path(target)`、`unlock_path(target)`、`writable_scope(uri_or_path)` 與全倉批量校驗/上鎖 `sync()` 等核心原語，底層直接委派 `SpaceRegistry.match_path(path, "/readonly")` 與 `iter_space_files("/readonly")`。
  - **VFS 與雲端同步無縫協同（防 Windows `WinError 5` 唯讀替換陷阱）**：於 `OSBackend` 寫入、替換與複製收尾階段掛載受控路徑檢核，命中時自動執行重鎖（非受控目標則強制剝離來源繼承之唯讀位元）；同時將 `core`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 五大模組共 18 處原生 `os.replace` / `os.remove` / `shutil.rmtree` / `shutil.copy2` 統一改經由 `core.vfs` 穿隧，徹底杜絕 Windows 下遭遇唯讀檔拋出 `PermissionError`。
  - **開發者逃生閥與狀態診斷 CLI**：提供標準 CLI 指令 `yscb core file-lock <status|sync|lock|unlock> [target] [--json]`，供開發者於特殊除錯或手動維護情境下檢視受保護檔案狀態、一鍵暫時解鎖指定檔案或全倉重新上鎖。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：**[Tier 1 - 排序 #1（第一優先基石）]** 已完成 `R01` 五大模組深度調研與 `2026_11_10_0055_ast_server_warmup_and_lock_contention_fix` 前置阻塞排除，立即進入階段 B 全自動實作。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（`core.file_lock` SDK、`SpaceRegistry` `/readonly` 合成與 `OSBackend` 透明穿隧）**：於 `core` 實作跨平台唯讀鎖定 SDK、`SpaceRegistry` `readonly` 非折疊萬用字元合成與 `OSBackend`/`VFS` 寫前解鎖、寫後重鎖及 `core/engine.py`、`core/installer.py` VFS 收斂。
  2. **Stage 2（全生態系模組 `spaces.readonly` 掛載與五大模組 VFS 穿隧修繕）**：於 `core`（`module://`, `module.mirror://`, `snapshot://`）、`vscode-support`（`project://.vscode/schemas/**`）與 `agents-workflow`（`workflow.plans://**/changelog.md`, `workflow.archived://**`, `workflow.roadmap://TODO.md` 及動態 `.agents/` 受管產物）完成宣告掛載，並同步完成 `dev`、`gdrive-support` 等模組之 VFS 穿隧相容改造。
  3. **Stage 3（CLI 診斷/逃生閥指令與全倉回歸測試）**：暴露 `yscb core file-lock <status|sync|lock|unlock>` CLI，並於沙盒測試驗證外部直寫攔截、VFS 透明更新與跨模組回歸測試 100% 通過。
