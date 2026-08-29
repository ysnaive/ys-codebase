# 協議產物工廠流水線規範 (Factory Pipeline Specification)

> 適用模組：`agents-workflow`  
> 核心組件：`ArtifactCompiler` (`compiler.py`), `ReleasePublisher` (`publisher.py`)  
> 規範版本：v2.0 (兩階段 6 步語意編譯發布管線)

---

## 1. 兩階段 6 步語意流水線概觀

```text
[1. 啟動] ──► [2. 段落佔位符解析] ──► [3. 釋出環境解析] ──► [4. URI 佔位符解析] ──► [5. 文件產出] ──► [6. 結束]
               (Stage 1: Content)     (Stage 2A: Targets)   (Stage 2B: Paths)      (Stage 2C: Atomic)
```

| 階段序號 | 階段名稱 | 核心職責 | 產出/落地位置 |
| :---: | :--- | :--- | :--- |
| **階段 1** | **啟動 (Startup)** | 搜集全系統 contributes（`export`、`insert`、`token`、`release_target`），初始化 `ExecutionContext`。 | 記憶體狀態機 |
| **階段 2** | **段落佔位符解析 (Stage 1)** | 5-Step 狀態機多輪遞迴解算 `__@{token}__`（支援 `const`, `uri`, `computed`），清除錨點標籤行。 | `cache.root://agents-workflow/resolved_contents/` |
| **階段 3** | **釋出環境解析 (Stage 2A)** | 讀取 `config.project.json` 之 `release_targets: []`，為各啟用目標建立專屬發布拓撲映射表 (Deployment Manifest Map)。 | 記憶體發布計畫表 |
| **階段 4** | **URI 佔位符解析 (Stage 2B)** | 讀取中繼產物，依三層階層將 `__#{uri}__` 動態轉譯為相對於目標檔案之本機實體相對路徑 (`os.path.relpath`)。 | 記憶體渲染文本 |
| **階段 5** | **文件產出 (Stage 2C)** | 執行 4 步原子發布交易：過往清理 ➔ 提前解算 ➔ 持久紀錄 ➔ 目錄落地與 `AGENTS.md` 軟合併。 | 實體專案目錄（如 `.agents/`） |
| **階段 6** | **結束 (Teardown)** | 統計輸出成果摘要並釋放暫存資源。 | 終端日誌與正常退出 |

---

## 2. 三層 URI 重映射演算機制 (3-Tier URI Resolution)

當 Stage 2 掃描到 `__#{uri}__` 標籤時，依以下優先級執行路徑轉譯：

```text
┌─────────────────────────────────────────────────────────────────┐
│                     __#{target_uri}__ 標籤                       │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
       ┌───────────────────────────────────────────────────┐
       │ Tier 1: 是否命中本次發布拓撲表 (Deployment Map)?   │
       └─────────┬───────────────────────────────┬─────────┘
              Yes│                             No│
                 ▼                               ▼
       ┌───────────────────┐           ┌───────────────────┐
       │ 查表取得目標實體  │           │ Tier 2: 是否為    │
       │ 路徑並計算相對    │           │ 專案級語意協議?   │
       │ 路徑 (os.path.    │           │ (project:// 等)   │
       │ relpath)          │           └─────┬───────┬─────┘
       └───────────────────┘              Yes│     No│
                                             ▼       ▼
                                   ┌───────────┐ ┌─────────┐
                                   │ uri.      │ │ Tier 3: │
                                   │ resolve() │ │ 安全    │
                                   │ 計算相對  │ │ 降級    │
                                   │ 路徑      │ │ 原樣    │
                                   └───────────┘ └─────────┘
```

---

## 3. 雙軌 Manifest 與原子發布交易語意 (Dual-Track Manifest & Atomic Release)

為防止無效 File I/O 頻繁衝擊磁碟、中途崩潰導致孤立檔案污染，以及跨機器協作時絕對路徑污染 Git 版本庫，發布引擎採用分流雙軌 Manifest 與 4 步原子交易保證：

### 🏛️ 雙軌空間與路徑分流架構
1. **Project 軌 (Tier 2，團隊共享 Targets)**：
   - **儲存空間**：`storage://agents-workflow/release_manifest.json`（受 Git 追蹤）。
   - **路徑格式**：100% 使用 `project://` 語意協議路徑（例如 `project://.agents/workflows/Auto.md`），徹底消除本機絕對路徑外溢與 Git dirty diff。
2. **Local 軌 (Tier 1，個人私有 Targets)**：
   - **儲存空間**：`cache://agents-workflow/release_manifest.json`（受 Git 忽略）。
   - **路徑格式**：使用本機實體絕對路徑。

### 🔄 4 步原子發布交易流水線
0. **階段 0 (來源端雙軌指紋短路 - Stage 0)**：計算來源資產（`assets/`）、`manifest.json`、專案組態與 Target 規則之綜合 SHA-256 指紋。若 `force=False` 且雙軌指紋相符且各軌檔案皆完好存在，**立即提前返回 (0 I/O，耗時 ~1ms)**。
1. **步驟 1 (過往發布狀態獨立清理 - Pruning)**：分別讀取 Project 與 Local 歷史紀錄，比對全量物化檔案集合，精確刪除已停用 Target 或已刪除資產之實體檔案。
2. **步驟 2 (提前解算新清單與分流集合)**：對所有已啟用的 Release Targets 提前完整解算目標檔案映射，並標註 Project 軌與 Local 軌歸屬清冊。
3. **步驟 3 (原子寫入雙軌 Manifest)**：分別將 Project 軌 (`project://` 格式) 寫入 `storage://`，將 Local 軌 (絕對路徑格式) 寫入 `cache://`。
4. **步驟 4 (物理落地與增量軟合併)**：比對磁碟現有內容執行增量寫入；所有檔案寫入顯式傳入 `newline="\n"`，與根目錄 `.gitattributes` 配合確保全專案純 LF 換行；若 `enable_agents_md: true`，對根目錄 `AGENTS.md` 執行無損軟合併。

