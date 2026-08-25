# 語意化需求書 (Semantic Requirements)

> 功能名稱：四段式版本號、雙軌來源庫 (Build vs Release)、四大語意維度、Config 解耦與 Migration 機制重構  
> 建立日期：2026-08-25  
> 計畫類型：Feature / Pipeline / Refactor  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Confirmed (Phase 0 討論完畢，正式定稿推進)  
> 依據調研：[R01](./R01_release_and_build_distinction_analysis.md) / [R02](./R02_release_cli_boundary_and_pipeline_analysis.md) / [R03](./R03_migration_mechanism_and_gitignore_boundary_analysis.md)  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Feature / Pipeline / Refactor] 語意化需求

### 現況痛點與重構動機 (Core Motivations)

- **動機 1（沙盒混血與測試特化複製）**：
  原有來源庫（`build/` 和 `mirror/`）被定義為純淨發布產物（嚴格剝除 tests 與開發檔案），導致 `dev test` 無法透過標準 `yscb install` 獲取測試代碼，被迫自行以 `shutil.copytree` 複製 `source/` 到沙盒，破壞了黑盒測試對稱性與單一真相來源。
- **動機 2（版本號缺乏 Revision 段與開發態表達）**：
  三段式版本號無法表達「本地開發中建置版 (build)」與內部修復號，亦無法支援「無大小比較意義，但不同即覆寫」的覆蓋更新語意。
- **動機 3（Git 邊界粗暴二分與本機污染）**：
  過去 `yscb.config.json` 同時混雜專案依賴標準與本機 provider 覆蓋，導致本機開發時容易將臨時設定提交至 Git，缺乏 `config.project` 與 `config.local` 的解耦。
- **動機 4（缺乏模組 Migration 機制）**：
  `minor` 適配性升級（資料結構微調、config 條目重命名）缺乏標準化生命週期與安全快照回滾保護。

---

### 期望演進形態 (Desired End State)

- **期望 1（四段式版本號體系 `major.minor.patch.revision`）**：
  - **`major`**：破壞性變更，無法適配性升級。
  - **`minor`**：適配性變更，需 migration 升級或增量內容過多需上提級別。
  - **`patch`**：無體感變更，使用者完全無感。
  - **`revision`**：Bug 修復、內部邏輯/效能優化、特殊版本標籤（例：`build`）。
  - **`revision` 運算與存在規則**：
    - 無大小比較意義；同級以最新 Revision 為準。
    - **同 `X.Y.Z` 僅存單一最新 Revision 原則**：在 `release/` 發布庫中，同一個 `major.minor.patch` 嚴格只保留一份最新版本，發布新 Revision 時自動淘汰清理舊修復版，防止碎片化。
    - **常態三元安裝約定**：外部使用者與依賴清冊常態以三元版本號（如 `core@1.0.0`）宣告，微內核自動匹配該 `X.Y.Z` 下的唯一最新 Revision（如 `1.0.0.2`）。
- **期望 2（雙軌來源庫體系與 Hermetic Clean Build）**：
  - **`build://`（空間 ② 本地完整打包）**：`dev build` 將 `source/` 進行 100% 完整打包（保留 `tests/`），產物 revision 強制標記為 `"build"`（例：`1.0.1.build`）。每次建置前清空目標目錄，版本變更時清理舊 build。
  - **`release://`（空間 ③ 唯一預設發布來源庫）**：嚴格依 `.yscbignore` 排除 `tests/` 生成純粹安裝檔，成為系統唯一預設來源庫 (`default_provider` 導向 Git 遠端相對索引)。
  - **`dev release` 發布流水線**：支援四段式 Bump、Pre-flight 4 大守門檢查、Hermetic 發布打包；**`major`/`minor` 預設自動建立 Git Tag (`{mod}/v{ver}`)，`patch`/`revision` 預設不打 Tag**（支援 `--tag` / `--no-tag` 覆蓋）；具備發布失敗原子回滾防護與同 `X.Y.Z` 舊 Revision 自動清理。
- **期望 3（安裝三層降級鏈與 `dev test` 全黑盒流水線）**：
  - 安裝順序：`build://`（本地開發優先）➔ `mirror://`（本地快取次優）➔ `provider`（Git 遠端兜底）。
  - `dev test [--all | <mod>]` 測試前自動執行 `dev build`，沙盒內依三層降級鏈標準 `yscb install`，原地執行測試（零 `source/` 拷貝，100% 黑盒對稱）。
- **期望 4（四大語意維度、Config 雙軌解耦與 Git 邊界）**：
  - 解耦為 `config.project`（專案標準基線，100% Git 追蹤）與 `config.local`（本機覆蓋，.gitignore 忽略）。
  - 模組雙軌消費：現場動態查詢型（🔥 熱更新）vs 啟動依賴注入型（❄️ 冷更新需 reload）。
- **期望 5（模組 Migration 適配性升級生命週期）**：
  - 遷移腳本規範：`module://scripts/migrations/{major}.{minor}.x.py`（語意：從 `{A}.{B-1}.x` 升級為 `{A}.{B}.x`）。
  - 增量階梯調用：更新時依階梯順序調用（如 1.0.0 ➔ 1.3.0 依序調用 1.1.x.py, 1.2.x.py, 1.3.x.py），找不到檔案自動靜默跳過。
  - 升級時建立雙層安全快照，若遷移拋錯則 100% 原子回滾至舊版本乾淨狀態。

---

### 範疇界定 (Scope Boundary)

#### 包含範疇 (In-Scope)
1. **`module:core` (版本運算器、Config 解耦與 Migration 引擎)**：
   - `core.semver`：四段式解析、比較、`"build"` 排序與「不同即覆寫」判定。
   - `core.uri`：註冊 `release://` 與 `release.root://`。
   - `core.config`：實作 `config.project` 與 `config.local` 層疊合併。
   - `core.installer` / `core.engine`：三層安裝降級鏈、Migration 掃描執行與快照回滾。
2. **`module:dev` (建置、發布與測試流水線)**：
   - `dev.builder`：`dev build` 完整打包含 tests；`dev release` 純淨打包與 Git Tag。
   - `dev.testing.sandbox` & `tester`：全黑盒測試流水線。
3. **宿主入口 (`yscb.py`)**：
   - 官方開發端 vs 第三方端自舉判定；`default_provider` 導向 Git 遠端。

#### 排除範疇 (Out-of-Scope)
- 外部雲端/二進位二階段簽署伺服器部署。
