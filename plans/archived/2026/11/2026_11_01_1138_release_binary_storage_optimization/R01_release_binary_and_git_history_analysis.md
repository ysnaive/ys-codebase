# 專題調研與分析報告：發布產物 `.zip` 二進位儲存解耦與 Git 歷史瘦身深度調研 (R01_release_binary_and_git_history_analysis.md)

> 調研主題：發布產物二進位儲存與 Git 歷史瘦身優化  
> 建立日期：2026-11-01  
> 所屬主計畫：N/A (Root Plan)  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與調研目標 (Background & Objectives)

- **背景脈絡與核心問題**：
  - 本議題最早於 `2026-08-29`（約第 100 個 Commit）記入 [roadmap.md](./roadmap.md)。當時 `.git` Packfile 為 `3.03 MiB`，歷史中累積了 `43` 個 `.zip` 二進位 Blobs（共 `2.08 MB`）。
  - 隨著專案演進至第 `237` 個 Commit（`2026-11-01`），每次執行 `/bump-revision` 或 `dev release` 都會將新的 `ys_codebase/release/<mod>/<ver>.zip` 提交進 `main` 分支。儘管 `Builder._update_release_index` 實作了「同三元組保留最新 3 個 revision、跨三元組僅保留最高 revision」的工作樹滑動窗口（使工作目錄始終維持約 37 個 `.zip`），但**從工作樹刪除舊 `.zip` 並不會將其從 Git 歷史物件庫中抹除**。
  - 更關鍵的是：`.zip` 採用 Deflate 壓縮，即便模組內僅修改一行文字，壓縮後的二進位位元流也會完全改變，導致 Git Packfile 的 Delta Compression 對 `.zip` 幾乎失效。
- **調研目標與範疇**：
  1. **現況量化診斷（Commit #100 vs Commit #237）**：精確測量當前 `.git/objects` 中各類資產與各模組 `.zip` 的真實磁碟佔比。
  2. **既有代碼耦合點全盤解剖**：徹查 `yscb.py`、`core`、`dev` 中所有依賴 `ys_codebase/release/<mod>/<ver>.zip` 實體檔案的機制，找出若直接 `.gitignore` 排除 `.zip` 會斷裂的關鍵路徑。
  3. **候選架構方案深度權衡**：對比雙分支解耦架構、GitHub Releases 託管、母倉 Source-Fallback 動態打包等路徑的工程代價與執行風險。
  4. **歷史清洗 (`git filter-repo`) 安全影響評估**：評估清洗歷史對 Commit Hash、Tag、遠端 Force Push 與既有工作區的影響。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 現況量化診斷：Commit #100 (2026-08) vs Commit #237 (2026-11)

透過 `git rev-list --objects --all` 與 `git cat-file --batch-check` 對當前倉庫（`237` Commits）進行全量物件掃描：

| 路徑分類 (Git 歷史全部 Blobs) | Blob 數量 | 未壓縮總體積 (Raw) | 磁碟打包體積 (Pack/Disk) | 佔全庫磁碟空間比例 |
| :--- | :---: | :---: | :---: | :---: |
| **`ys_codebase/release/*.zip` (二進位發布包)** | **177** | **15.12 MB** | **7.49 MB** | **45.67%** |
| `plans/archived/` (封存開發計畫 Markdown) | 1,618 | 7.90 MB | 3.66 MB | 22.32% |
| `ys_codebase/source/` (五模組源碼與測試 SSOT) | 1,901 | 22.66 MB | 2.31 MB | 14.09% |
| `CHANGELOG.md` (高頻追加之長歷史檔案) | 159 | 21.52 MB | 1.24 MB | 7.56% |
| `plans/` (活躍計畫與路線圖) | 302 | 1.82 MB | 0.53 MB | 3.23% |
| `docs/` (系統知識庫 Markdown) | 402 | 3.88 MB | 0.49 MB | 2.99% |
| 其他設定與根目錄檔案 (`yscb.py` 等) | 1,107 | 5.19 MB | 0.49 MB | 2.99% |
| 早期歷史殘留 (`ys_codebase/modules` 明文副本) | 641 | 4.89 MB | 0.18 MB | 1.10% |
| **總計 (Total)** | **6,307** | **82.98 MB** | **16.40 MB** | **100.00%** |

#### 各模組 `release/*.zip` 歷史沉澱明細
| 模組名稱 | 當前工作樹 `.zip` 數 | Git 歷史累積 `.zip` Blobs 數 | 歷史未壓縮總體積 | 歷史 Packfile 磁碟體積 |
| :--- | :---: | :---: | :---: | :---: |
| **`agents-workflow`** | 9 | 51 | 6.51 MB | **3.23 MB** |
| **`knowledge-db`** | 8 | 43 | 4.24 MB | **1.76 MB** |
| **`core`** | 9 | 39 | 2.47 MB | **1.41 MB** |
| **`dev`** | 7 | 36 | 1.68 MB | **0.93 MB** |
| **`server`** | 4 | 8 | 0.22 MB | **0.17 MB** |
| **合計** | **37** | **177** | **15.12 MB** | **7.49 MB** |

---

### 2.2 既有代碼對 `release/*.zip` 的耦合點深度解剖

| 耦合點編號 | 模組與檔案座標 | 現行行為與對 `.zip` 的依賴方式 | 直接移除 Git 中 `.zip` 後果 |
| :--- | :--- | :--- | :--- |
| **C1：外部專案遠端一鍵初始化與安裝** | [yscb.py](../../yscb.py) (`DEFAULT_PROVIDER_URL`)、[engine.py](../../ys_codebase/source/core/core/engine.py) (`_download_from_remote_tier`) | 外部使用者下載單檔 `yscb.py` 執行 `python yscb.py init` 或 `install <mod>` 時，預設向 `https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release/<mod>/<ver>.zip` 發起 HTTP GET 下載 `.zip`。 | **完全斷裂 (HTTP 404)**！若 `main` 分支上沒有 `.zip`，外部環境無法從 `main` 分支 raw URL 下載任何模組。 |
| **C2：母倉新 Clone / 跨分支切換之自動還原 (`restore`)** | [yscb.py](../../yscb.py) (`_bootstrap_package_from_provider`)、[yscb.config.json](../../yscb.config.json) | 母倉的 `yscb.config.json` 設定 `"default_provider": "./ys_codebase/release"`。當開發者剛 `git clone` 母倉時，`yscb.py` 會去 `./ys_codebase/release/core/<ver>.zip` 解壓 `core` 與其他模組。 | **新 Clone 母倉無法啟動**！因為新 Clone 的工作樹中 `ys_codebase/release/` 下只有 `index.json` 而無 `.zip`。 |
| **C3：`dev release-check` 版本不可變性與單調遞增守門** | [releaser.py](../../ys_codebase/source/dev/dev/releaser.py) (`release_check` Gate 2 & Gate 3) | Gate 2 檢查 `vfs.exists("module.release://<mod>/<ver>.zip")`；Gate 3 透過 `os.listdir(real_rel_dir)` 掃描所有 `.zip` 檔名來計算歷史最高版本 `global_highest`，未讀取 `index.json`。 | **Gate 2 & Gate 3 失效**！若新 Clone 環境無 `.zip` 實體檔，Gate 2/3 會誤以為該模組從未發布過任何版本。 |
| **C4：`Builder._update_release_index` 索引生成邏輯** | [builder.py](../../ys_codebase/source/dev/dev/builder.py) (`_update_release_index`) | 每次打包新版本時，重新掃描目錄下的實體 `.zip` 檔案並直接覆寫 `index.json`。 | 若本地只有剛打包的 1 個 `.zip`，`index.json` 中的歷史版本清單會被覆蓋清空為只剩 1 個版本。 |
| **C5：`AtomicEngine._find_manifest_in_local_provider` 依賴解析** | [engine.py](../../ys_codebase/source/core/core/engine.py) (`_find_manifest_in_local_provider`) | 本地 Provider 解析模組依賴 (`dependencies`) 時，會打開 `release/<mod>/<best_v>.zip` 讀取裡面的 `manifest.json`。 | 本地安裝時若無 `.zip` 且 `index.json` 無 `dependencies` 元數據，將回退為空依賴字典 `{}`。 |

---

## 3. 結論 (Conclusion)

- **核心結論（經開發者多輪討論拍板定案之四大支柱架構）**：
  1. **支柱一：通用模組設計與版本帳本 SSOT（`dev` & `core` 保持對第三方儲存庫策略中立）**：
     - **不寫死 `INTERNAL_IGNORE_PATTERNS`**：不在 `core/installer.py:INTERNAL_IGNORE_PATTERNS` 強制忽略 `/release/**/*.zip`。
     - **標準事件廣播取代特化 Hook**：當 `dev` 執行打包/發布完成時，統一透過 `core.events.broadcast("on_module_released", ExecutionContext("dev", "on_module_released", ...), emit_module="dev")` 發出標準事件。
     - **`release/<mod>/index.json` 升格為版本元數據 SSOT**：擴充 `index.json` 紀錄各版本的 `releases[<ver>]`（含 `status: "active"|"pruned"`, `dependencies`, `type`, `urgency`, `summary`），使 `Releaser.release_check`、`Builder._update_release_index` 與 `AtomicEngine` 以 `index.json` 結合現有 `.zip` 為權威依據。
  2. **支柱二：本地自給自足之同版本精確匹配動態打包與 `pruned` 同三元組自動遞補（`yscb.py` & `core`）**：
     - 本地 Provider 缺失 `<mod>/<ver>.zip` 時，若 `ys_codebase/source/<mod>/manifest.json` 存在且 `"version" == ver`，當場以純標準庫忽略過濾器動態打包至 `.mirror/` 與 `release/` 後解壓至 `.modules/`。
     - 若外部老專案於新環境 Clone 時遇到指定版本已被滑動視窗標記為 `pruned` 且無本地快取，自動平滑遞補至同三元組 (`X.Y.Z.*`) 最高可用 revision。
  3. **支柱三：母倉特化對接方案 B（`.gitignore` + `releases` 孤兒分支 + GitHub Actions 自動發布）**：
     - 於母倉根目錄 `.gitignore` 加入 `ys_codebase/release/**/*.zip`，使 `main` 分支僅追蹤純文字 `ys_codebase/release/*/index.json`。
     - 將 `DEFAULT_PROVIDER_URL` 更新為 `https://raw.githubusercontent.com/ysnaive/ys-codebase/releases`（並支援舊版 `main` URL 無感遷移），搭配 `.github/workflows/release-publish.yml` 以單一無父節點孤兒 Commit 發布至 `origin/releases`。
  4. **支柱四：全歷史 `.zip` 與早期誤追蹤目錄一次性徹底清洗 (`git filter-repo`)**：
     - 清除全歷史 `release/*/*.zip` 及早期誤入庫之 `modules/`、`.modules/`、`.mirror/`、`storage/`、`build/`、`.agents/`、`workflows/`、`temp_workflow/`、`.quarantine/`，並執行 `git gc --prune=now --aggressive`。
- **後續建議**：
  - 本調研結論已全數獲開發者拍板確認，並拆分為三個正交子計畫（[`sub_01`](./sub_01_release_binary_and_git_history/P00_discuss.md)、[`sub_02`](./sub_02_release_metadata_and_compat_governance/P00_discuss.md)、[`sub_03`](./sub_03_legacy_release_migration_and_history_purge/P00_discuss.md)）推進實作。

