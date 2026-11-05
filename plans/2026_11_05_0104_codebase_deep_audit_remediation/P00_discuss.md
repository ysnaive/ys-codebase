# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_05_0104_codebase_deep_audit_remediation  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模型：Unknown  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對全倉執行分批八維度深度審計（重點關注新模組 `vscode-support` 與 `gdrive-support`），經 4 路盲眼子代理反向驗證確認真實性與影響幅度後，規劃全倉修復計畫（分類型主計畫 + N agents sub-plan），並將審計報告作為分類型主計畫之 `R01`。
- **核心目標**：
  1. 將雙輪審計成果固化為主計畫調研報告 `R01_codebase_deep_audit.md`（狀態 `Concluded`），確立全倉 **64 項有效修復標的**（`2 P0 / 12 P1 / 29 P2 / 21 P3`）與 **8 大防回歸修復紅線**。
  2. 以 **預先規劃型（Pre-planned）Umbrella 主計畫** 統籌 **4 個正交無衝突子計畫（`sub_01` ～ `sub_04`）**，使各子計畫可由獨立 Agent 平行或序列推進而不發生跨模組檔案寫入衝突。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `gdrive-support` 既有 `_token_lock` / `_tls` 架構擴充 `_cache_lock` 與 `_precreate_remote_dirs` 分層平行化（對標 `TODO-23`）。
  - 復用 `vscode-support` 既有 `_yscb_managed["extraPaths"]` 差集追蹤機制擴充 `source/<mod>` 與 `.modules/<mod>` 投影（對標 `TODO-22`）。
  - 復用 `dev/testing/runner.py` 已實作但未接線之 `run_subprocess_with_tree_timeout` 完成子進程樹超時保護。
- **邊界排除 (Explicitly Excluded)**：
  - 排除經盲眼反向查驗正式駁回之 2 項偽陽性：`U1-P2-01`（`reconciler.py` 單邊修改 vs 對向刪除要求 `--force` + `--delete` 雙重授權屬刻意防誤刪設計）與 `DEV-06`（`releaser.py` 9 模組 Kahn 排序耗時 `<5us`）。
  - 排除破壞 20% 差異分支不變量之過激改法（如對 `contributes.get` 無條件 `deepcopy`、對 `RRF` 融合分數套用 BM25 `min_score`、刪除 `is_dirty_file_match` 雙向後綴匹配、或在 `create_sandbox` 全程持有 `_SANDBOX_LOCK`）。
- **架構影響範圍**：涵蓋宿主 `yscb.py` 與 `ys_codebase/source/{gdrive-support,vscode-support,core,server,dev,agents-workflow,file-space,ast,knowledge-db}/` 九大模組源碼與對應單元測試。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採納雙輪盲眼反向查驗校準後之 64 項有效標的、雲端實況追補之 3 項 `gdrive-support` 同步漏洞與 8 大防回歸紅線**：
  - 首輪檢出之 66 項候選問題經 4 路 Devil's Advocate 盲眼子代理於 Linux VM 實證反推後，確立 64 項有效問題（`2 P0 / 12 P1 / 29 P2 / 21 P3`）；並於雲端完整性盤點時額外追補 3 項 `gdrive-support` 同步缺陷（`U1-P0-02` `sync_spaces` 為空未阻斷同步與缺少 `contribute.json`、`U1-P0-03` `SYSTEM_NAMES` 誤濾分支根目錄 `README.md`、`U1-P2-04` `DELETE_REMOTE` 未清理空父目錄）及 1 項雲端 `.agents/` 格式備忘（`CLOUD-OPS-01`）。
  - **本地端先行修復與雲端強制推送對齊紀錄（2026-11-05 14:12）**：
    1. 本地已完成 `2026_11_04_1739_sys_path_and_five_semantic_spaces`（統一 `core.platform` `sys.path` 注入並確立 `config.local://` 與 `storage.local://` 五大語意空間）與 `2026_11_05_0528_gdrive_changes_api_and_lock_preemption`（`/drive/v3/changes` 三級 `remote_repo_cache` 增量快取、前景 `cli_yield.signal` 協同讓鎖、Stage 3 單檔原子 CoW 與 `finally` `meta_dirty` 落盤），並透過 `gdrive push --force` 完成 129 筆變更上雲對齊。
    2. 經比對最新雲端源碼，正式將 **6 項已修畢標的** 標記為 `Resolved in Prior Plans` 並自子計畫待辦扣除：`U1-P1-03`（Stage 3 單檔原子 CoW 與 `finally` `meta_dirty` 寫回）、`U1-P2-03`（`changes` API `remote_repo_cache` 取代全量重掃）、`U2-P1-02`/`[TODO-22]`（`vscode-support` 投影全模組 `extraPaths`）、`U3-P2-03`（`core/symbols.py` 僅於 `YSCB_TEST_SANDBOX=="1"` 回退 `module.source://`）、`DEV-02`（`runner.py` 清除 `sys.modules["scripts"]` 與底線 `pkg_name`）、`AW-03`（拔除 `agents-workflow` 頂層手動 `sys.path` 補丁並由 `dev/checker.py` 強制零豁免 AST 守門）。
    3. 同步更新 `U1-P0-03` 定位：`coordinator.py` 升級 `remote_repo_cache` 後，`rel_p in SYSTEM_NAMES` 對分支根目錄 `README.md` 之誤攔截位於 `_scan_remote_branch_with_dirs` (`L1700`) 與 `_try_incremental_remote_cache` (`L2058, L2136`) 共 3 處。
- **[P00:DR-02] 按模組實體目錄正交切分為 4 個子計畫（`sub_01` ～ `sub_04`）以支援多 Agent 並行推進**：
  - 為符合 `SubagentStandards.md` 單回合平行上限（3～4 個）與 Single-Writer 寫入正交圍欄，按職責與目錄邊界拆分為：
    1. `sub_01_gdrive_and_vscode_support`：聚焦重點新模組 `gdrive-support`（10 項）與 `vscode-support`（5 項）。
    2. `sub_02_host_and_core_microkernel`：聚焦 `yscb.py` 與 `core`（14 項，含將 `core/uri.py` 全域作用域變數改為 `threading.local()` 以根治 `DEV-01`）。
    3. `sub_03_server_dev_and_workflow`：聚焦 `server`（6 項）、`dev`（4 項）與 `agents-workflow`（6 項）。
    4. `sub_04_knowledge_pipeline`：聚焦三階檢索管線 `file-space`（6 項）、`ast`（6 項）與 `knowledge-db`（6 項）。

---

## 3. 開放議題與確認紀錄

- **已確認事項**：已完成雙輪審計與 `R01_codebase_deep_audit.md` 固化，並建立主計畫總覽與 4 個子計畫之 `P00_discuss.md` 起點，待開發者確認啟動順序（如優先啟動 `sub_01` 或 4 路子計畫平行推進 Phase 01～05）。
