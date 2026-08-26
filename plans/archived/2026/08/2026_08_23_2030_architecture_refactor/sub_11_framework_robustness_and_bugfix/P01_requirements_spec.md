# 需求規格說明書 (Requirements Specification)

> 功能名稱：套件框架健壯性強化與缺陷修復 (Framework Robustness & Bug Fixes)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P00/調研報告：[P00_semantic_requirements.md](./P00_semantic_requirements.md), [R01_framework_architecture_and_logic_audit.md](./R01_framework_architecture_and_logic_audit.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格說明 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- |
| **FR-01** | 剛性組態載入與沙盒防穿透 | `yscb.py:load_config` 徹底移除 `while True` 向上遞迴爬目錄樹，剛性僅探測 `yscb.py` 同層之 `yscb.config.json`，徹底消除沙盒執行時向上逃逸偷取外層宿主組態之風險。 | P00 §1 動機 1<br/>P00 §2 期望 1 |
| **FR-02** | 剛性注入引擎與空間邊界隔離 | `core.contributes.ContributesAggregator` 嚴格僅讀取 `modules/` 運行空間之正式產物與 `config.root://` 模組專屬設定，全面移除對 `module.source.root://` 與 `project://` 的軟相容穿透 fallback，違反邊界時直接拋錯阻斷。 | P00 §1 動機 1<br/>P00 §2 期望 1 |
| **FR-03** | 剛性 URI 解算器與非標準格式攔截 | `core.uri.resolve()` 嚴格僅接受合法語意 URI (`token://...`) 或作業系統絕對路徑，移除非協議字串雙重猜測（原回退至 `proj_d` 或 `yscb_dir`），非標準格式直接拋出 `ValueError`。 | P00 §1 動機 1<br/>P00 §2 期望 1 |
| **FR-04** | 安裝器與沙盒宿主剛性錨定 | 1. `core.installer` 移除 `default_provider` 之 3 層 fallback 與硬編碼後門（`"./ys_codebase/build"`），組態缺少時明確報錯阻斷。<br/>2. `dev.sandbox` 剛性定位 `host_d/yscb.py`，移除宿主路徑多重猜測。 | P00 §1 動機 1<br/>P00 §2 期望 1 |
| **FR-05** | SemVer 2.0.0 版本運算器與依賴求解 | 1. 建立純 Python 標準庫之 `core.semver` 子模組，支援版本解析（`major.minor.patch-prerelease`）、數值排序（物理保證 `"1.10.0" > "1.9.0"`）與範圍過濾（支援 `>=, >, <=, <, ==, ~=, *`）。<br/>2. `core.installer:cmd_update` 與 `core.engine:act_solve_deps` 全面接入 SemVer 進行最高合規版本解算與更新。 | P00 §1 動機 2<br/>P00 §2 期望 2 |
| **FR-06** | 微內核物理拓撲命名對齊與註解補齊 | 1. 將 `core.uri._find_host_config()` 全域重構為 **`_get_host_config()`**，杜絕「推導」歧義，與物理拓撲概念剛性對齊。<br/>2. 於 `core.uri` 與 `core.engine` 補齊微內核常量自定位、零 I/O Fast-Path 與 OS 原子鎖設計意圖註解。 | P00 §1 動機 3<br/>P00 §2 期望 3 |
| **FR-07** | `ExecutionContext` 單一真相來源收斂 | 1. 採方案 B：將最新完整版不可變 `@dataclass(frozen=True)` 之 `ExecutionContext` 統一定義在 `core/core/context.py` 作為 SSOT。<br/>2. `core/core/uri.py` 透過 `from core.context import ExecutionContext` 重新導出，確保既有呼叫端 100% 向後相容。 | P00 §1 動機 4<br/>P00 §2 期望 4 |
| **FR-08** | 雙層組態快照與完美回滾閉環 | 1. `core.engine:act_snapshot` 範圍擴充納入 `config.root://`（各模組專屬設定目錄）。<br/>2. `core.engine:act_restore_snapshot` 還原 `yscb.config.json` 時，同步完整還原 `config/` 目錄，達成 100% 純淨的組態級回滾。 | P00 §1 動機 4<br/>P00 §2 期望 4 |
| **FR-09** | Provider 精確版本比對與防污染 | `core.engine:act_download` 下載本地 Provider 時，嚴格比對特定版本目錄 `provider/{mod}/{ver}`，若傳入模組根目錄則 Double-Check 內部 `manifest.json` 版本，杜絕整包多版本巢狀拷貝污染。 | P00 §1 動機 4<br/>P00 §2 期望 4 |
| **FR-10** | URI 全域狀態 Context Manager 防護 | 於 `core.uri` 提供 `@contextmanager` 封裝（`module_scope(mod)` 與 `host_scope(path)`），在區塊退出時以 `finally` 保證 100% 還原舊全域狀態，杜絕測試與 Hook 污染。 | P00 §1 動機 4<br/>P00 §2 期望 4 |
| **FR-11** | 沙盒模組動態版本繼承 | `dev.sandbox` 在拷貝模組時，動態讀取該模組真實 `manifest.json` 之 `version` 與 `description` 填入沙盒 `yscb.config.json`，取代硬編碼 `"1.0.0"`。 | P00 §1 動機 4<br/>P00 §2 期望 4 |
| **FR-12** | 測試報表精準計數與失敗清單展示 | 1. `dev.runner` 依據 TestCase 類別（Contract / Custom）精準分離成功/失敗計數，杜絕交叉誤扣。<br/>2. 若有失敗或錯誤案例，以獨立清單區塊清楚列出「模組名、測試方法名、失敗類型與錯誤摘要」，提升 CLI 除錯體驗。 | P00 §1 動機 4<br/>P00 §2 期望 4 |

---

## 2. 邊界與異常情況處理 (Edge Cases)

| 邊界編號 | 邊界情境說明 | 防禦處置與預期行為 | 對應需求 |
| :--- | :--- | :--- | :--- |
| **EC-01** | 無效或非標準 URI 字串傳入 | 傳入非 `xxx://...` 協議且非作業系統絕對路徑之字串（如 `"some/rel/path"`）至 `uri.resolve()` 時，必須拋出 `ValueError`，嚴禁進行模糊推測。 | FR-03 |
| **EC-02** | SemVer 版本字串語法畸形 | 傳入不合法版本字串（如 `"v1.x.y"`, `"1.0"`, `"invalid"`）至 SemVer 解析器時，拋出 `ValueError` 並明確提示畸形版本格式。 | FR-05 |
| **EC-03** | 依賴約束無可匹配版本 | 當 Provider 中所有可用版本皆無法滿足 `version_constraint`（如要求 `">=2.0.0"` 但最高僅 `"1.5.0"`）時，`act_solve_deps` 拋出 `RuntimeError` 說明無可匹配之合規版本。 | FR-05 |
| **EC-04** | 雙層快照還原時目標目錄缺失 | 若還原快照時當前宿主環境 `config/` 或 `yscb.config.json` 不存在，快照還原器應自動建立目錄並乾淨物化，不得報錯崩潰。 | FR-08 |
| **EC-05** | 本地 Provider 目錄無目標版本且無 manifest | 若本地 Provider 目錄不存在目標版本且無合法 `manifest.json`，`act_download` 立即拋出 `FileNotFoundError` 阻斷。 | FR-09 |
| **EC-06** | 上下文管理器內部拋出執行期例外 | `module_scope` 或 `host_scope` 內部拋出例外時，`finally` 區塊仍必須保證 100% 還原全域狀態，且將原始例外正常向上拋出。 | FR-10 |

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01（100% Python 標準庫）**：所有新增模組與演算法（包含 SemVer 2.0.0 解析比對器）100% 基於 Python 3.10+ 標準庫，零第三方 pip 套件依賴。
- **NFR-02（微秒級版本運算效能）**：單次 SemVer 解析、比對與版本範圍過濾耗時 $\le 0.1\text{ ms}$。
- **NFR-03（100% 回歸測試通過）**：現有 48 項單元與整合測試及本計畫新增測試案例全數 100% 綠燈通過。

---

## 4. 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充功能名稱 | 觸發模式 | 判定結果 | 評估理由 |
| :--- | :---: | :---: | :--- |
| `dogfooding_pipeline_ext` | always | **Excluded (排除)** | 本計畫聚焦框架本體健壯性加固與缺陷修復，遵循標準閉環流水線。 |

---

## 5. 踩坑紀錄與設計註記巡檢 (Design Notes Pre-check)

- **DN-01（不可變鏡像庫保證）**：`mirror://` 為不可變版本庫，任何安裝/升級不得直接原地篡改既有版本目錄。
- **DN-02（微內核拓撲不變量）**：`core.uri._get_yscb_root()` 往上 3 層在微內核派發鏈條下為物理拓撲恆等式，是 Fast-Path 零 I/O 解析基礎。
- **DN-03（全域環境變數唯一性）**：全系統唯一的外部環境變數為 `YSCB_HOST_DIR`（用於跨目錄執行錨定），不引入多餘環境變數。
