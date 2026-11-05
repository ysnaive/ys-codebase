# 技術路線圖：宣告式受控檔案唯讀鎖定 SDK 與 VFS 透明穿隧防護機制 (Roadmap)

> 主題：宣告式受控檔案唯讀鎖定 SDK 與 VFS 透明穿隧防護機制  
> 歸檔日期：2026-11-05  
> 狀態：Proposed  
> 目標範疇：core (file_lock / vfs) 與各模組 CLI 受控資產（物化產物與帳本檔）之作業系統級唯讀保護  
> 前置解鎖條件：無  
> 模型：Gemini 4 Argon (Medium)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **純提示詞自律無法物理阻斷對受控資產之誤改**：隨著生態系演進，專案中由 CLI 專責編譯、聚合或維護之全託管檔案持續增加，涵蓋二層物化產物（如 `.agents/`、`.modules/`、`.mirror/`、`.vscode/schemas/`）與結構化帳本檔（如 `release/*/index.json`、`plans/*/changelog.md`、`plans/roadmap/TODO.md`）。然而該類檔案在作業系統層面仍維持一般可寫權限（`0o644`），一旦 AI 代理於長對話上下文壓縮後遺忘規範並直接調用宿主寫檔工具，或人類開發者於編輯器中誤觸修改，極易造成結構損毀、校驗失效或於下次 CLI 執行時遭無預警覆寫。
  - **缺乏統一且正交之檔案權限治理基座**：若由各模組各自散落實作 `os.chmod` 權限切換，將導致跨平台相容性（POSIX 權限位元 vs Windows 唯讀屬性）、跨分支同步（如 Git 檢出與雲端雙向同步落盤）及異常中斷時的權限恢復邏輯高度重複且難以維護。
- **長期願景與目標定位**：
  - 於 `core` 微內核建立統一之**宣告式受控檔案唯讀鎖定 SDK（如 `core.file_lock` / `core.file_guard`）**，結合 `contributes` 擴充點與 `core.vfs` 寫入管線透明穿隧，將所有 CLI 受控資產平時恆定維持於**作業系統級唯讀狀態（`0o444` / Read-Only）**，從物理層面攔截外部工具或人工之非授權直接覆寫，同時確保透過官方 CLI 與 VFS 進行之受控更新 100% 無感順暢。
- **範疇與邊界約束**：
  - 涵蓋 `core` 受控唯讀鎖定 SDK、`contributes/core.json` 宣告契約、`core.vfs` 寫入後自動重鎖整合、全域逃生閥 CLI 指令，以及 `dev`、`agents-workflow`、`vscode-support`、`gdrive-support` 等模組之受管路徑掛載；僅鎖定檔案本身（`0o444`）而不鎖定父目錄（維持 `0o755`），確保同目錄臨時檔原子替換（`os.replace`）與 Git 分支切換不受阻礙。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **靜止態預設唯讀不變量 (Read-Only at Rest)**：凡經模組透過靜態擴充點或動態註冊納入受控範圍之全託管檔案，於磁碟靜止狀態下一律強制剝除寫入位元（設為 `0o444`，若原具執行位元則保留為 `0o555`），使任何繞過 YSCB VFS 之外部直接寫入（如宿主 `edit_file`/`write_file` 或 IDE 手動存檔）直接由作業系統以 `PermissionError` 剛性攔截。
  - **VFS 受控寫入透明穿隧不變量 (Transparent VFS Tunneling)**：模組內部透過 `core.vfs`（`write_text`、`write_json`、`atomic_write`）或專用受控寫入上下文（`writable_scope`）更新受保護檔案時，底層自動處理既有目標檔之唯讀剝離、同目錄暫存檔原子替換，並於 `finally` 收尾階段自動將新落盤檔案重新鎖回 `0o444` 唯讀狀態，業務層零樣板代碼負擔。
  - **宣告式正交歸屬不變量 (Declarative Ownership via Contributes)**：微內核不硬編碼特定業務模組之檔案路徑；各模組透過 `contributes/core.json`（及動態註冊介面）自主宣告其管轄之唯讀語意 URI 或 Glob 模式（涵蓋編譯產物與 `index.json`、`changelog.md`、`TODO.md` 等 CLI 帳本檔）。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **跨平台檔案唯讀鎖定 SDK (`core.file_lock`)**：提供 `is_protected(uri_or_path)`、`lock_path(uri_or_path)`、`unlock_path(uri_or_path)`、`writable_scope(uri_or_path)` 與全倉批量校驗/上鎖 `sync_all()` 等核心原語，內建語意 URI 展開、Glob 模式匹配（含記憶體快取）及跨平台權限控制（POSIX `stat.S_IREAD` 與 Windows `FILE_ATTRIBUTE_READONLY`）。
  - **VFS 與雲端同步無縫協同**：於 `OSBackend` 寫入與複製收尾階段掛載受控路徑檢核，命中時自動執行 `lock_path`；同時確保 `gdrive-support` 拉取遠端變更落盤時亦經由受控寫入通道平滑更新並維持落盤後唯讀。
  - **開發者逃生閥與狀態診斷 CLI**：提供標準 CLI 指令（如 `yscb file-lock <status|sync|unlock|lock>`），供開發者於特殊除錯或手動維護情境下檢視受保護檔案狀態、一鍵暫時解鎖指定檔案或全倉重新上鎖。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：無硬性前置阻塞，隨時可透過 `roadmap promote` 立項實作。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（`core.file_lock` SDK 與 `contributes` Schema 建立）**：於 `core` 實作跨平台唯讀鎖定 SDK、動態註冊表、`contributes/core.json` 擴充點（支援語意 URI 與萬用字元模式）及 `OSBackend` 透明自動上鎖整合。
  2. **Stage 2（全生態系模組受控資產與帳本掛載）**：於 `core`（`module://`, `module.mirror://`）、`dev`（`module.release://*/index.json`）、`agents-workflow`（`.agents/**`, `workflow.plans://**/changelog.md`, `workflow.roadmap://TODO.md`）與 `vscode-support`（`project://.vscode/schemas/`）完成宣告掛載與雲端同步相容性驗證。
  3. **Stage 3（CLI 診斷/逃生閥指令與全倉回歸測試）**：暴露狀態檢視與手動解鎖/上鎖 CLI，並於沙盒測試驗證外部直寫攔截與 VFS 透明更新行為。

