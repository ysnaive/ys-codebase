# 技術路線圖：發布產物二進位儲存與 Git 歷史瘦身優化 (Roadmap)

> 主題：發布產物二進位儲存與 Git 歷史瘦身優化  
> 歸檔日期：2026-08-29  
> 狀態：**Paused / Backlog (列入中長期里程碑)**  

---

## 1. 問題陳述與根因量化 (Problem & Root Cause)

### 1.1 痛點現象
在專案演進至第 100 個 Commit 時，`.git/` 資料夾體積增長偏快（未壓縮物件庫約 **4.4 MB**，壓縮後 Packfile 達 **3.03 MiB**）。

### 1.2 全庫歷史物件量化分析
透過 `git rev-list --objects --all` 與 `git cat-file --batch-check` 分析結果：

```
路徑分類 (Git 歷史累積)                         未壓縮總體積       Blob 數量
-----------------------------------------    -------------    ----------
ys_codebase/modules (運行端歷史副本)           3.71 MB           485
CHANGELOG.md (高頻大文字)                     2.91 MB            57
plans/archived (全階段 SOP 計畫檔案)          2.67 MB           533
ys_codebase/release (*.zip 二進位發布包)      2.08 MB            43 (純二進位)
ys_codebase/source (源碼 SSOT)                1.01 MB           166
```

### 1.3 核心根因
1. **二進位壓縮包無 Delta Diff**：`.zip` 檔案在 Deflate 演算法下，任何源碼微調都會造成二進位 Byte Stream 雪崩效應，Git 無法進行差異壓縮，每個版本的 zip 均以 100% 完整體積寫入 Packfile。
2. **早期版本過渡期沉澱**：早期版本在 `ys_codebase/release/` 曾有同名覆蓋（4~5 次）與刪除重命名，導致雖然當前工作目錄僅有 14 個 zip (~717 KB)，但歷史中沉澱了 **43 個獨立 zip Blobs（共 2.08 MB）**，佔 Packfile 空間 **60%+**。

---

## 2. 四大候選架構方案對比 (Candidate Solutions)

| 方案 | 運作原理 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：Git LFS** | 倉庫僅存 100 Bytes 指針，zip 存入 LFS 空間。 | 官方標準、大檔管理方便。 | 需本機與 CI 安裝額外外掛；遠端託管有配額限制。 | ⭐️⭐️⭐️ |
| **方案 2：孤兒發布分支 (Orphan Branch)** | 建立無父節點之獨立分支（如 `release-store`），發布時透過 `--amend` 或 Squash 保持歷史長度為 1~2。 | 100% 原生 Git、主分支 (`main`) 徹底純文字化。 | 工具鏈整合成本偏高（需處理切換分支/Worktree 與並發鎖定）。 | ⭐️⭐️⭐️⭐️ |
| **方案 3：二進位完全脫鉤 Git (推薦)** | `.gitignore` 排除所有 `*.zip`，僅追蹤 `index.json`，zip 產物置於本地 cache 或外部 Artifacts / GitHub Releases。 | 最純粹的現代軟體倉庫架構、維護難度最低、零狀態風險。 | 新環境需定義產物獲取管道（本地 cache 或遠端 Provider 下載）。 | ⭐️⭐️⭐️⭐️⭐️<br/>(最高推薦) |
| **方案 4：Submodule 隔離** | 將 `release/` 抽離為獨立子模組倉庫。 | 主倉庫體積解耦。 | 增加 Submodule 初始化與同步的心智負擔。 | ⭐️⭐️ |

---

## 3. 多維度綜合可行性評估

| 評估維度 | 方案 2：孤兒分支 (Orphan Branch) | 方案 3：二進位脫鉤 (Git Ignore + Releases) | 歷史清洗 (`git-filter-repo`) |
| :--- | :--- | :--- | :--- |
| **可行性 (Feasibility)** | 🟢 **高 (100% 原生 Git)** | 🟢 **高 (極致純文字)** | 🟢 **高 (成熟工具)** |
| **後續維護難度 (Maintenance)** | 🔴 **偏高 (隱性狀態機成本)** | 🟢 **極低 (維護負擔最小)** | 🟡 **中等 (一次性維護)** |
| **可靠性 (Reliability)** | 🟡 **中等 (腳本分支切換風險)** | 🟢 **極高 (純檔案操作)** | 🔴 **低 (破壞性改寫 Hash)** |
| **落地難度 (Implementation)** | 🟡 **中等 (需改寫發布腳本與測試)** | 🟡 **中等 (需考慮分發管道)** | 🔴 **高 (全庫備份與重置)** |

---

## 4. 歷史冗餘清洗標準作業流程 (Historical Cleanup SOP)

未來若決定對過往歷史進行徹底瘦身，採用 Git 官方專用工具 **`git-filter-repo`**：

> ⚠️ **執行前置要求**：必須先完整複製整個專案目錄作為本機備份！

```bash
# 步驟 1：安裝 git-filter-repo 工具
pip install git-filter-repo

# 步驟 2：從全歷史 Commit 中徹底移除 release 下的所有 zip
git filter-repo --path ys_codebase/release --invert-paths --force

# 步驟 3：強制清除所有歷史 Reflog 與懸空物件，重新進行極限壓縮
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

- **預期效益**：`.git/` 體積預計從 **4.4 MB (Packfile 3.03 MiB)** 驟降至 **< 1.2 MB**（瘦身幅度超過 **60%**）。

---

## 5. 決策結論與未來實施路線圖 (Roadmap)

### 5.1 近期策略 (Current Strategy)
- **暫緩實施**：目前 `.git` 體積為 3.03 MiB，絕對值極小，對 clone 與儲存無實質效能損耗。專案處於模組功能快速演進期，不宜進行破壞性歷史重寫。

### 5.2 未來啟動時機 (Trigger Conditions)
- **觸發條件 1**：專案準備對外開源發布或建立 1.0 LTS 長期支援版本。
- **觸發條件 2**：引入遠端套件託管管道（如 GitHub Releases 或專用 HTTP Package Provider）。

### 5.3 實施步驟
1. **Stage 1 (解耦)**：更新 `.gitignore` 排除 `ys_codebase/release/**/*.zip`，發布管線僅追蹤 `index.json`。
2. **Stage 2 (分發)**：對接遠端 Release Provider / 本地 Cache 機制。
3. **Stage 3 (清洗)**：執行 `git-filter-repo` 一次性清理過往歷史冗餘，達成極致純文字輕量倉庫。
