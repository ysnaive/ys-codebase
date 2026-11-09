# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：宣告式受控檔案唯讀鎖定 SDK 與 VFS 透明穿隧防護機制 (declarative_readonly_file_lock_sdk)  
> 建立日期：2026-11-10  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 3.1 Pro  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 啟動 Tier 1 - 第 1 順位路線圖：`declarative_readonly_file_lock_sdk.md`（遷入為 `roadmap.md`）。
  2. 先將路線圖的五大模組深度調研結果記錄為計畫 `R01`（`R01_declarative_readonly_file_lock_sdk_research.md`），暫緩進入實作，優先另開計畫處理 `ast status` / Server 預熱與 Stage 1 鎖競爭卡死問題。
- **核心目標**：
  1. 於 `core` 建立統一之宣告式受控檔案唯讀鎖定 SDK（`core.file_lock`），結合 `contributes/core.json`（`spaces.readonly` 與頂層 `readonly_files`）及動態鎖定清單（`cache://core/file_lock_dynamic.json`），將全託管物化產物與 CLI 帳本檔於磁碟靜止態維持作業系統級唯讀（POSIX `0o444`/`0o555`、Windows `FILE_ATTRIBUTE_READONLY`）。
  2. 於 `core.vfs`（`OSBackend` 與 `VFS`）實作寫前透明剝離唯讀、寫後依規則自動重鎖（及非受控目標剝離繼承自唯讀來源之唯讀位元），並暴露 `yscb file-lock <status|sync|lock|unlock> [target] [--json]` 診斷與逃生閥指令群。
  3. 將 `core`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 五大模組中繞過 VFS 直接呼叫 `os.remove`、`os.replace`、`shutil.rmtree`、`shutil.copy2` 之潛在碰撞點全面收斂至 `vfs` 原語，並固化於 [`R01_declarative_readonly_file_lock_sdk_research.md`](./R01_declarative_readonly_file_lock_sdk_research.md)。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接復用 `core/space/schema.py` 之三座標預編譯規則引擎 `CompiledRuleSet`（`matches_fast` 與 `find_matching_rule`）及 `core/space/registry.py` 之 `SpaceRegistry.iter_space_files` 剪枝走訪。
  - 直接復用 `core/context.py` 之 `RuntimeContext` 儲存模組級快取與執行緒局部 `writable_scope` 重入計數，100% 符合 `dev check` 之 `C8` 規範。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁鎖定任何父目錄（目錄恆維持 `0o755`），僅鎖定受控檔案本身，且跳過符號連結 (`os.path.islink`)。
  - 嚴禁鎖定與使用者或 IDE 共管之軟合併檔案（如 `AGENTS.md`、`CLAUDE.md`、`.github/copilot-instructions.md`、`.vscode/settings.json`、`.vscode/extensions.json`）與使用者自建之非受管 Skill。
- **架構影響範圍**：
  - `ys_codebase/source/core/`（新增 `core/file_lock.py`，更新 `core/context.py`、`contributes/_format.json`、`contributes/core.json`、`core/validator.py`、`core/space/registry.py`、`core/vfs/os_backend.py`、`core/vfs/vfs.py`、`core/engine.py`、`core/installer.py`、`core/commands/dispatcher.py`、`scripts/cli.py`、`core/__init__.py`）
  - `ys_codebase/source/dev/`（`contributes/core.json`、`dev/builder.py`、`dev/testing/sandbox.py`）
  - `ys_codebase/source/vscode-support/`（`contributes/core.json`、`vscode_support/schema_compiler.py`）
  - `ys_codebase/source/agents-workflow/`（`contributes/core.json`、`agents_workflow/publisher.py`、`agents_workflow/plans/archiver.py`）
  - `ys_codebase/source/gdrive-support/`（`gdrive_support/transport.py`、`gdrive_support/sandbox_transport.py`、`gdrive_support/coordinator.py`）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 靜止態檔案級唯讀與目錄免鎖不變量**：
  - 僅對受控檔案本身剝除寫入位元（POSIX `mode & ~0o222`，一般檔 `0o444`、具執行位元檔保留 `0o555`；Windows 設定 `stat.S_IREAD`），父目錄維持 `0o755`，確保同目錄 `.tmp` 建立與 `os.replace` 原子替換零阻礙。
- **[P00:DR-02] 靜態 Contributes + 動態清單雙軌註冊機制**：
  - 靜態規則透過 `contributes/_format.json` 新增之頂層 `"readonly_files"` 與 `spaces.readonly` 宣告；動態投射檔案（如 `agents-workflow` 之 `published_files` 扣除 `agents_md_abs_set`）透過 `file_lock.register_dynamic_locks` 持久化於 `cache://core/file_lock_dynamic.json`。
- **[P00:DR-03] 五大模組 VFS 穿隧碰撞點與 SDK 設計先固化為 `R01` 調研報告**：
  - 依開發者指示，將 3 路子代理針對五大模組盤點出之精確行號碰撞矩陣、SDK 介面簽名與三階段實作藍圖完整沉澱至 [`R01_declarative_readonly_file_lock_sdk_research.md`](./R01_declarative_readonly_file_lock_sdk_research.md)（狀態 `Concluded`），待 `ast status` 與 Server 預熱鎖競爭修復計畫完成後再行接續推進本計畫之實作閉環。

---

## 3. 開放議題與確認紀錄

- **[已確認]** 已將五大模組調研成果完整記錄於 [`R01_declarative_readonly_file_lock_sdk_research.md`](./R01_declarative_readonly_file_lock_sdk_research.md)，待優先完成 `2026_11_10_0055_ast_server_warmup_and_lock_contention_fix` 後再行接續實作。
