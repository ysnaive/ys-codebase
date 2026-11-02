# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`core.contributes` 格式驅動合併策略與 `file-space` 來源追蹤修正  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `_format.json` 合併策略 DSL 解析與 Meta-Check | 擴充 `ContributesValidator.parse_type_signature(sig)` 解析尾端 `\| <strategy>` 修飾詞（回傳 `"merge_strategy": Optional[str]`），支援 `merge`、`extend`、`replace`、`unique` 四種策略；同步於 `validate_format_schema` 檢驗擴充點頂層可選 `"merge"` 屬性與所有型別簽名中之策略合法性。 | P0 | [P00:DR-01] |
| **FR-02** | `core.contributes` 格式驅動合併與 `__providers__` 多來源追蹤 | 擴充 `_tag_provider` 同時注入 `"__provider__"` 與 `"__providers__": [donor_name]`；於 `_apply_project_overrides_and_persist` 將專案覆寫標記為 `"project"`；升級 `_deep_merge` 支援傳入目標模組 `_format.json` Schema，依欄位/擴充點宣告之 `merge`/`extend`/`replace`/`unique` 策略執行合併並自動累積去重 `"__providers__"` 清單。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | `file-space` `_format.json` 宣告與 `FileSpaceManager` 來源收斂 | 於 `file-space/contributes/_format.json` 明確標註 `include`、`exclude`、`file_patterns` 為 `\| extend`，`spaces.*` 為 `$FileSpaceDef \| merge`；重構 `FileSpaceManager` 空間載入邏輯，消除對已由 `core.contributes` 合併之 `config://file-space/contribute.json` 的二次重複疊加，並依 `"__providers__"` 精確判定 `origin`（`MODULE` / `PROJECT` / `MERGED`）。 | P0 | [P00:DR-03] |
| **FR-04** | 生態系開發規範與知識庫文檔對齊 | 更新 `ys_codebase/source/agents-workflow/skills/yscb-module-dev/references/contributes_guide.md`、`docs/core/contributes_guide.md` 與 `docs/file-space/contributes_guide.md`，補齊 `\| <strategy>` 合併策略語法與 `__providers__` 契約說明。 | P1 | [P00:DR-01], [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `_format.json` 填寫未知的合併策略（如 `"list[str] \| unknown_mode"` 或 `"merge": "invalid"`） | `ContributesValidator.validate_format_schema` 攔截並回報 `ERROR` 級別 `ValidationIssue`，提供合法策略建議清單 `['extend', 'merge', 'replace', 'unique']`。 |
| **EC-02** | 擴充點映射標註 `\| unique` 時，兩個不同模組（Donor A 與 Donor B）定義同名 Key | 第二個模組注入同名 Key 時，`core.contributes` 記錄衝突告警並保留第一個模組之定義不被覆蓋；但當 `is_project_override=True`（專案 `config://<target>/contribute.json`）時，允許覆寫或合併該 Key。 |
| **EC-03** | 欄位標註 `\| replace`（如 `"list[str]? \| replace"` 或 `"$Def \| replace"`）時發生同名合併 | 後者（較晚模組或專案）之清單或字典直接整包取代前者之值（若為字典取代，仍保留累積之 `"__providers__"` 追蹤清單）。 |
| **EC-04** | 空間僅定義於專案 `config://file-space/contribute.json`（如 `"source"`），無任何模組貢獻 | `core.contributes.get("file-space")` 中該空間之 `"__providers__"` 為 `["project"]`，`FileSpaceManager` 將其 `origin` 判定為 `FileSpaceOrigin.PROJECT` 且 `owner_modules=["project"]`，絕不誤判為 `MERGED`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 相容性與依賴 | 100% Python 標準庫實現，零第三方依賴；未標註 `\| <strategy>` 之既有 `_format.json` 100% 向下相容（`dict`/`$Ref` 預設 `merge`、`list` 預設 `extend`、純量預設 `replace`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `parse_type_signature` 解析順序必須先剝離尾端 `| <strategy>`，再解析 `= <default>` 與 `!` / `?` 必填標記，確保如 `"list[str]? = [] | replace"` 或 `"list[str]! | extend"` 皆能無歧義解析。
- **`[!CAUTION]`** `FileSpaceManager` 支援單元測試注入 `spaces_config`、`contributed_spaces` 或 `custom_config_dir`；當處於預設運行模式（三者皆為 `None`）時，`core.contributes.get("file-space")` 已包含 `config://file-space/contribute.json`，此時不可於 `_discover_project_spaces()` 重複讀取同一份檔案二次合併。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[module://<donor>/contributes/<target>.json] ──(_tag_payload_body: __provider__=donor, __providers__=[donor])──┐
                                                                                                               ├──> [_deep_merge(..., format_schema)]
[config://<target>/contribute.json] ───────────(_tag_payload_body: __provider__="project", __providers__=["project"])┘          │
                                                                                                                                ▼
                                                                                                     [cache://<target>/contributes.merged.json]
                                                                                                                                │
                                                                                                                                ▼
                                                                                                     [FileSpaceManager.load_spaces() -> origin: MODULE | PROJECT | MERGED]
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/validator.py` | Modify | 擴充 `VALID_MERGE_STRATEGIES`、`parse_type_signature` 支援 `\| <strategy>`，並於 `validate_format_schema` 遞迴檢驗策略合法性 |
| `ys_codebase/source/core/core/contributes.py` | Modify | 擴充 `_tag_provider` 寫入 `"__providers__"`、為專案覆寫標記 `"project"`，並使 `_deep_merge` 支援根據 `_format.json` 執行 `merge`/`extend`/`replace`/`unique` |
| `ys_codebase/source/file-space/contributes/_format.json` | Modify | 為 `FileSpaceDef` 之 `include`、`exclude`、`file_patterns` 標註 `\| extend`，`spaces.*` 標註 `\| merge` |
| `ys_codebase/source/file-space/file_space/manager.py` | Modify | 重構 `_discover_module_contributed_spaces`、`_discover_project_spaces` 與 `load_spaces`，消除預設模式下對 `config://file-space/contribute.json` 的二次合併並依 `"__providers__"` 精確判定 `origin` |
| `ys_codebase/source/dev/assets/skills/yscb-module-dev/references/contributes_guide.md` | Modify | 補充 `_format.json` 合併策略 DSL (`\| merge/extend/replace/unique`) 規範 |
| `docs/core/contributes_architecture.md` | Modify | 同步更新核心 Contributes Schema 合併策略與 `__providers__` 說明 |
| `docs/dev/reference/contributes_format.md` | Modify | 同步更新 `_format.json` 合併策略修飾符說明 |
| `docs/file-space/README.md` | Modify | 同步更新 `file-space` 擴充點合併策略與來源判定說明 |
| `ys_codebase/source/core/tests/test_validator.py` | Modify | 新增 `\| <strategy>` 解析與 `validate_format_schema` 正負向測試 |
| `ys_codebase/source/core/tests/test_contributes.py` | Modify | 新增格式驅動合併（`extend`/`replace`/`unique`）與 `"__providers__"`（含 `"project"`）測試 |
| `ys_codebase/source/file-space/tests/test_file_space_manager.py` | Modify | 新增 `core.contributes` 整合下純專案空間 `origin=PROJECT` 與多來源空間 `origin=MERGED` 驗證測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `parse_type_signature` 尾端管道符 `|` 優先剝離設計**：
  - 由於型別簽名可能同時含選填預設值與合併策略（如 `"list[str]? = [] | replace"` 或 `"list[str]! | extend"`），解析器先以最後一個 `|` 分離出 `merge_strategy`，再依既有邏輯解析 `= <default>` 與 `!`/`?`，維持 100% 向下相容。
- **[P02:DR-02] Schema 驅動 `_deep_merge` 與無 Schema 降級相容**：
  - `_deep_merge(base, overlay, schema=None, types_map=None, is_project_override=False)` 在未傳入 `schema` 時完全退化為預設行為（`dict` 為 `merge`、`list` 為 `extend`、純量為 `replace`），確保既有直接呼叫 `_deep_merge(base, overlay)` 之呼叫端 100% 相容。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/validator.py
class ContributesValidator:
    VALID_MERGE_STRATEGIES = ("merge", "extend", "replace", "unique")

    @classmethod
    def parse_type_signature(cls, sig: str) -> Dict[str, Any]: ...

    @classmethod
    def validate_format_schema(cls, format_schema: Dict[str, Any]) -> ValidationResult: ...

# ys_codebase/source/core/core/contributes.py
def _tag_provider(data: Any, donor_name: str) -> Any: ...

def _merge_providers_meta(base_dict: Dict[str, Any], overlay_dict: Dict[str, Any]) -> None: ...

def _deep_merge(
    base: Dict[str, Any],
    overlay: Dict[str, Any],
    schema: Optional[Any] = None,
    types_map: Optional[Dict[str, Any]] = None,
    is_project_override: bool = False,
) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `validate_format_schema` 遇到不屬於 `VALID_MERGE_STRATEGIES` 的策略字串時，回傳 `is_valid=False` 及包含精確路徑與 `Did you mean` / 合法清單建議之 `ValidationIssue(severity="ERROR")`。
  - `_deep_merge` 在運行聚合期遇到 `unique` 跨模組衝突時，遵循 Tolerant Ingress 原則記錄 `logger.warning` 並保留先行模組之項目，不中斷整體環境啟動。
- **階段決策紀錄**：`[P03:DR-01]` 維持 `_deep_merge(base, overlay)` 前兩個位置參數不變，新增具預設值之選填參數 `schema`、`types_map`、`is_project_override`，保障所有外部與測試調用零破壞。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：當 `core.contributes` 為 `config://<target>/contribute.json` 注入 `"__provider__": "project"` 與 `"__providers__": ["project"]` 時，會不會在 `validate(target, target_overlay)` 校驗階段因多了私有鍵而報錯？*
  - *答*：完全不會。一來 `_tag_payload_body` 是在 `validate()` 通過之後才對 `valid_overlay` 執行；二來 `ContributesValidator._validate_dict_schema_node` 對於內部注入欄位（或我們在 `_validate_dict_schema_node` 忽略以 `__` 開頭之內部元資料鍵如 `__provider__`、`__providers__`）可安全放行。我們將在 `_validate_dict_schema_node` 明確跳過 `k.startswith("__") and k.endswith("__")` 的內部元資料鍵，防止二次驗證時誤報未知欄位。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/file-space/README.md` | Modify | 同步更新 `FileSpaceManager` 雙軌空間聚合與 `__providers__` 來源判定說明 |
| **專題手冊** | `docs/core/contributes_architecture.md`, `docs/dev/reference/contributes_format.md` | Modify | 補充 `_format.json` `\| <strategy>` 合併語法與 `__providers__` 追蹤機制 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | N/A | 無特殊妥協 |
| **微觀註解** | `validator.py`, `contributes.py`, `manager.py` Docstrings | Modify | 同步更新關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 將於 P07 結案時記錄本版本發布摘要 |

- **決策定稿**：**[P04:DR-01]** 鎖定 `core`、`file-space`、`dev` 三模組連動更新與測試守門。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：於 `ys_codebase/source/core/core/validator.py` 實作 `| <strategy>` 型別簽名解析、內部 `__*__` 欄位忽略與 `validate_format_schema` 合併策略檢驗
- [x] **TASK-02**：於 `ys_codebase/source/core/core/contributes.py` 實作 `"__providers__"` 多來源追蹤、專案 `"project"` 標記與 Schema 驅動之 `_deep_merge`
- [x] **TASK-03**：更新 `ys_codebase/source/file-space/contributes/_format.json` 並重構 `ys_codebase/source/file-space/file_space/manager.py` 來源判定與單次合併邏輯
- [x] **TASK-04**：於 `test_validator.py`、`test_contributes.py`、`test_file_space_manager.py` 編寫單元與邊界測試並通過 `dev check` 與 `dev test`
- [x] **TASK-DOC**：同步更新 `ys_codebase/source/dev/assets/skills/yscb-module-dev/references/contributes_guide.md`、`docs/core/contributes_architecture.md`、`docs/dev/reference/contributes_format.md` 與 `docs/file-space/README.md` 並完成 `@build` 熱部署驗證

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
