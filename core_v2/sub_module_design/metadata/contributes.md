# 子模組架構設計規格：`core.metadata.contributes`（Contributes 2.0 雙向強型別擴充引擎與 `ProvenanceGraph`）

> **所屬功能域**：`Domain 3 — 組態與擴充域 (metadata/)`
> **模組路徑**：`core_v2/source/core/core/metadata/contributes/`
> **建議內部切分**：`spec.py`、`compiler.py`、`validator.py`、`provenance.py`、`aggregator.py`、`__init__.py`
> **依賴上限（Allowed Imports）**：`foundation/*`、`filesystem.fs`、`metadata.config`
> **禁止反向依賴（Forbidden Imports）**：`filesystem.{vfs, space, storage}`、`packaging/*`、`execution/*`、`surface/*`
> **狀態**：`Draft — Design Frozen for Wave 1.2 Implementation`

> [!NOTE]
> **實作彈性邊界**：`MergeStrategy`、`ContribField`、`ExtensionPointSpec`、`ProvenanceGraph`、JSON 合併語意（`merge/extend/replace/unique/bucket_by_donor`）與 `contributes/<target>.json` / `config://<target>/contribute.json` 磁碟同構格式屬硬契約；內部驗證輔助實作可由遠端實作端微調。

---

## 1. 模組定位與 1.x $\to$ 2.0 核心演進（對齊 `DR-06`）

`core.metadata.contributes` **100% 完整保留** YS-Codebase 免改源碼的宣告式依賴注入體系（模組間 `contributes/<target>.json`、專案級 `config://<target>/contribute.json` 覆寫、拓撲序聚合、四大合併策略、Strict Egress / Tolerant Ingress 雙重驗證、`Did you mean` 拼寫診斷、`locales` 契約校驗、溯源與分桶，以及 `.vscode/schemas/*.json` 導出），並升級為 **Python SDK 強型別版本**：

1. **所有編譯、驗證、聚合與實例化邏輯 100% 歸屬 `core`（`dev` 零重複實作）**：
   - Host 模組以純 Python `@dataclass(frozen=True, slots=True)` + `Annotated[T, ContribField(...)]` 作為唯一真理來源（SSOT），徹底淘汰手寫 `contributes/_format.json` 自創 DSL。
   - **Tier 0 模組與 `InMemoryModule` 測試**：運行端直接從 Python `@dataclass` 萃取 `ExtensionPointSpec` 執行驗證、聚合與實例化，零需預先跑 `dev build`。
   - **Tier 1 模組（如 `ast`、`knowledge-db`）**：打包（或於其 `.venv` 內安裝初始化）時**直接呼叫 `core` 自身的 `compile_extension_points()` API** 產出隨包靜態 `contributes/_schema.json`（JSON Schema Draft 2020-12 附 `x-yscb-merge` / `x-yscb-bucket-by-donor`）；如此 Tier 0 內核聚合與 `vscode-support` 投影皆 **0 匯入 Tier 1 `.py`**，而 Tier 1 Worker 內部仍使用同一套 `core` 解碼器實例化強型別 `@dataclass`。
   - `dev build` / `dev check` 僅作為薄呼叫端直接調用 `core.metadata.contributes` API。
2. **純淨業務負載 + 獨立 `ProvenanceGraph`（零魔術鍵污染）**：
   - 廢除 1.x 偷塞進業務 JSON 字典的 `"__provider__"` / `"__providers__"` / `"__modules__"` 魔術鍵（避免破壞 `DataclassCodec` 嚴格欄位檢查）。
   - 溯源資訊全數收斂於伴隨之 **`ProvenanceGraph`**（以 JSON Pointer 記錄每一節點之貢獻鏈與最終覆寫者）；需要按來源模組分桶之擴充點（如 `locales`）宣告 `MergeStrategy.BUCKET_BY_DONOR`，直接解碼為 `Mapping[ModuleId, T]`。
3. **純記憶體按需聚合（取消 `cache://<target>/contributes.merged.json` 落盤）**：
   - 移除 `commands`（2.0 改由 `@task(cli=...)` + `tasks.index.json` 宣告）後，全倉 `contributes/*.json` 總量僅約 20–30 KB。
   - 熱態（Daemon）常駐記憶體 0 I/O 並隨監視器重載；冷態單次讀取聚合僅 `< 1–2ms`，徹底消除 `contributes.meta.json` 寫盤競態、空檔清理（`DN-02`）與陳舊快取問題。人工除錯改走 `yscb contributes inspect <target> [--provenance] [--json]`。
4. **專案覆寫檔同構收斂**：
   - `config://<target>/contribute.json` 統一與 `module://<donor>/contributes/<target>.json` **100% 同構**（頂層直接寫擴充點鍵名，不再保留 1.x `{ "<target>": {...} }` 外層剝殼特例）；持續剛性禁止 `config://<target>/contribute.local.json`（偵測到時輸出結構化警告並忽略）。

---

## 2. 兩階拓撲聚合與合併策略規則

### 2.1 確定性載入與拓撲序
對目標模組 `<target>` 執行聚合時，嚴格遵循兩階決定性順序：
1. **階層 ① 模組貢獻（`{yscb_root}/.modules/<donor>/contributes/<target>.json`）**：
   - 依已安裝模組之 `manifest.dependencies` **拓撲排序**遍歷（`core` 置頂，同層依 `ModuleId` 字母序打破平手）；僅支援目錄式 `contributes/<target>.json`（廢除舊單檔 `contributes.json`）。
2. **階層 ② 專案覆寫（`{yscb_root}/config/<target>/contribute.json`）**：
   - 疊加於所有模組貢獻之上，於 `ProvenanceGraph` 中記錄貢獻者標記為 `"project"`。

### 2.2 五大合併策略（`MergeStrategy`）
| 策略 | 預設適用型別 | 合併語意 |
| :--- | :--- | :--- |
| **`MERGE`** | `Mapping` / `@dataclass` | 遞迴逐鍵合併字典，後序覆蓋同名純量鍵 |
| **`EXTEND`** | `Sequence` / `tuple` | 保序附加元素（具確定性去重選項） |
| **`REPLACE`** | 任意欄位 | 後序整包取代前序值 |
| **`UNIQUE`** | `Mapping` 鍵集合 / 識別符 | 禁止不同模組宣告同名鍵（碰撞即報 `CONTRIBUTES_INVALID`）；僅允許專案覆寫（`"project"`）合法覆蓋或合併 |
| **`BUCKET_BY_DONOR`** | 擴充點層級（如 `locales`） | 依來源 `<donor>` 自動分桶為 `{ "<donor>": <payload> }`，完全隔離同名鍵碰撞，直接解碼為 `Mapping[ModuleId, T]` |

---

## 3. 核心公開契約規格 (`core/metadata/contributes/`)

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, Mapping, Optional, Sequence, TypeVar

from core.foundation.primitives import HostPath, JsonObject, JsonValue, ModuleId, MutableJsonObject
from core.metadata.config import ModuleManifest

TPoint = TypeVar("TPoint")


class MergeStrategy(Enum):
    MERGE = "merge"
    EXTEND = "extend"
    REPLACE = "replace"
    UNIQUE = "unique"
    BUCKET_BY_DONOR = "bucket_by_donor"


@dataclass(frozen=True, slots=True)
class ContribField:
    """搭配 typing.Annotated[T, ContribField(...)] 標註擴充點欄位之合併策略與 IDE 說明。"""
    merge: Optional[MergeStrategy] = None
    description: str = ""
    dedupe: bool = True


@dataclass(frozen=True, slots=True)
class ExtensionPointSpec(Generic[TPoint]):
    """Host 模組開放之單一強型別擴充點規格（唯一真理來源）。"""
    name: str
    payload_type: type[TPoint]
    description: str = ""
    merge_strategy: MergeStrategy = MergeStrategy.MERGE
    strict_fields: bool = True


@dataclass(frozen=True, slots=True)
class ContributesSchemaBundle:
    """由 core 編譯產出之靜態擴充契約包（可序列化為 contributes/_schema.json 供 Tier 0 / IDE 消費）。"""
    target_module: ModuleId
    schema_version: int
    points_schema: JsonObject  # JSON Schema Draft 2020-12 含 x-yscb-merge / x-yscb-bucket-by-donor

    def to_json(self) -> MutableJsonObject: ...
    @classmethod
    def from_json(cls, raw: JsonObject) -> ContributesSchemaBundle: ...
```


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    json_pointer: str
    contributors: tuple[str, ...]  # 依序累積之貢獻來源（模組 ID 或 "project"）
    final_owner: str               # 最終生效覆寫方


class ProvenanceGraph:
    """離帶（Out-of-Band）溯源圖：不向業務 JSON 注入魔術鍵，支援精確 JSON Pointer 來源查詢。"""
    def __init__(self, entries: Mapping[str, ProvenanceEntry]) -> None: ...
    def origin_for(self, json_pointer: str) -> Optional[ProvenanceEntry]: ...
    def contributors_for(self, json_pointer: str) -> tuple[str, ...]: ...
    def pointers_by_donor(self, donor: str) -> tuple[str, ...]: ...
    def to_json(self) -> MutableJsonObject: ...


class ValidationSeverity(Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: ValidationSeverity
    source_label: str              # 例 "module:dev/contributes/core.json" 或 "project:config/core/contribute.json"
    json_pointer: str
    message: str
    suggestion: Optional[str] = None  # Did you mean '...'


@dataclass(frozen=True, slots=True)
class ValidationReport:
    target_module: ModuleId
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool: ...
    @property
    def errors(self) -> tuple[ValidationIssue, ...]: ...
    @property
    def warnings(self) -> tuple[ValidationIssue, ...]: ...


@dataclass(frozen=True, slots=True)
class AggregatedContributes:
    """目標模組單次聚合結果（純淨業務 JSON + 獨立 ProvenanceGraph + 強型別解碼入口）。"""
    target_module: ModuleId
    raw_merged: JsonObject
    provenance: ProvenanceGraph
    warnings: tuple[ValidationIssue, ...] = ()

    def has_point(self, point_name: str) -> bool: ...
    def decode_point(self, point_name: str, target_cls: type[TPoint]) -> TPoint: ...
    def decode_donor_bucket(self, point_name: str, item_cls: type[TPoint]) -> Mapping[str, TPoint]: ...


def compile_extension_points(
    target_module: ModuleId,
    specs: Sequence[ExtensionPointSpec[object]],
) -> ContributesSchemaBundle: ...


def validate_locale_bundle(
    donor_module: ModuleId,
    module_root: HostPath,
    locale_pointers: Mapping[str, str],
) -> tuple[ValidationIssue, ...]: ...


class ContributesAggregator:
    """純記憶體兩階拓撲聚合與雙重驗證引擎（100% 歸屬 core，零磁碟快取落盤）。"""
    def __init__(
        self,
        *,
        yscb_root: HostPath,
        manifests: Sequence[ModuleManifest],
        live_specs: Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]] = ...,
    ) -> None: ...

    def reload(
        self,
        manifests: Optional[Sequence[ModuleManifest]] = None,
        live_specs: Optional[Mapping[ModuleId, Sequence[ExtensionPointSpec[object]]]] = None,
    ) -> None: ...
    def get_schema_bundle(self, target_module: ModuleId) -> Optional[ContributesSchemaBundle]: ...
    def list_extension_points(self, target_module: Optional[ModuleId] = None) -> Mapping[ModuleId, ContributesSchemaBundle]: ...
    def aggregate(self, target_module: ModuleId, *, strict: bool = False) -> AggregatedContributes: ...
    def validate_all(self, *, strict: bool = True) -> tuple[ValidationReport, ...]: ...
    def validate_donor_file(
        self, donor_label: str, target_module: ModuleId, raw_payload: JsonObject, *, strict: bool = True,
    ) -> ValidationReport: ...
```

---

## 4. Core 內建三大擴充點與雙層運行契約

### 4.1 `core` 保留之內建強型別擴充點
| 擴充點 | 合併策略 | 承載契約 |
| :--- | :--- | :--- |
| **`uri_schemes`** | `UNIQUE`（按 `token`） | 模組自訂語意協議宣告（`token`、`target_uri`/`config_binding`、`description`），由組裝根轉為 `vfs.MountRule` |
| **`spaces`** | `BUCKET_BY_DONOR` + `MERGE` | 各模組靜態 `SpaceSpec` 定義（`gitignore`、`workspace`、`readonly`、`source`、`docs`、`plans` 等），由組裝根餵入 `space.SpaceRegistry` |
| **`locales`** | `BUCKET_BY_DONOR` | 各模組語系檔指標（`definition` + `<lang-id>` 相對路徑），經 `validate_locale_bundle` 檢查孤兒鍵、路徑穿越與 `{placeholder}` 一致性後載入 `foundation.LocaleCatalog` |

### 4.2 雙重驗證與跨 Tier 協作不變量
1. **Strict Egress vs. Tolerant Ingress**：
   - `strict=True`（`yscb contributes check` 與 `dev check`）：未知擴充點、未知欄位、型別錯誤、`UNIQUE` 跨模組衝突或 `locales` 契約違規一律產出 `ERROR` 並回傳非零退出碼（內建 `difflib.get_close_matches` 產生 `Did you mean '<candidate>'?`）。
   - `strict=False`（執行期 `aggregate`）：遇非致命欄位瑕疵記錄 `WARNING` 於 `AggregatedContributes.warnings` 並保護其餘合法模組正常運行；偵測到 `config/<target>/contribute.local.json` 時明確發出 `WARNING` 並忽略。
2. **Tier 0 / Tier 1 同源零重複**：
   - 查詢目標模組契約時優先取 `live_specs[target]`（經 `compile_extension_points` 產出），若該目標為 Tier 1 模組而不在 Tier 0 記憶體中，則自動讀取 `.modules/<target>/contributes/_schema.json`（該檔同樣由 `core.metadata.contributes.compile_extension_points()` 於打包或環境初始化階段產出）。
   - `vscode-support` 投影 `.vscode/schemas/*.json` 時直接消費 `ContributesAggregator.get_schema_bundle(target)`，確保 IDE 補全與執行期驗證 100% 同源。

---

## 5. 必測驗收門檻 (Verification Gate)

1. **Python `@dataclass` SSOT 往返測試**：以 `ExtensionPointSpec` + `ContribField` 編譯為 `ContributesSchemaBundle`，序列化為 `_schema.json` 再反序列化後，對相同輸入的驗證與合併結果與 `live_specs` 100% 一致。
2. **拓撲順序、五種策略與 `ProvenanceGraph`**：驗證依賴拓撲順序決定性、`MERGE`/`EXTEND`/`REPLACE`/`UNIQUE`（跨模組碰撞報錯、`"project"` 覆寫放行）/`BUCKET_BY_DONOR`（零 `"__provider__"` / `"__modules__"` 殘留於 `raw_merged`），以及 `ProvenanceGraph` 精準回報多層貢獻鏈。
3. **專案同構覆寫與防線**：`config://<target>/contribute.json` 與模組檔同構合併生效；`contribute.local.json` 遭忽略並產出 `WARNING`；無任何檔案寫入 `cache://`。
4. **雙重驗證與 `locales` 契約**：拼寫錯誤觸發 `Did you mean`；`locales` 偵測孤兒鍵、`..` 穿越與 `{placeholder}` 不一致。
