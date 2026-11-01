# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：發布產物二進位儲存與 Git 歷史瘦身優化調研  
> 建立日期：2026-11-01  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Umbrella  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「接下來看看 roadmap，準備處理陳積已久的 `.zip` 混入 git 歷史問題」
  - 「是，由於陳積已久，先進行詳盡調研」
- **核心目標**：
  - 針對自 2026-08-29（第 100 個 Commit）留存至今（第 237 個 Commit）的 [roadmap.md](./roadmap.md) 進行全方位的現況量化診斷、架構依賴鏈盤點與多方案深水區調研。
  - 釐清若將 `ys_codebase/release/**/*.zip` 從 `main` 分支解耦或清洗 Git 歷史，對現有生態系（`yscb.py` 單檔遠端初始化、`core` 三層套件解析、`dev` 發布守門與沙盒測試）的真實衝擊與最佳架構演進路徑。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `yscb.py`（`DEFAULT_PROVIDER_URL`、`_discover_latest_core`、`_bootstrap_package_from_provider`）
  - `ys_codebase/source/core/core/engine.py`（`AtomicEngine.act_fetch`、`_download_from_release_tier`、`_download_from_remote_tier`、`_find_manifest_in_local_provider`）
  - `ys_codebase/source/core/core/installer.py`（`_discover_available_versions_for_module`、`generate_internal_gitignore`）
  - `ys_codebase/source/dev/dev/builder.py`（`Builder._update_release_index`、`package_release`）
  - `ys_codebase/source/dev/dev/releaser.py`（`Releaser.release_check` Gate 2/3、`release_git`）
- **邊界排除 (Explicitly Excluded)**：
  - **嚴禁在 `sub_01` 與 `sub_02` 代碼改造與測試驗收完成前，擅自修改 `.gitignore`、刪除 `ys_codebase/release/*.zip` 或執行 `git filter-repo` 改寫 Git 歷史**。
- **架構影響範圍**：
  - `yscb.py`、`core` (`engine.py`, `installer.py`, `update_checker.py`)、`dev` (`builder.py`, `releaser.py`, `checker.py`)、`.gitignore` 與 Git 倉庫分支/歷史結構。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 先行展開全庫物件量化與供應鏈耦合點調研（`R01`）**：
  - 鑑於此問題橫跨「Git 倉庫物理體積」、「遠端無伺服器 HTTP Provider (`raw.githubusercontent.com`) 分發契約」與「本地母倉 Dogfooding (`default_provider: ./ys_codebase/release`)」三大維度，先行產出詳盡調研報告 [`R01_release_binary_and_git_history_analysis.md`](./R01_release_binary_and_git_history_analysis.md)，量化第 100 Commit 至第 237 Commit 的膨脹趨勢，並解剖所有依賴 `.zip` 實體檔的代碼路徑與候選解耦方案。
- **[P00:DR-02] 升格為增量演進型分類主計畫（Umbrella Plan）並拆分為三大正交子計畫 (`sub_01` ~ `sub_03`)**：
  - 經與開發者完成多輪討論並透過兩輪共 3 位盲眼 Subagent 執行 Devil's Advocate 反向查驗後，將整體工程拆分為三個職責正交之子計畫：
    1. [`sub_01_release_binary_and_git_history`](./sub_01_release_binary_and_git_history/P00_discuss.md)：發布解耦架構、本地同版本自給自足動態打包、`pruned` 版本同三元組自動平滑遞補與 `releases` 孤兒分支 CI 管線。
    2. [`sub_02_release_metadata_and_compat_governance`](./sub_02_release_metadata_and_compat_governance/P00_discuss.md)：事後相容性修正機制（`index.json` 方案 II 聚合帳本 + `"status": "active"|"pruned"` + `dev` 輕量維護指令）、釋出元數據向前相容解析與 `UpdateChecker` 跨版本 `[CRITICAL UPDATE]` 告警。
    3. [`sub_03_legacy_release_migration_and_history_purge`](./sub_03_legacy_release_migration_and_history_purge/P00_discuss.md)：存量 37 個 `.zip` 全數保留遷移與 `index.json` 自動回填、本次變動模組正式發布、`.gitignore` 切換與 `git filter-repo` 全歷史一次性徹底淨化。

---

## 3. 開放議題與確認紀錄

- [x] 已完成 `R01_release_binary_and_git_history_analysis.md` 調研定案。
- [x] 已完成 `sub_01`、`sub_02`、`sub_03` 規格收斂與兩輪盲眼 Subagent 反向查驗補強。

