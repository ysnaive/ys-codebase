# 技術路線圖：宣告式開發期變更集、自動版號折疊與有界可溯源發布管線治理 (Roadmap)

> 主題：宣告式開發期變更集、自動版號折疊與有界可溯源發布管線治理 (`declarative_dev_changeset_and_auto_bump`)  
> 歸檔日期：2026-11-07  
> 狀態：Ready  
> 目標範疇：`dev` / `core` / `agents-workflow` 模組版本生命週期治理、開發期 `.changes/*.json` 變更登記、發布期自動版號折疊、`git_tree_sha` 二維度有界滑動視窗與 `constraints.txt` 依賴鎖定  
> 前置解鎖條件：[Tier 1 - 排序 #3] 緊隨 Tier 1 - #1 (`jupyter_style_runtime_isolation_and_static_guardrails`) 與 Tier 1 - #2 (`declarative_readonly_file_lock_sdk`) 後啟動  
> 模型：Gemini 3.1 Pro  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **上下文壓縮與多輪迭代下之版號失控遞增**：現行機制中，開發期與發布期共用模組 `manifest.json` 之版本欄位，且工作流提示詞中包含版號遞增說明。當 AI 代理歷經長對話上下文壓縮（Context Compaction）或跨多個子計畫連續開發時，極易因慣性在未獲發布授權下自行反覆遞增版號，導致單次發布週期內出現多次無效跳號。
  - **多人與跨環境並行開發之版本欄位衝突及脈絡遺失**：多名開發者或本地與雲端代理同時修改同一模組時，直接修改 `manifest.json` 的版本號與單一 `release` 欄位極易在合併時引發衝突與變更摘要互蓋；而延遲發布時亦難以完整回溯所有中間 `@build` 修改的語意類型與緊急度。
  - **跨版本三元組之二進位發布包與本地建置快取無界累積**：雖然發布分支已採孤立提交（Orphan Commit）隔離歷史被淘汰的修訂版（Revision），但若跨語意版本三元組（`Major.Minor.Patch`）皆無限期保留二進位壓縮包，長期高頻迭代下二進位檔案總數仍將隨三元組數量線性增長；同時本機 `.build/` 與 `.mirror/` 快取亦缺乏自動滑動修剪機制。
  - **生產環境可重現安裝缺乏統一依賴鎖定檔（`TODO-01`）**：現行模組宣告寬鬆相依區間（如 `>=0.12.0`），缺乏由發布管線統一匯出之根目錄 `constraints.txt` 供 CI 與離線生產環境鎖定可重現版本。
- **長期願景與目標定位**：
  1. **開發期與發布期徹底物理分離**：日常開發完全移除手動或指令式遞增版號的行為，改以獨立碎片檔（`<mod>/.changes/<id>.json`）增量登記變更意圖；正式發布時由 `yscb dev release` 自動讀取、確定性折疊計算最終版號、聚合發布元數據並一次性寫入 `manifest.json` 與 `release/<mod>/index.json`。
  2. **熱快取有界滑動視窗（$O(1)$ 常數空間上限）+ 冷歷史 Git 確定性溯源重建（100% 位元級無損重現）**：確保遠端發布分支與本機快取空間永久封頂於極小常數規模，同時在 `index.json` 記錄 `git_tree_sha` 與打包格式版本，賦予任意歷史 `pruned` 版本隨時從主分支 Git 歷史一鍵精確重建並驗證 SHA-256 的能力。
  3. **統一發布管線閉環**：在同一趟 `dev/releaser.py` 改造中一併落地 `constraints.txt` 自動匯出與校驗（收編 `TODO-01`）。
- **已整併吸收之原獨立路線圖與待辦事項**：
  - **正式整併吸收原 `git_traceable_bounded_release_window.md`**：將 `git_tree_sha` 溯源錨點、二維度有界滑動視窗（同三元組 $N$ 個 $\times$ 跨三元組 $K$ 個）、歷史包按需確定性重建與本地 `.build/` / `.mirror/` 修剪完整併入本路線圖。
  - **正式收編 `TODO-01`（生產環境 `constraints.txt` 依賴鎖定與打包校驗）**。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **開發期版號凍結與多源增量無衝突不變量（Development-Time Version Immutability & Additive Accumulation）**：在日常功能開發、測試與 `@build` 熱部署期間，`manifest.json` 中的正式版號維持凍結（並由 `core.file_lock` 施加 OS 級 `0o444` 唯讀鎖保護）；開發者與代理僅於 `<mod>/.changes/<id>.json` 增量追加變更紀錄，各筆紀錄彼此獨立、跨分支 100% 零合併衝突。
  - **發布期確定性單次折疊不變量（Deterministic Release-Time Folding）**：無論開發期累積多少筆變更紀錄，執行 `yscb dev release` 時均由腳本自動收斂為**單次版本晉升**（取最高升版幅度：`major` > `minor` > `patch` > `revision` 與最高緊急度：`critical` > `recommended` > `optional`），合併變更摘要寫入 `manifest.json` 與 `index.json` 後自動清空已消費之 `.changes/`。
  - **熱快取空間常數上界不變量（$O(1)$ Bounded Active Window）**：每個模組同時保留之活躍 `.zip` 二進位包數量受雙重上界（同三元組修訂上限 $N \times$ 跨三元組保留上限 $K$）嚴格約束，超出視窗之古老三元組自動轉為 `pruned` 並回收實體二進位包。
  - **源碼樹雙重錨定與可重現封裝不變量（`git_tree_sha` + Versioned Deterministic Packer）**：`index.json` 之 `releases[<ver>]` 永久保留元數據、相依宣告、`.zip` 之 `sha256`、`pack_format_version` 以及該模組源碼目錄之 `git_tree_sha`（Git Tree Object SHA-1）與 Commit 座標；執行 `dev release` 前強制驗證目標模組目錄為 **Clean Worktree**。
  - **消費端無感相容不變量（Transparent Consumer Fallback）**：當下游專案請求已移出熱快取視窗之歷史 `pruned` 版本時，解析引擎具備同 `Major.Minor` 相容版本區間內之自動平滑遞補或按需從 Git 歷史溯源重建能力。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **支柱一：開發期變更集載體（`<mod>/.changes/<id>.json`）與 Fail-Fast 發布預檢**：
    - 提供 `yscb dev change add <mod>` 寫入獨立變更碎片檔（記錄 `bump`、`type`、`urgency`、`summary`），打包正式 `.zip` 時自動排除 `.changes/`。
    - 當模組處於 `@build` 或源碼較上版有異動但 `.changes/` 為空時，`yscb dev release-check` 明確 Fail-Fast 阻斷並提示補登變更摘要，並同步移除日常開發技能手冊中直接改版號之提示詞（Prompt De-Versioning）。
  - **支柱二：發布期自動折疊、拓撲對齊與 `constraints.txt` 鎖定匯出**：
    - `dev release` 掃描所有含待消費變更集之模組，依 DAG 相依拓撲順序自動計算目標版號、寫入 `manifest.json` 與 `release/<mod>/index.json`，並自動匯出/校驗全倉外部套件之 `constraints.txt`（完成 `TODO-01`）。
  - **支柱三：二維度有界滑動視窗、`git_tree_sha` 確定性時光機與本機快取修剪**：
    - 發布時自動記錄 `git_tree_sha` 並執行「同三元組 $N$ 個 + 跨三元組 $K$ 個」二維度視窗修剪；提供 `yscb dev release-rebuild <mod> <ver>` 從 Git 歷史提取指定 `git_tree_sha` 重建 `.zip` 並校驗 `sha256`。
    - 對本機 `.build/` 與 `.mirror/` 實施自動容量修剪，並維護母倉遠端 `^refs/heads/releases` 負向 Refspec 排除規則。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 排定為 **Tier 1 - 排序 #3**，緊隨 Tier 1 - #1（`jupyter_style_runtime_isolation_and_static_guardrails`）與 Tier 1 - #2（`declarative_readonly_file_lock_sdk`，提供 `manifest.json` / `index.json` 唯讀鎖與 `dev release` 寫入隧道）完成後啟動。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（`.changes/*.json` 規格、`dev change` CLI 與 `release-check` Fail-Fast 守門）**：建立開發期變更集 Schema 與增量登記介面，並結合 `core.file_lock` 凍結開發期 `manifest.json` 與 `index.json` 手動改寫。
  2. **Stage 2（自動版號折疊、`git_tree_sha` 溯源錨點、二維滑動視窗與按需重建）**：升級 `dev/releaser.py` 實作 DAG 拓撲自動折疊升版、寫入 `git_tree_sha`、執行二維度 `.zip` 滑動視窗淘汰與歷史包按需重建。
  3. **Stage 3（`constraints.txt` 鎖定匯出、本機快取修剪與工作流技能去版號化）**：整合 `constraints.txt` 自動生成與校驗（`TODO-01`）、`.build`/`.mirror` 自動修剪，並更新 `agents-workflow` 技能手冊全面切換至宣告式變更集工作流。
