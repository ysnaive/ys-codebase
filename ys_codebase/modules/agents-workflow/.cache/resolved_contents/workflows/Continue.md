> [!NOTE]
> ### 🧭 專案語意 URI 即時解析地圖 (JIT Dynamic Context)
> 本專案已註冊之語意 URI 實體路徑如下：
> 
> | 語意 URI 協議 | 當前專案實體路徑 (相對於專案根目錄) | 狀態 |
> | :--- | :--- | :--- |
> | **`project://`** | `./` | `[ACTIVE]` |
> | **`yscb://`** | `./ys_codebase` | `[ACTIVE]` |
> | **`plans://`** | `./plans` | `[!UNDEFINED]` |
> | **`archive://`** | `./archive` | `[!UNDEFINED]` |
> | **`docs://`** | `./docs` | `[!UNDEFINED]` |
> 
> 🛠️ **CLI 動態解析指令**：`python yscb.py uri resolve <uri>`（例：`python yscb.py uri resolve project://AGENTS.md`）

# 接續開發計畫工作流 (Continue)

本 Workflow 用於從一個**已存在但尚未完成**的開發計畫接續工作。所有階段的執行規範請嚴格遵循 [標準開發作業流程 (NewPlan)](`__#{module://agents-workflow/assets/workflows/NewPlan.md}__`)。

---

## 🚀 執行步驟

### 步驟 1：定位目標計畫目錄與狀態掃描

1. 檢視 `workflow.plans://` 計畫目錄下的進行中計畫。
2. 若使用者未明確指定計畫名稱：
   - 僅有一個進行中計畫 ➔ 自動定位為目標。
   - 多個進行中計畫 ➔ 列出所有計畫名稱與狀態，詢問開發者要接續哪一個。

---

### 步驟 2：檢查 `handoff.md` 現場交接快照 (Handoff Detection)

檢查目標計畫目錄下是否存在 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)：
- **若存在 `handoff.md`**：
  1. 優先讀取 `handoff.md`，提取其中的「現場已完成事項」、「進行中待辦」、「踩坑與注意事項」與「下一次接手第 1 步」。
  2. 依據現場快照直接還原斷點上下文，無需漫無目的地掃描所有歷史代碼。
- **若無 `handoff.md`**：
  - 進入步驟 3 進行標準 Track 與 Phase 結構化判定。

---

### 步驟 3：判定計畫層級與 Track 模式

根據工作目錄中的關鍵檔案判定計畫層級：

| 判定依據 | 計畫層級 / Track | 進入判定分支 |
| :--- | :--- | :--- |
| 存在 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) | **Level 2：Umbrella 分類型主計畫** | ➔ 進入 **步驟 3-U** |
| 存在 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`) | **Level 0：Fast Track** | ➔ 進入 **步驟 3-F** |
| 存在 `P00` / `P01` ~ `P07` | **Level 1：Full Track (或獨立子計畫)** | ➔ 進入 **步驟 3-T** |

---

#### 步驟 3-U：Umbrella 主計畫與子計畫定位

1. 讀取主計畫的 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) 與 [`P00_semantic_requirements.md`](`__#{module://agents-workflow/assets/templates/P00_semantic_requirements.md}__`)。
2. 檢查子計畫清單矩陣：
   - 尋找當前處於 `進行中`、`In Progress`、`Planning` 或 `未開始` 的第一個子計畫目錄 `sub_{編號}_{名稱}/`。
   - 若所有既有子計畫均已 Completed 但主計畫尚有後續階段 ➔ 提示開發者是否開立下一個 `sub_XX` 子計畫。
3. 進入當前目標子計畫目錄，檢查該子計畫是否含有 [`handoff.md`](`__#{module://agents-workflow/assets/templates/handoff.md}__`)，若無則依其檔案結構進入 **步驟 3-T** (Full Track) 或 **步驟 3-F** (Fast Track) 判定進度。

---

#### 步驟 3-T：Full Track 進度判定

根據目標工作目錄中已存在的產出物檔案及其狀態標頭判定：

| 已存在的最新檔案 | 檔案狀態為 `Confirmed` / `Passed` | 檔案狀態為 `Discussing` / `Draft` / `Pending` | 判定結果 |
| :--- | :---: | :---: | :--- |
| [`P00_semantic_requirements.md`](`__#{module://agents-workflow/assets/templates/P00_semantic_requirements.md}__`) | ✅ | — | Phase 0 已確認，尚未進行分流或進入 Phase 1 |
| [`P00_semantic_requirements.md`](`__#{module://agents-workflow/assets/templates/P00_semantic_requirements.md}__`) | — | ✅ | Phase 0 需求討論進行中 |
| [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`) | ✅ | — | Phase 1 已完成，應從 Phase 2 開始 |
| [`P01_requirements_spec.md`](`__#{module://agents-workflow/assets/templates/P01_requirements_spec.md}__`) | — | ✅ | Phase 1 進行中，應接續 Phase 1 |
| [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`) | ✅ | — | Phase 2 已完成，應從 Phase 3 開始 |
| [`P02_architecture_plan.md`](`__#{module://agents-workflow/assets/templates/P02_architecture_plan.md}__`) | — | ✅ | Phase 2 進行中，應接續 Phase 2 |
| [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`) | ✅ | — | Phase 3 已完成，應從 Phase 4 開始 |
| [`P03_api_spec.md`](`__#{module://agents-workflow/assets/templates/P03_api_spec.md}__`) | — | ✅ | Phase 3 進行中，應接續 Phase 3 |
| [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) | ✅ | — | Phase 4 已定稿，應進入 Phase 5 開始實作 |
| [`P04_implementation_plan.md`](`__#{module://agents-workflow/assets/templates/P04_implementation_plan.md}__`) | — | ✅ | Phase 4 Review 進行中 |
| [`P05_task.md`](`__#{module://agents-workflow/assets/templates/P05_task.md}__`) | — | — | Phase 5 實作中（讀取 `[x]` / `[ ]` 定位中斷點） |
| [`P06_test_plan.md`](`__#{module://agents-workflow/assets/templates/P06_test_plan.md}__`) | — | — | Phase 6 測試驗證中（檢查實測狀態與 UX 驗證關卡） |
| [`P07_walkthrough.md`](`__#{module://agents-workflow/assets/templates/P07_walkthrough.md}__`) | — | — | Phase 7 Review 中（若已完成應已歸檔） |

---

#### 步驟 3-F：Fast Track 進度判定

根據 [`fast_track_plan.md`](`__#{module://agents-workflow/assets/templates/fast_track_plan.md}__`) 的狀態欄位判定：

| 狀態 | 判定結果 |
| :--- | :--- |
| `Planning` | FT-1 變更規劃進行中 |
| `Implementing` | FT-2 程式碼實作進行中（檢查清單標記定位具體進度） |
| `Reviewing` | FT-3 品質審查與驗證進行中 |
| `Completed` | 已完成（待歸檔） |

---

### 步驟 4：載入計畫上下文與決策脈絡

1. 優先讀取工作目錄中的 [`changelog.md`](`__#{module://agents-workflow/assets/templates/changelog.md}__`)（若為子計畫亦需讀取主目錄之 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`)），掌握關鍵決策 (`[{Phase}:DR-XX]`) 與演進歷程。
2. 讀取當前 Phase 對應之文件內容，明確當前核心任務。

---

### 步驟 5：呈遞接續進度簡報並確認

向開發者呈現接續狀態簡報：

```markdown
## 📋 計畫接續簡報

- **計畫名稱**：`{目錄名稱}`
- **計畫層級**：Level 2 Umbrella 主計畫 / Level 1 獨立 Full Track / Level 0 Fast Track / 模式 A 衍生子計畫
- **交接快照 (Handoff)**：已載入 handoff.md / 無交接檔案（依 Phase 狀態判定）
- **當前進度**：Phase {N} 已完成 / Phase {N} 進行中（具體位置：{區塊名稱}）
- **關鍵注意事項 (Gotchas)**：{從 handoff.md 或 changelog 提取之踩坑點}
- **下一步動作**：{極精確的下一步重啟行動指引}
```

詢問開發者是否確認開始接續，**立即 End Turn 等待確認**。

---

