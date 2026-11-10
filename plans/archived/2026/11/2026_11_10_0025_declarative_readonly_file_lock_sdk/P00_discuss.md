# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：宣告式受控檔案唯讀鎖定 SDK 與 VFS 透明穿隧防護機制 (declarative_readonly_file_lock_sdk)  
> 建立日期：2026-11-10  
> 所屬主計畫：N/A  
> 狀態：Completed
> 模型：Gemini 3.1 Pro  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 啟動 Tier 1 - 第 1 順位路線圖：`declarative_readonly_file_lock_sdk.md`（遷入為 `roadmap.md`）。
  2. 先將路線圖的五大模組深度調研結果記錄為計畫 `R01`（`R01_declarative_readonly_file_lock_sdk_research.md`），優先另開計畫處理 `ast status` / Server 預熱與 Stage 1 鎖競爭卡死問題（`2026_11_10_0055_ast_server_warmup_and_lock_contention_fix`，已驗收結案）。
  3. 針對 `core.file_lock` 需求面進行定案確認並反哺回 `P00_discuss.md` 與 `R01_declarative_readonly_file_lock_sdk_research.md`：
     - **決策 1**：宣告機制 100% 統一為純 `spaces.readonly`（對齊 `spaces.gitignore` 與 `on_register_file_spaces` 動態空間合成機制，不額外於 `contributes/_format.json` 新增頂層 `readonly_files` 欄位，亦不另建 `file_lock_dynamic.json`）。
     - **決策 2**：`dev` 模組之發布與版本描述檔（`module.release://*/index.json`、`module.release://*/*.zip`、`module.source://*/manifest.json` 與 `yscb.config.json`）暫不納入本期鎖定，留待 `declarative_dev_changeset_and_auto_bump` 計畫由 `dev` 模組統一管理管線時一併掛載。
     - **決策 3**：`agents-workflow` 除鎖定 `workflow.plans://**/changelog.md`、`workflow.roadmap://TODO.md` 及動態投射之 `.agents/.yscb/**` 與受管 `published_files` 外，一併納入全倉盤點確認之 **候選一（`workflow.archived://**` 歷史歸檔計畫庫）** 與 **`core` 候選二（`snapshot://` 環境回滾快照）**。
     - **決策 4（強制 `P06` 靶向深度審計融斷守門）**：嚴禁從 `P06` 直接一路進入 `P07`；於 `auto` `P06` 斷點時，**必須以 `@codebase-deep-auditor` 九維度標準（`C1~C9` / `A1~A5` / `D1~D5` 與 Linux/Windows/macOS 三平台相容性）及 `@yscb-async-deep-audit` 三軌五步雙盲子代理融斷閉環進行靶向審查（最多 3 輪 `Loop 1 ~ Loop 3`，除非提早滿足 `P0=0, P1=0, P2=0` 且無殘留 `ARCH`/`PERF` 技術債而觸發融斷）**，全數根治並通過 `0 ResourceWarning` 驗證後方可推進 `P07`。
- **核心目標**：
  1. 於 `core` 建立統一之宣告式受控檔案唯讀鎖定 SDK（`core.file_lock`），100% 復用 `SpaceRegistry` 之 `<owner>/readonly` 命名空間與 `/readonly` 自動合成空間（結合靜態 `contributes/core.json` 之 `spaces.readonly` 與 `on_register_file_spaces` 動態註冊），將全託管物化產物、歷史歸檔計畫與 CLI 帳本檔於磁碟靜止態維持作業系統級唯讀（POSIX `0o444`/`0o555`、Windows `FILE_ATTRIBUTE_READONLY`）。
  2. 於 `core.vfs`（`OSBackend` 與 `VFS`）實作寫前透明剝離唯讀、寫後依 `/readonly` 空間規則自動重鎖（及非受控目標剝離繼承自唯讀來源之唯讀位元），並暴露 `yscb core file-lock <status|sync|lock|unlock> [target] [--json]` 診斷與逃生閥指令群。
  3. 將 `core`、`dev`、`vscode-support`、`agents-workflow`、`gdrive-support` 五大模組中繞過 VFS 直接呼叫 `os.remove`、`os.replace`、`shutil.rmtree`、`shutil.copy2` 之 18 處潛在碰撞點全面收斂至 `vfs` 原語，並確保與 [`R01_declarative_readonly_file_lock_sdk_research.md`](./R01_declarative_readonly_file_lock_sdk_research.md) 完全一致。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 100% 復用 `core/space/registry.py` 之 `SpaceRegistry` 四階段雙遍編譯管線（Stage 1 `contributes/core.json` `spaces.readonly` $\to$ Stage 3 `on_register_file_spaces` 動態註冊 `<owner>/readonly` $\to$ Pass 2 自動合成 `/readonly` 聯集空間）、`match_path(path, "/readonly")` $O(1)$ 預編譯規則匹配（`CompiledRuleSet`）及 `iter_space_files("/readonly")` 剪枝走訪。
  - 直接復用 `core/context.py` 之 `RuntimeContext` 儲存執行緒局部 `writable_scope` 重入計數，100% 符合 `dev check` 之 `C8` 規範。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁鎖定任何父目錄（目錄恆維持 `0o755`），僅鎖定受控檔案本身，且跳過符號連結 (`os.path.islink`)。
  - 嚴禁鎖定與使用者或 IDE 共管之軟合併檔案（如 `AGENTS.md`、`CLAUDE.md`、`.github/copilot-instructions.md`、`.vscode/settings.json`、`.vscode/extensions.json`、`.gitignore`、`README.md`、`config://**`、`config.local://**`）與使用者自建之非受管 Skill。
  - 明確排除 `.storage.local/` 與 `.cache/` 下之高頻執行期狀態/二進位索引，以及宿主根目錄 `yscb.py` 單檔啟動器。
  - `dev` 發布相關檔案（`module.release://*/index.json`、`manifest.json` 等）留待 `declarative_dev_changeset_and_auto_bump` 計畫一併納管。
- **架構影響範圍**：
  - `ys_codebase/source/core/`（新增 `core/file_lock.py`，更新 `core/context.py`、`contributes/core.json`、`core/space/registry.py`、`core/vfs/os_backend.py`、`core/vfs/vfs.py`、`core/engine.py`、`core/installer.py`、`scripts/cli.py`、`core/__init__.py`）
  - `ys_codebase/source/dev/`（`dev/builder.py`、`dev/testing/sandbox.py` VFS 穿隧相容修繕）
  - `ys_codebase/source/vscode-support/`（`contributes/core.json` 新增 `spaces.readonly`、`vscode_support/schema_compiler.py`）
  - `ys_codebase/source/agents-workflow/`（`contributes/core.json` 新增靜態 `spaces.readonly`、`scripts/hook.core.py` 擴充動態 `agents-workflow/readonly` 註冊、`agents_workflow/publisher.py`、`agents_workflow/plans/archiver.py`）
  - `ys_codebase/source/gdrive-support/`（`gdrive_support/transport.py`、`gdrive_support/sandbox_transport.py`、`gdrive_support/coordinator.py`）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 靜止態檔案級唯讀與目錄免鎖不變量**：
  - 僅對受控檔案本身剝除寫入位元（POSIX `mode & ~0o222`，一般檔 `0o444`、具執行位元檔保留 `0o555`；Windows 設定 `stat.S_IREAD`），父目錄維持 `0o755`，確保同目錄 `.tmp` 建立與 `os.replace` 原子替換零阻礙。
- **[P00:DR-02] 宣告機制統一為純 `spaces.readonly`（對齊 `spaces.gitignore`）**：
  - 不在 `contributes/_format.json` 新增頂層 `readonly_files` 欄位，亦不建立獨立 `file_lock_dynamic.json` 狀態檔；統一透過 `contributes/core.json` 之 `spaces.readonly`（靜態規則）與 `on_register_file_spaces` 事件呼叫 `registry.register_space("<owner>/readonly", ...)`（動態規則）匯入 `SpaceRegistry`，由 Pass 2 自動合成全域 `/readonly` 空間。
- **[P00:DR-03] 本期納入鎖定之三大模組受控清單與 `dev` 管線延後決策**：
  - **`core/readonly`**：鎖定 `module://`（排除 `__pycache__`, `*.pyc`, `*.pyo`, `*.pyd`）、`module.mirror://` 與 **候選二 `snapshot://`**（`yscb://.snapshots/**` 環境回滾快照）。
  - **`vscode-support/readonly`**：鎖定 `project://.vscode/schemas/**`。
  - **`agents-workflow/readonly`**：靜態鎖定 `workflow.plans://**/changelog.md`、`workflow.roadmap://TODO.md` 與 **候選一 `workflow.archived://**`**（`plans/archived/**` 歷史歸檔計畫庫）；動態由 `hook.core.py:on_register_file_spaces` 根據 `ReleasePublisher.collect_readonly_patterns()` 鎖定 `.agents/.yscb/**` 與 `release_manifest*.json` 紀錄之已發布檔案（排除 `AGENTS.md`、`CLAUDE.md` 與 `mode="inject"` 軟合併檔）。
  - **`dev` 模組**：`module.release://*/index.json`、`module.release://*/*.zip`、`manifest.json` 與 `yscb.config.json` 留待 Tier 1 下一順位 `declarative_dev_changeset_and_auto_bump` 計畫由 `dev` 統一管理；但本期仍先行完成 `dev/builder.py` 與 `dev/testing/sandbox.py` 之 `vfs` 唯讀穿隧修繕，確保沙盒測試拆解含唯讀檔之模組時 100% 順暢。
- **[P00:DR-04] `P06` 斷點強制執行最多 3 輪雙盲靶向深度審計與融斷閉環（禁止直入 `P07`）**：
  - 本計畫與緊隨其後之 `server_hot_dispatch_worker_race_and_ux_feedback` 均嚴禁於 `P06` 初次測試通過後直接跳入 `P07`；於 `auto` `P06` 斷點時，必須依 `@codebase-deep-auditor`（`C1~C9` 九維度 / `A1~A5` 架構整理 / `D1~D5` 演進技術債 / 三平台相容）與 `@yscb-async-deep-audit`（三軌 `OPT/ARCH` x `PERF` x `AUD` 五步雙盲子代理：Fresh-Eyes 初審 $\to$ Devil's Advocate 反向查證 $\to$ 手術修復 $\to$ VM `0 ResourceWarning` 全量測試與 Checker 驗證）針對所有受改動模組與關聯交互鏈執行靶向深度審查，最多執行 3 輪（`Loop 1 ~ Loop 3`），直至達成提早融斷條件（`P0=0, P1=0, P2=0` 且無待清理之 `ARCH`/`PERF` 項目）後方可進入 `P07` 結案。

---

## 3. 開放議題與確認紀錄

- **[已確認]** 四項核心決策（純 `spaces.readonly` 機制、`dev` 發布描述檔留待 `dev release` 管線計畫一併納管、納入候選一 `workflow.archived://**` 與候選二 `snapshot://`、以及 `P06` 斷點強制執行最多 3 輪 `@codebase-deep-auditor` / `@yscb-async-deep-audit` 靶向深度審計融斷閉環）均已由開發者拍板定案，具備直接進入階段 B 長任務全自動實作之完整條件。
