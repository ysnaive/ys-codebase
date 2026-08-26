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

## 3. 4 步原子發布交易語意 (4-Step Atomic Release)

為防止發布中途崩潰導致殘留檔案或孤立檔案污染，發布引擎採用基於 `storage://agents-workflow/release_manifest.json` 的 4 步交易保證：

1. **步驟 1 (過往發布狀態清理)**：讀取持久紀錄，若存在過往發布清單，比對本次即將發布清單，精確刪除已停用 Target 或已刪除資產之實體檔案。
2. **步驟 2 (提前解算新清單)**：對所有已啟用的 Release Targets 提前完整解算所有目標檔案的「絕對路徑 ➔ 最終渲染字串」映射。若解算過程發生嚴重錯誤，立即中止交易，絕不污染專案檔案系統。
3. **步驟 3 (更新持久清單)**：原子寫入本次最新發布清單至 `storage://agents-workflow/release_manifest.json`。
4. **步驟 4 (物理落地與軟合併)**：建立目標實體目錄，原子寫入檔案；若 `enable_agents_md: true`，對根目錄 `AGENTS.md` 執行無損軟合併。
