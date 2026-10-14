# API 與介面規格書 (Interface & Protocol Spec)

> 功能名稱：sub_04_docs_standards_and_docstring_alignment  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 介面契約與資料結構 (Interface Contracts & Data Structures)

| 協議名稱 | 語意說明 | 唯讀性 | 物理位置對應 |
| :--- | :--- | :---: | :--- |
| `project://` | 當前專案根目錄 | R/W | 專案根目錄（由 `yscb.project.json` 定位） |
| `module.source://` | 生態系源碼模組目錄 | R/W | `project://source/{module}` |
| `module.mirror://` | 本地運行與熱重載鏡像目錄 | R/W | `project://.modules/{module}` |
| `storage://` | 跨環境共享持久化資料空間 | R/W | `project://.yscb/storage/` |
| `cache://` | 本地本機非受控暫存快取空間 | R/W | `project://.cache/{module}/` |
| `cache.root://` | 頂層暫存快取根目錄 | R/W | `project://.cache/` |
| `config.project://` | 專案宣告式組態檔 | R/W | `project://config/{module}/` |

> [!CAUTION]
> 已廢除之 `temp://`、`module.root://` 與 `mirror://` 禁止再出現在任何規格文檔或代碼註解中。

---

## 2. 核心 API 簽名與詳細規格 (API Signatures)

### Knowledge-DB 8 大標準指令集介面規格

| 指令 | 核心參數 / 選項 | 說明 |
| :--- | :--- | :--- |
| `status` | `[--scan]` `[--diff]` `[--json]` | 檢查索引就緒狀態與檔案異動指紋 |
| `index` | `[--force]` `[--export <path>]` `[--space <sp>]` | 建置 AST/倒排/圖譜索引，可選擇導出 Bundle |
| `search` | `<query>` `[--space]` `[--kind]` `[--lang]` `[--lexical-only]` | 詞彙與向量混合檢索 |
| `callers` | `<symbol>` `[-d/--depth]` `[--json]` | 查詢給定符號的調用者呼叫圖譜 |
| `callees` | `<symbol>` `[-d/--depth]` `[--json]` | 查詢給定符號所調用的下游符號圖譜 |
| `impact` | `<symbol>` `[-d/--depth]` `[--json]` | 評估符號異動影響傳播半徑 |
| `clean` | `[--space <sp>]` | 清除倒排、圖譜、向量二進位快取與狀態快照 |
| `model` | `<status\|download>` `[--force]` | 向量模型離線狀態檢查與預下載 |

---

## 3. 依賴拓撲與實作順序 (Dependency Topology)

1. `STANDARDS.md`（頂層標準修訂）
2. 各模組 `DESIGN_NOTES.md` 與手冊更新
3. `source/server/README.md` 新增
4. `plans/roadmap/` 狀態對齊


