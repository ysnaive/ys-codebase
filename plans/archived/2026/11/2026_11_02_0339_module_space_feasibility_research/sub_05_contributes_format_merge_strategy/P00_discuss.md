# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`core.contributes` 格式驅動合併策略與 `file-space` 來源追蹤修正  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 「如果兩個模組或是模組+專案都設定了同一個名稱的 contributes，會發生什麼事?」
  2. 「1. 修正 2. 我認為是不是應該由 contributes format 提供者決定?」
  3. 「1. 你覺得哪個自由度和維護性比較佳? 2. 先同一套策略就好 3. 是」
  4. 「file_patterns 是 extend， /auto」
- **核心目標**：
  1. **由 `contributes` Format Provider（`_format.json`）決定同名合併策略**：擴充 `core.validator.ContributesValidator` 的輕量型別簽名 DSL，支援行內後綴 `| <strategy>`（`merge`、`extend`、`replace`、`unique`）及擴充點頂層可選 `"merge"` 屬性，並由 `core.contributes` 依據目標模組 `_format.json` 執行 Schema 驅動合併。
  2. **完整記錄跨模組與專案之貢獻來源清單 (`__providers__`)**：在 `core.contributes` 聚合模組與專案覆寫 (`config://<target>/contribute.json`) 時，為專案覆寫注入 `"__provider__": "project"`，並在字典合併時自動累積保序去重的 `"__providers__": [...]` 清單。
  3. **修正 `FileSpaceManager` 重複合併與 `origin` 誤判缺陷**：利用 `core.contributes` 強化後的 `"__providers__"` 與格式驅動合併，消除 `FileSpaceManager` 對 `config://file-space/contribute.json` 的二次重複疊加，使純專案空間正確判定為 `origin=project`（而非被誤標為 `merged`），多來源合併空間完整保留所有 `owner_modules`。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接擴充 `ys_codebase/source/core/core/validator.py` 之 `ContributesValidator.parse_type_signature` 與 `validate_format_schema`。
  - 直接升級 `ys_codebase/source/core/core/contributes.py` 之 `_tag_provider`、`_deep_merge` 與 `ContributesAggregator`。
  - 直接收斂 `ys_codebase/source/file-space/file_space/manager.py` 之空間探索與來源判定邏輯。
- **邊界排除 (Explicitly Excluded)**：
  - 暫不區分「模組間合併」與「專案覆寫」之雙軌差異策略（統一使用同一套 `| <strategy>` 策略，惟 `unique` 僅禁止不同模組註冊同名 Key、允許 `project` 覆寫或合併）。
  - 不引入任何第三方 Schema 套件（維持 100% Python 標準庫實現）。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/validator.py`
  - `ys_codebase/source/core/core/contributes.py`
  - `ys_codebase/source/file-space/contributes/_format.json`
  - `ys_codebase/source/file-space/file_space/manager.py`
  - `ys_codebase/source/dev/assets/skills/yscb-module-dev/references/contributes_guide.md`
  - `docs/core/contributes_architecture.md`、`docs/dev/reference/contributes_format.md` 及 `docs/file-space/README.md`
  - `ys_codebase/source/core/tests/test_validator.py`、`test_contributes.py` 與 `ys_codebase/source/file-space/tests/test_file_space_manager.py`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採行 Inline DSL 後綴 `| <strategy>` 搭配擴充點頂層可選 `"merge"` 屬性**：
  - 於 `_format.json` 型別簽名字串尾端支援 `| <strategy>`（如 `"list[str]! | extend"`、`"$FileSpaceDef | merge"`），並支援擴充點定義物件可選 `"merge"` 欄位。
  - 合法策略集合為 `{"merge", "extend", "replace", "unique"}`：
    - `merge`：適用於 `dict` / `$Type`，遞迴合併子欄位（預設於 `dict` 與 `$Type`）。
    - `extend`：適用於 `list`，保序去重附加（預設於 `list`）。
    - `replace`：適用於純量、`list`、`dict`、`$Type`，後者直接整包覆寫前者（預設於純量）。
    - `unique`：適用於字典萬用鍵 `"*"` 或映射結構，禁止不同模組（Donor A 與 Donor B）定義同名 Key（記錄告警/錯誤並拒絕後者模組覆蓋前者模組），但允許 `project`（`config://<target>/contribute.json`）對既有模組定義進行覆寫或合併。
- **[P00:DR-02] 標準化 `__provider__` 與 `__providers__` 多來源追蹤**：
  - `_tag_provider` 為每個貢獻字典注入 `"__provider__": donor_name` 與 `"__providers__": [donor_name]`；專案層級 `config://<target>/contribute.json` 統一以 `donor_name="project"` 標記。
  - 當兩個字典合併時，自動將雙方之 `"__providers__"` 保序去重合併，且將 `"__provider__"` 更新為最新覆疊方。
- **[P00:DR-03] `file-space/contributes/_format.json` 策略配置與 `FileSpaceManager` 來源收斂**：
  - `FileSpaceDef` 明確宣告 `"include": "list[str]! | extend"`、`"exclude": "list[str]? | extend"`、`"file_patterns": "list[str]? | extend"`，`"spaces"` 映射宣告 `"*": "$FileSpaceDef | merge"`。
  - `FileSpaceManager` 當使用預設環境探索（未傳入顯式測試 `spaces_config` / `contributed_spaces` 且未指定獨立 `_custom_config_dir`）時，直接由 `core.contributes.get("file-space")` 取得已依 `_format.json` 合併完畢之空間定義，並依據 `"__providers__"` 判定 `origin`：
    - 僅含 `"project"` $\rightarrow$ `FileSpaceOrigin.PROJECT`
    - 不含 `"project"` $\rightarrow$ `FileSpaceOrigin.MODULE`
    - 同時含模組與 `"project"` $\rightarrow$ `FileSpaceOrigin.MERGED`
  - 若為單元測試顯式注入 `contributed_spaces` / `spaces_config` 或 `_custom_config_dir`，亦共用同一套合併與 `origin` 判定邏輯，確保 100% 行為一致。

---

## 3. 開放議題與確認紀錄

- 開發者已全數確認：採方案 A（Inline DSL `| <strategy>`）、先採同一套策略、`file_patterns` 為 `extend`、立為 `sub_05` 並啟動 `/auto` 推進。
