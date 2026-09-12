# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Contributes 宣告架構升級與 Schema 剛性校驗 (Contributes Schema & Rigid Validation)  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 計畫類型：Feature / Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 現行 contributes 完全靠書面協議定義，發生更動或格式錯誤時缺乏剛性反饋，排查與除錯成本高昂。
  - 規劃設計為 `modules://@/contributes/`（即 `module.source://<mod>/contributes/`）中添加/移植：
    - `_format.json`：定義如何為這個模組做貢獻（取代純文字說明書）。
    - `_manifest.md`：紀錄該模組貢獻了什麼給其他模組。
    - 預計這兩個檔案也要包含在 `dev create module` 的骨架中。
  - `_format.json` 的格式預計為：
    ```json
    {
        "<contribute n>": {
           "description": "",
           "format": { ... }
        }
    }
    ```
  - 添加核心 command `contributes` 和 SDK：
    - `list`：展示各模組提供之注入用途。
    - `check [module | file uri]`：檢查各模組提供之 contributes 語法是否正確（範例與介面支援 First-Class 語意 URI 協議）。
  - 於 `dev check` 和 `core` 運行期添加剛性檢測：
    - 於 `modules://<module>/contributes/` 中所定義的 `<target>.json` 僅能包含對 `<target>` 的注入。
    - 於 `config://<module>/contribute.json` 所定義的僅能包含對於 `<module>` 之注入。
  - 移除 `commands` contribute format 舊有的 `phases` 欄位。
  - 先行產出第三方開發者視角之參考手冊置於 `docs/dev/reference/contributes_format.md`。
- **核心目標**：
  - 建立 100% Python 標準庫、零第三方依賴的輕量宣告式 Schema DSL 與校驗引擎。
  - 提供 `contributes list` 與 `contributes check` CLI 指令與對應 SDK，杜絕靜默吞錯與欄位拼寫錯誤。
  - 實現剛性單向邊界防線（Pre-flight 靜態阻斷 + Runtime 髒資料過濾），徹底解決越權注入。
  - 達成全生態系 5 大模組 contributes 結構遷移與腳手架標準化。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁引入任何第三方驗證庫（如 `pydantic`、外部 `jsonschema` 套件）。
  - 不更動微內核底層 `ContributesAggregator` 核心拓撲合併演算法，僅在其邊界處增加驗證與過濾層。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 檔案拓撲與底線命名空間隔離**：
  在 `contributes/` 目錄中，以 `_` 開頭作為元檔案命名空間保護：
  - `_format.json`（Ingress / 輸入契約）：宣告本模組接受何種結構之貢獻。
  - `_manifest.md`（Egress / 輸出清冊）：記錄本模組對外貢獻了哪些能力與協議。
  - `<target>.json`（Egress / 實際注入體）：實際向目標模組注入之數據宣告。
- **[P00:DR-02] 輕量型別 DSL (Type Signature DSL)**：
  捨棄冗長的標準 JSON Schema，設計 100% 原生解析之輕量型別表達式：
  - 基礎型別：`str`, `int`, `bool`, `float`, `any`（支援 `string`, `boolean`, `integer` 別名容錯）。
  - 修飾符：`!`（必填）、`?`（選填，未加亦預設選填）。
  - 列舉與預設值：`enum(a, b, c)`、`= <default_value>`。
  - 複合容器：物件清單 `[ { ... } ]`、動態鍵字典 `"*": <schema>`。
  - 樹狀遞迴支援：透過 `_types` 共用結構區與 `$TypeName` 參照，完美支援層級化 CLI 指令樹（`cmd`, `args`, 2 層級 `options`, `usage` 等）。
- **[P00:DR-03] 雙重剛性邊界防線 (Static Pre-flight + Runtime Aggregator)**：
  - 靜態守門（`dev check`）：新增 `ContributesCheckPass`，若發現未定義欄位、型別不符、跨目標越權注入，直接 Exit Code 1 阻斷，禁止打包與發布。
  - 運行期守門（`core.contributes.ContributesAggregator`）：移除原有 `except Exception: pass` 盲目吞噬，遇格式違規記錄錯誤日誌並過濾無效鍵，防止髒資料進入 cache。
- **[P00:DR-04] 核心指令與 SDK 邊界**：
  在 `core` 模組註冊 `contributes list` 與 `contributes check`，提供公開 SDK（`get_format`, `validate`, `list_points`），並全線支援 `module.source://` 與 `config://` 語意 URI。
- **[P00:DR-05] 腳手架預置與生態系平滑遷移**：
  - `dev create module` 自動產生帶有教學範例的 `_format.json` 與 `_manifest.md`。
  - 將 5 大模組現有 `contributes.format.md` 規格精確物化為 `_format.json`，並建立對應 `_manifest.md`。

---

## 3. 開放議題與確認紀錄

- [x] 是否移除 `commands` 中的 `phases` 欄位？➔ 確認移除，改由 `tier` 與 `usage (pros/cons)` 驅動。
- [x] `commands` 結構如何精確表達？➔ 採用 `_types` + `*` 通配符 + `$CommandNode` 遞迴樹狀結構。
- [x] CLI 與檔案檢驗介面規範？➔ 支援模組名與 First-Class 語意 URI（如 `module.source://`）。
- [x] 第三方開發者文檔規範？➔ 已完成並存於 `docs/dev/reference/contributes_format.md`。
