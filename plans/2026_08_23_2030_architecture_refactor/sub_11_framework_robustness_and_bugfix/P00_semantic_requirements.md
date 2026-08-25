# 語意化需求書 (Semantic Requirements)

> 功能名稱：套件框架健壯性強化與缺陷修復 (Framework Robustness & Bug Fixes)  
> 建立日期：2026-08-25  
> 計畫類型：Refactor / Bug Fix / Robustness  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Confirmed (Phase 0 語意需求全數收斂，等候 Phase 0 結案宣告)  
> 擴充項目：none  
> 模板版本：v1.1  

---

## [類型：Refactor / Bug Fix / Robustness] 語意化需求

### 現況痛點與重構動機 (Core Motivations)

- **動機 1（回歸 R01~R05 剛性拓撲，全面清除 6 大軟相容手段）**：
  在落地實作中，為了規避邊界報錯，代碼滋生了「向上無限制爬目錄偷取組態」、「運行期跨界穿透至 source/ 空間抓取未編譯代碼」、「模組配置穿透至專案根目錄」、「resolve 無協議字串雙重猜測」、「installer 3 層 fallback 硬編碼後門」、「沙盒 yscb.py 多重猜測」等 6 大軟相容退化點，違反了 R01~R05 確定的「剛性拓撲與零臆測」鐵律。
- **動機 2（健全真實 SemVer 2.0.0 版本比較與依賴求解）**：
  目前套件管理使用純字串排序（導致 `"1.10.0" < "1.9.0"` 經典降級 Bug），且 `act_solve_deps` 未具備版本約束運算能力（直接將 `">=1.0.0"` 作為路徑搜尋崩潰），需在 `core` 模組引入純 Python 標準庫的 SemVer 2.0.0 運算器。
- **動機 3（補齊微內核物理拓撲設計邏輯註解與命名對齊）**：
  `_find_host_config` 命名帶有「推導猜測」歧義且註解不足，需重構為 `_get_host_config` 並完整註解闡明微內核常量自定位的拓撲剛性保證與零 I/O Fast-Path 意圖。
- **動機 4（雜項代碼整潔與工程邊界收斂）**：
  收斂 `context.py` 作為 `ExecutionContext` 單一真相來源 (SSOT)；擴充 `act_snapshot` 納入 `config/` 目錄以達成雙層組態還原閉環；加固 `act_download` 嚴格版本目錄比對；提供 `core.uri` 上下文管理器防止測試全域狀態污染；沙盒繼承動態讀取真實版本；優化測試報表 contract/custom passed 精準計數並獨立列出失敗清單。

---

### 期望演進形態 (Desired End State)

- **期望 1（100% 剛性拓撲與零臆測）**：
  - `yscb.py:load_config` 剛性錨定同層目錄，徹底移除向上爬樹。
  - `ContributesAggregator` 100% 僅讀取 `modules/` 運行空間產物，徹底移除對 `source/` 與 `project://` 的穿透 fallback。
  - `uri.resolve` 僅接受語意 URI 或絕對路徑，非標準字串直接拋出 `ValueError`。
  - `installer.py` 移除後門硬編碼，`sandbox.py` 剛性定位 `host_d/yscb.py`。
- **期望 2（標準 SemVer 2.0.0 版本運算器）**：
  - 建立輕量純標準庫的 SemVer 模組（支援 `(major, minor, patch, prerelease)` 數值比較、`>=`, `>`, `<=`, `<`, `==`, `~=`, `*` 範圍解析）。
  - `cmd_update` 與 `act_solve_deps` 全面基於標準 SemVer 進行最高合規版本解算與更新。
- **期望 3（物理拓撲設計註解與命名對齊）**：
  - `_find_host_config()` 全面重構為 `_get_host_config()`，並補齊常量自定位物理拓撲註解。
- **期望 4（全域品質、雙層快照還原與精確報表）**：
  - `context.py` 作為 `ExecutionContext` 唯一定義，`uri.py` re-export 保持向後相容。
  - `act_snapshot` / `act_restore_snapshot` 同步備份還原 `config.root://`。
  - `act_download` 嚴格比對版本目錄，杜絕巢狀目錄污染。
  - `uri.py` 提供 `module_scope` / `host_scope` 上下文管理器。
  - 沙盒動態讀取 `manifest.json` 真實版本號。
  - `TestRunner` 精確分離 contract/custom 計數，若有失敗案例單獨列出清單。
  - 全量回歸測試維持 100% 通過。

---

### 範疇界定 (Scope Boundary)

#### 包含範疇 (In-Scope)
1. **宿主入口 (`yscb.py`)**：
   - 移除 `load_config` 向上爬目錄樹，剛性錨定同層 `yscb.config.json`。
2. **`module:core` 核心模組加固**：
   - `core.context`：定義標準不可變 `@dataclass(frozen=True)` 之 `ExecutionContext` 作為 SSOT。
   - `core.uri`：重命名 `_get_host_config()`、補齊物理拓撲註解、`resolve()` 移除非法字串猜測、提供 `module_scope` 與 `host_scope` 上下文管理器、re-export `ExecutionContext`。
   - `core.semver`：新建純標準庫 SemVer 2.0.0 解析、比對與範圍過濾器。
   - `core.engine`：`cmd_update` 與 `act_solve_deps` 接入 SemVer；`act_download` 嚴格比對版本目錄；`act_snapshot` 與 `act_restore_snapshot` 納入 `config.root://` 雙層備份還原。
   - `core.installer`：移除 `default_provider` 硬編碼 fallback。
   - `core.contributes`：移除對 `module.source.root://` 與 `project://` 的穿透 fallback。
3. **`module:dev` 開發與測試引擎加固**：
   - `dev.sandbox`：移除宿主 `yscb.py` 猜測；沙盒繼承模組時動態讀取真實 `version` 與 `description`。
   - `dev.runner`：優化測試報表 contract / custom passed 分類統計，並於有失敗案例時單獨清單列出。
4. **測試驗證 (`tests/`)**：
   - 補充 SemVer 版本解析與範圍比對單元測試、剛性邊界防護測試、雙層快照備份還原測試。

#### 排除範疇 (Out-of-Scope)
- **第三方業務模組開發**（如 `agents-workflow`、`git-tools` 等業務插件）。
- **遠端網路 Package Registry 伺服器建置**（維持本地/HTTP 通用抽象）。
- **引入第三方 Python 套件**（嚴格遵守 100% Python 標準庫約束）。

---

### 不可破壞的約束 (Hard Constraints)

- **約束 1**：**100% Python 標準庫 (Zero External Dependencies)** — 嚴禁引入任何第三方套件（如 `packaging` 或 `semver` pip 套件，100% 以原生純 Python 演算法實作）。
- **約束 2**：**單一真相來源與空間邊界** — `yscb.py` 嚴格僅調度 `modules/`，禁止跨空間穿透至 `source/`。
- **約束 3**：**向後相容性與全量測試通過** — 既有 48 項測試與新增測試必須 100% 保持通過。

---

## 開放議題紀錄 (Open Questions)

| # | 議題描述 | 狀態 | 結論 |
|---|---------|------|------|
| 1 | SemVer 範圍支援的複雜度邊界？ | Closed | 支援 pip/npm 常見標準前綴 `>=, >, <=, <, ==, ~=, *`，由純 Python 標準庫實作，保持極簡。 |
| 2 | `load_config()` 的根邊界判定策略？ | Closed | 剛性錨定 `yscb.py` 同層目錄，徹底移除向上爬樹，杜絕沙盒穿透。 |
| 3 | `ExecutionContext` 的定義放置位置？ | Closed | 採方案 B：由 `core/core/context.py` 作為 SSOT，並由 `core.uri` re-export 保持向後相容。 |
| 4 | `act_snapshot` 快照備份範圍？ | Closed | 擴充快照範圍納入 `config.root://`（各模組設定），還原時同步覆蓋還原，達成雙層組態一致性。 |
| 5 | 全域可變狀態防護策略？ | Closed | 在 `core.uri` 提供 `module_scope` 與 `host_scope` 上下文管理器，退出時自動 `finally` 還原舊狀態。 |

---

## 相關參考文件 (References)
- 宏觀架構調研報告：[R01_framework_architecture_and_logic_audit.md](./R01_framework_architecture_and_logic_audit.md)
