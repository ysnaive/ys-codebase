# 語意化需求書 (Semantic Requirements)

> 功能名稱：模組化體系宏觀架構重構與規範白皮書 (Module Architecture Specification)  
> 建立日期：2026-08-23  
> 計畫類型：Refactor / Architecture  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Refactor / Architecture] 語意化需求

### 現況痛點與重構動機 (Core Motivations)

- **動機 1（建立純粹的微內核與模組化體系）**：跳脫歷史局部解法與單檔過大包袱，建立「超薄宿主 (Ultra-Thin Host) + 自治能力模組 (Modular Capabilities)」的極簡自舉架構。
- **動機 2（消除特例與雙重標準）**：確立「一切皆模組、零特例特權」原則，連 `core` 本身亦透過相依拓撲排序實現第 1 順位自我注入 (Self-Injection)。
- **動機 3（多維空間與路徑確定性）**：建立語意 URI 空間（`project://`, `yscb://`, `mirror://`, `cache://`, `config://`, `module://`）與路徑佔位符（`{module}`），嚴禁從未追蹤的 local 讀取路徑。

### 期望演進形態 (Desired End State)

- **期望 1（超薄單檔宿主 `yscb.py`）**：體積極致輕量（約百餘行），內建 2 項原生指令 `init` 與 `self-update`，其餘所有指令皆動態轉接至 `modules/{module}/scripts/cli.py`。
- **期望 2（`core` 基礎模組化）**：承接 7 項 Installer 指令集（`install`, `update`, `remove`, `list`, `status`, `rollback`, `reload`）與全域語意 URI 系統。
- **期望 3（5 大來源聚合貢獻體系）**：模組可透過 `manifest.json`、`contributes.{module}.json`、`config.project.json` 等宣告擴充，具備清晰的覆蓋矩陣。

### 範疇界定 (Scope Boundary)

#### 包含範疇 (In-Scope)
1. **單檔入口 (`yscb.py`)**：
   - 超薄宿主實現（約百餘行，100% 原生零相依）。
   - 內建原生指令 `init` 與 `self-update`（自舉建立環境、下載 core，以及宿主單檔自我更新）。
   - 泛用 CLI 動態轉接器（`yscb.py {module} {any}` 轉接至 `modules/{module}/scripts/cli.py`）。
2. **核心基礎模組 (`core`)**：
   - 承接 7 項 Installer 指令集（`install`, `update`, `remove`, `list`, `status`, `rollback`, `reload`）。
   - 語意 URI 系統與路徑佔位符（`{module}`、`project://`, `yscb://`, `mirror://`, `temp://`, `snapshot://`, `cache://`, `config://`, `module://` 等）。
   - 模組 contributes 5 大檢索來源聚合與自注入機制。
3. **規範化 test 測試流程 (`test/`)**：
   - 建立標準化迴歸測試套件，涵蓋單檔自舉、套件管理、CLI 派發與 URI 完整生命週期驗證。

#### 排除範疇 (Out-of-Scope)
- **`agents-workflow` 模組**：暫不在本次開發範圍，重構與測試期間移至暫存區隔離，防止干擾。
- **其他開發工具類模組**：全數回歸標準模組化體系（無任何非模組特例），於後續獨立計畫討論。

### 不可破壞的約束 (Hard Constraints)

- **約束 1**：**零外部依賴 (Zero External Dependency)** — 宿主中控與核心 SDK 100% 維持 Python 3.8+ 標準庫。
- **約束 2**：**單檔自舉完整性 (Single-File Bootstrapping)** — 下游專案僅需單一 `yscb.py` 即可完成全套環境自舉與管理。
- **約束 3**：**路徑版控確定性 (Path Determinism)** — 任何路徑相關設定僅允許讀取 `config.project.json`，嚴禁自 `config.local.json` 讀取。
- **約束 4**：**回歸測試通過率 100%** — 維持全量單元/整合測試與沙盒 E2E 驗證 100% 通過。

---

## 開放議題紀錄 (Open Questions)

| # | 議題描述 | 狀態 | 結論 |
|---|---------|------|------|
| 1 | `yscb.py` 宿主與 `core` 的職責劃分 | ✅ 已定案 | `yscb.py` 僅保留 `init`，其餘 8 項 Installer 指令與 CLI 派發全數委派至 `core` |
| 2 | `yscb://` 與 `yscb.config.json` 的關係 | ✅ 已定案 | `yscb://` 實體來源定義於 `yscb.config.json` 的 `yscb_root`（由 `init {yscbRoot}` 寫入） |
| 3 | 語意 URI 與路徑佔位符動態解算 | ✅ 已定案 | 支援 `{module}` 佔位符與 5 大檢索來源矩陣，`core` 第一順位拓撲自注入 |
| 4 | 初始化自舉階段之 Event 廣播相依性防呆 | ✅ 已定案 | `yscb.py init` 階段僅在最小基礎設施（路徑解算與檔案系統）就緒後方可觸發事件，`core` 於相依拓撲排在第 1 順位完成自注入後再依序廣播其餘模組（參見 R03 §2.3.3 與 R04 附錄 1）。 |

---

## 討論結束確認 (Discussion Close Gate)

> [!CAUTION]
> **Agent 執行鐵律**：本欄位**必須由開發者明確宣告**後，Agent 才可將狀態更新為 `Confirmed` 並觸發 Track 分流。Agent 嚴禁自行判定討論完整並推進。

- [x] **開發者已明確宣告討論結束**，P00 語意需求內容已完整且正確。

---

## 三大分流層級判定 (Three-Tier Phasing Matrix)

> 本區塊在開發者確認 P00 後填寫。

| 分流層級 | 判定結果 | 適用場景與判定理由 |
| :--- | :--- :--- | :--- |
| **Level 0：Fast Track** | ☐ | 修改檔案 ≤ 2、不變更 Public API、無跨模組依賴、純 Bug 修復或局部微調 |
| **Level 1：Full Track** | ☐ | 單一功能語意、單一使用情境、單一模組的新增或重構 |
| **Level 2：Full Track $\times$ n<br/>(啟用分類型主計畫 Umbrella)** | ☑ | 多個功能語意/情境、跨模組大型架構重構。細化為 9 大子計畫逐步推進 |

> 分流後立即執行：
> - **Level 0 (Fast Track)** → 建立 `FT_plan.md`，P00 內容以引用形式嵌入 FT-1 節。
> - **Level 1 (Full Track)** → 建立 `changelog.md`，進入 Phase 1 規格轉譯。
> - **Level 2 (Umbrella Plan)** → 建立 `umbrella_overview.md`，拆分子計畫目錄 `sub_01`, `sub_02`... 並依序推進。
