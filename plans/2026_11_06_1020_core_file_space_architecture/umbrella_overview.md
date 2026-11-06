# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_11_06_1020_core_file_space_architecture  
> 建立日期：2026-11-06  
> 計畫狀態：In Progress  
> Umbrella 模式：Incremental (增量演進型)  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：將檔案空間管理 (`file-space`) 全面升級並直接內聚併入 `module:core`，建立正交、完整且零順序陷阱的空間定義機制，分階段建構 L0 原子操作與 CLI、衍生複合能力，並無縫對接選配之 `module:server` 常駐監控 Hook（在無 `server` 環境下天然純本地運作不觸發常駐依賴）。
- **架構邊界**：
  - **空間定義五大支柱定案**：
    1. **拓撲與過濾 (`entries` / `include` / `exclude`)**：`entries` 支援多入口（資料夾或單一檔案，支援語意 URI）；`include` 預設 `["*"]`；`exclude` 優先級高於 `include`。規則匹配三座標相容：① 語意 URI 前綴、② 含 `/` 之相對路徑（`project://` 與所屬 `entry` 雙基準相容）、③ 不含 `/` 之任意層級檔名或目錄名。
    2. **顯式預設集 (`presets`)**：支援定義與顯式引用 `{include, exclude}` 規則包（含內建動態 `"@gitignore"` 預設集），無隱式全域 `default_presets`。
    3. **空間組合 (`compose`)**：支援透過 `compose: [...]` 合併既有空間評估後之檔案結果集（含 DAG 循環檢測），並可疊加自身 `entries` / `presets` / `include` / `exclude` 進行補充與二次過濾。
    4. **命名空間隔離與聯集引用 (`<owner>/<space>` vs `<space>`)**：模組貢獻自動命名為 `<module>/<space>`、專案設定命名為 `project/<space>`，定義端互不覆蓋、零載入順序衝突；引用時輸入 `<module>/<space>` 或 `project/<space>` 為精準定位，輸入短名 `<space>` 則自動代表所有同名空間之聯集。
    5. **與 VFS Guard 職責解耦**：Space 專注於集合拓撲、過濾、快照與變更追蹤（僅保留 `description` 描述屬性）；單點式防誤改物理鎖（臨時解鎖、寫入後上鎖）獨立歸屬 `core.vfs` File Guard 範疇。
  - **三階段增量推進策略**：
    1. **階段一 (`sub_01`)**：建立核心原子功能（空間與預設集解析、三座標預編譯過濾、零冗餘掃描與基礎查詢原語），所有核心能力皆可透過原子操作達成，並暴露為 L0 CLI。
    2. **階段二 (`sub_02`)**：基於 L0 原子能力建構組合與進階複合功能（如空間組合展開、快照指紋、差異對比、導航與規則診斷等），以及下游模組遷移對齊。
    3. **階段三 (`sub_03`)**：對接 `module:server` Hook 與背景常駐增量同步機制（天然在無 `server` 環境下不觸發且維持 100% 功能可用）。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_atomic_core_and_l0_cli` | Full Track | `Completed` | 內聚於 `core` 之 Space / Preset 定義解析、`<owner>/<space>` 與 `<space>` 聯集尋址、`entries`/`include`/`exclude` 三座標匹配原子引擎與 L0 CLI 介面 (`core file-space` / `fs`) |
| **sub_02** | `sub_02_composite_capabilities` | Full Track | `Pending` | 基於核心原子操作衍生之複合功能（`compose` 組合視圖、快照與差異感知、進階 CLI 導航/診斷） |
| **sub_03** | `sub_03_server_hook_integration` | Full Track | `Pending` | 對接 `module:server` 常駐監控與事件 Hook 整合（無 `server` 時天然靜默退回純本地原子運作） |
| **sub_04** | `sub_04_ecosystem_migration_and_legacy_removal` | Full Track | `Pending` | 遷移全倉既有模組（`ast`、`knowledge-db`、`gdrive-support`、`agents-workflow`）SDK 與 `contributes` 至 `core.space`，並正式退役移除舊 `module:file-space` |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1 (`sub_01`)**：完成 Space 原子定義引擎與 L0 CLI 建置並通過沙盒驗證
- [ ] **里程碑 2 (`sub_02`)**：完成基於原子能力之複合功能建置
- [ ] **里程碑 3 (`sub_03`)**：完成 `server` Hook 常駐增量整合
- [ ] **里程碑 4 (`sub_04`)**：完成全倉既有模組 SDK 遷移並移除舊 `module:file-space`
