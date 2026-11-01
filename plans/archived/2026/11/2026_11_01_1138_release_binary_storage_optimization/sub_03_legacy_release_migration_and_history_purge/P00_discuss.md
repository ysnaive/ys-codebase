# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：存量發布遷移、新版本發布與 Git 歷史徹底淨化 (sub_03)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「下一個問題就需要非常仔細的討論了，我們要怎麼處裡現有發布內容? 還有本次的變動?」
  - 「對於 4. 我需要補充，這三個模組在後台有打包」
  - 「2. 策略 A（全數保留並遷移至 releases 分支 + 自動提取補齊 index.json 的 dependencies）；感覺這次的遷移和淨化也是大工程，可能要單獨列 sub 03 ?」
  - 「同意， /blind-subagent 排查有沒有我們沒考慮到的其他問題」
- **核心目標**：
  - 在 `sub_01` 與 `sub_02` 代碼改造與測試驗收完成後，以獨立子計畫（`sub_03`）執行存量 37 個 `.zip` 發布包與 5 份 `index.json` 的無損元數據遷移、本次變更模組（`core`、`dev`、`yscb.py`）之正式升版發布、遠端 `releases` 孤兒分支初始化、母倉 `.gitignore` 切換以及 `git filter-repo` 全歷史一次性徹底淨化。
- **既有組件復用與查重 (Reuse Discovery)**：
  - `ys_codebase/release/{core,dev,server,knowledge-db,agents-workflow}/index.json` 與存量 `.zip`
  - `sub_01` 與 `sub_02` 產出之新版 `dev`（`release`、`index-patch`）與 `core` 工具鏈
- **邊界排除 (Explicitly Excluded)**：
  - **嚴禁在 `sub_01` 與 `sub_02` 通過完整測試前提前刪除 `.zip` 或執行 `git filter-repo`**。
  - **嚴禁對未變更源碼之 `server@1.0.1.3`、`knowledge-db@1.1.2.3`、`agents-workflow@1.2.2.2` 進行冗餘版號遞增**（此三模組已於 Commit `4e014d0` 打包完成，僅需補齊 `index.json` 之釋出元數據）。
- **架構影響範圍**：
  - `ys_codebase/release/*/index.json`、`ys_codebase/release/*/*.zip`
  - `yscb.py` (`__version__`)、`ys_codebase/source/{core,dev}/manifest.json`
  - `.gitignore`、遠端 `origin/releases` 孤兒分支與母倉 `.git` 歷史物件庫

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 存量 37 個歷史 `.zip` 採「策略 A：全數保留遷移至 `releases` 分支 + 自動提取補齊 `index.json`」**：
  - 掃描 `ys_codebase/release/` 現有全部 37 個 `.zip`，自動讀取各包內 `manifest.json` 的 `dependencies` 回填至各模組 `index.json` 的 `releases[<ver>]`。
  - 針對剛在 `4e014d0` 正式打包完成的 `server@1.0.1.3`、`knowledge-db@1.1.2.3`、`agents-workflow@1.2.2.2`，不重新打 `.zip`，直接透過 `sub_02` 輕量維護指令補齊其 Issue #8 釋出元數據（`type`、`urgency`、`summary`）。
- **[P00:DR-02] 本次變動資產（`yscb.py`、`core`、`dev`）之升版與發布**：
  - 遞增 `yscb.py` 之 `__version__`（觸發外部舊版環境 `[CRITICAL UPDATE]` 提示執行 `self-update`），並為本次修改源碼之 `core` 與 `dev` 執行版本遞增與帶元數據之正式打包發布。
- **[P00:DR-04] 跨平台/跨系統掛載 (`virtiofs`/Windows) 目錄句柄鎖定三階段真偽鑑別與檔案級原子同步 (`In-place File-level Atomic Sync`) 及 `.build` 退回加固**：
  - 於 `core/engine.py` (`_atomic_swap_dir`) 與 `yscb.py` (`_fetch_and_extract_zip`)：當目錄級 `os.replace` 拋出 `EACCES`/`EBUSY`/`EPERM` 或 `winerror in (5, 32)` 時，執行三階段嚴格鑑別：① 檢查 `parent_dir` 與 `target_dir` 之 `os.access` 寫入權限；② 於 `target_dir` 內執行實機寫入探針（建立 `.yscb_write_probe` 並 `os.replace` + `os.remove`）以 100% 排除真權限/磁碟唯讀故障；③ 通過探針後備份現有檔案並逐檔以同目錄臨時檔 `os.replace` 原子同步，任一檔案異常即全量回滾並原樣拋出例外。
  - 於 `core/installer.py` (`_restore_module_package`) 與 `yscb.py` (`_bootstrap_package_from_provider`)：當請求版本為 `*.build` 但精確版號 `.build.zip` 已因升版被覆寫時，自動匹配同模組 `.build/<mod>/*.build.zip` 或 `index.json` 最新正式版並同步更新 `yscb.config.json`。
- **[P00:DR-03] 母倉 `.gitignore` 切換、`git filter-repo` 全歷史一次性徹底清洗與遠端 `releases` 孤兒分支發布工序**：
  - **嚴格執行順序（先清洗 `main` 歷史，再建立本地/遠端 `releases` 孤兒分支，避免 `git filter-repo` 洗掉本地 `releases` 分支）**：
    1. **前置準備**：安裝 `git-filter-repo` 工具；完成 `[P00:DR-02]` 之 `core`/`dev` 正式打包發布並更新 `yscb.config.json`，確保 `yscb.config.json` 中所有 `installed_modules[<mod>]["version"]` 與 `ys_codebase/source/<mod>/manifest.json` 的 `"version"` **100% 嚴格相等**。
    2. **外部備份**：記錄 `git remote get-url origin`，並將完整 `ys_codebase/release/`（含 37 個存量 `.zip`、新打包 `.zip` 與 5 份更新後之 `index.json`）及 `.agents/` 完整備份至工作區外部暫存目錄（如 `/tmp/yscb_release_backup/`）。
    3. **`.gitignore` 切換与提交**：於母倉根目錄 `.gitignore`（非託管區）新增 `ys_codebase/release/**/*.zip`，執行 `git rm --cached 'ys_codebase/release/*/*.zip'`，使 `main` 分支僅追蹤 `ys_codebase/release/*/index.json` 並完成 Commit。
    4. **執行 `git filter-repo` 全歷史過濾**：對 `main` 歷史執行一次性清洗，移除：
       - ① 二進位發布包與早期解壓態發布子目錄：`ys_codebase/release/*/*.zip`、`release/*/*.zip`、`ys_codebase/release/*/*/`（僅保留 `ys_codebase/release/*/index.json`）。
       - ② 運行時與快取目錄：`ys_codebase/modules/`、`modules/`、`ys_codebase/.modules/`、`ys_codebase/.mirror/`、`ys_codebase/storage/`。
       - ③ 建構暫存目錄：`ys_codebase/build/`、`build/`、`ys_codebase/.build/`。
       - ④ 二層物化與隔離工作區：`.agents/`、`workflows/`、`temp_workflow/`、`.quarantine/`。
    5. **重建 Remote、垃圾回收與環境自舉實證**：
       - 重建被 `git filter-repo` 預設移除之 `origin` remote（`git remote add origin <url>`），並執行 `git reflog expire --expire=now --all && git gc --prune=now --aggressive`。
       - 在工作樹完全無 `.zip` 的狀態下，執行 `python yscb.py restore --force` 實證 5 大模組 100% 透過 `sub_01` 之本地同版本 `source/<mod>` 動態打包自舉成功，並執行 `python yscb.py agents-workflow release` 重新編譯物化 `.agents/`。
    6. **建立並推送 `releases` 單層孤兒分支**：將外部備份之全部存量與新版 `.zip` 及 `index.json` 寫入無父節點之單一孤兒 Commit 並推送至 `origin/releases`。

---

## 3. 開放議題與確認紀錄

- [x] `sub_03` 存量遷移、新版發布與 Git 歷史淨化步驟已確認（`Confirmed`）。

