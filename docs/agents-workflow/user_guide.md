# Agents Workflow 使用者與操作指南 (User Guide)

本文件提供 `agents-workflow` 模組的完整操作指引，特別針對 **Dev Plans 開發計畫工具鏈**（`plan archive`, `plan status`, `plan search`, `plan verify`）之日常操作與工程規範進行深度說明。

---

## 1. Dev Plans 工具鏈 (Plans Management Toolchain)

YS-Codebase 將所有開發計畫管理功能收斂為原生 CLI 子指令，零依賴硬編碼路徑，全面透過 `core.uri` 解析語意空間（`workflow.plans://` 與 `workflow.archived://`）。

### 1.1 計畫狀態矩陣掃描 (`plan status`)

掃描當前專案活躍進行中的開發計畫（`workflow.plans://`），即時解析各計畫之 Track 類型（Umbrella, Fast Track, Full Track, Phase 0）與當前 Phase 狀態，並以樹狀縮排展示子計畫階層。

```bash
# 掃描並展示進行中開發計畫狀態矩陣
python yscb.py agents-workflow plan status

# 亦支援快速別名
python yscb.py agents-workflow plan-status
```

> [!NOTE]
> 依據設計規範，`plan status` 專注於活躍進行中計畫，**不掃描歷史封存目錄**。

#### 輸出範例
```text
==========================================================================================
計畫名稱 / 子計畫                                           | Track 模式        | 當前狀態             | 位置
==========================================================================================
2026_08_25_2200_agents_workflow_migration            | Umbrella        | In Progress      | plans/
  └─ sub_01_core_skeleton_migration                  | Full Track      | Completed        | plans/
  └─ sub_08_plans_cli_toolchain_migration            | Full Track      | Phase 7          | plans/
==========================================================================================
```

---

### 1.2 計畫安全歸檔 (`plan archive`)

將已結案的計畫安全搬移至歷史年/月封存目錄（`workflow.archived://{YYYY}/{MM}/{plan_name}/`）。

```bash
# 標準歸檔（觸發 4 重守門檢查）
python yscb.py agents-workflow plan archive 2026_08_20_1200_demo_feature

# 強制歸檔（略過 Completed 標記與 CHANGELOG 記載檢查）
python yscb.py agents-workflow plan archive 2026_08_20_1200_demo_feature --force

# 亦支援快速別名
python yscb.py agents-workflow plan-archive 2026_08_20_1200_demo_feature
```

#### 🛡️ 4 重守門安全防護
1. **完成狀態守門**：檢查 `P07_walkthrough.md`、`fast_track_plan.md` 或 `umbrella_overview.md` 是否標記 `Completed`。
2. **CHANGELOG 登載守門**：核對專案根目錄 `CHANGELOG.md` 是否已記載該計畫發布紀錄。
3. **現場快照清理**：自動偵測並物理刪除殘留的暫時性交接快照 `handoff.md`。
4. **目的地衝突防護**：若 `workflow.archived://{YYYY}/{MM}/{plan_name}/` 已存在同名目錄，強制阻斷防止覆蓋。

---

### 1.3 歷史與決策檢索 (`plan search`)

跨活躍進行中與歷史歸檔計畫檢索決策記錄 (DR) 或全文關鍵字。

```bash
# 1. 檢索架構決策記錄 (DR模式，正則結構化擷取並自動去重)
python yscb.py agents-workflow plan search --dr
python yscb.py agents-workflow plan search "URI" --dr
python yscb.py agents-workflow plan search --dr --year=2026 --month=08 --limit=15

# 2. 跨計畫全文程式碼檢索（展示匹配行號與前後上下文）
python yscb.py agents-workflow plan search "PlanArchiver"
python yscb.py agents-workflow plan search "VFS" --limit=10

# 亦支援快速別名
python yscb.py agents-workflow plan-search --dr
```

#### 輸出範例 (DR 模式)
```text
==========================================================================================
Plan 名稱 / 來源檔案                           | DR ID / 標題             | 結論 / 摘要
==========================================================================================
2026_08_25_2200_agents_workflow_migr...   | [P01:DR-01] 舊版 4 大腳...  | 完整收斂至 agents-workflow.plans 子套件...
2026_08_25_2200_agents_workflow_migr...   | [P02:DR-01] 階梯式封裝...   | 建立專屬 plans 子套件，定義自定義例外...
==========================================================================================
```

---

### 1.4 計畫規範與合規性稽核 (`plan verify`)

全面稽核 Markdown 文件是否符合開發標準規範，及早發現模板指引殘留與格式缺失。

```bash
# 稽核所有進行中計畫
python yscb.py agents-workflow plan verify

# 稽核指定計畫
python yscb.py agents-workflow plan verify 2026_08_25_2200_agents_workflow_migration

# 一併稽核歷史封存計畫
python yscb.py agents-workflow plan verify --all

# 亦支援快速別名
python yscb.py agents-workflow plan-verify
```

#### 稽核重點
- **指引過濾檢查**：偵測 Markdown 檔案內是否殘留 `<!-- AGENT_GUIDANCE -->` 模板指引註解未剝除。
- **Header 元數據檢查**：驗證 Markdown 開頭 Blockquote 是否齊備 `功能名稱`、`建立日期` 與 `狀態` 欄位。
- **子計畫遞迴覆蓋**：自動深入 `sub_*` 目錄進行遞迴稽核。

---

## 2. 工作流程資產發布與初始化

### 2.1 一鍵工作流初始化 (`--init-default`)
```bash
# 初始化 workflow.plans://, workflow.archived://, workflow.docs:// 目錄結構與組態
python yscb.py agents-workflow --init-default -y
```

### 2.2 原子發布交易 (`release`)
```bash
# 執行 4 步原子交易發布至 .agents/ 目錄並軟合併 AGENTS.md
python yscb.py agents-workflow release
```
