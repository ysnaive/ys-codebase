---
target: "Core/SemVerEngine"
doc_type: "topic_doc"
status: "active"
source_paths:
  - "source/core/scripts/semver.py"
related_docs:
  - "./README.md"
  - "./MIGRATION_FRAMEWORK.md"
  - "../Installer/UPGRADE_PIPELINE.md"
last_updated: "2026-08-23"
---

# SemVer 2.0.0 語意化版本與相依約束引擎手冊

本文件說明 `yscb_core.semver` 模組的架構設計、SemVer 2.0.0 規範遵循性、富比較邏輯與相依約束解析語法。

---

## 1. 核心定位與設計原則

- **純標準庫實現 (Zero External Dependency)**：100% 使用 Python 3.8+ 標準庫（`re`, `typing`）實現，不引入 `semver` 或 `packaging` 第三方套件。
- **剛性遞進與專案適配公理**：
  - `Major`（主版本號）：使用者角度或重大架構發生不可調和之變更。
  - `Minor`（次版本號）：需要執行資料/設定格式遷移 (`_migration.py`) 的變動。
  - `Patch`（修訂號）：內部實作優化、修復或向後相容之新增功能。

---

## 2. SemVer 物件架構與比較運算

### 物件初始化與寬容解析
```python
from yscb_core import SemVer

v1 = SemVer("1.2.3")
v2 = SemVer("v2.1.0-alpha.1+build.20260823")
v3 = SemVer("1.0")  # 自動補齊為 1.0.0
```

### 優先級比對規則 (SemVer 2.0.0 Spec Section 11)
- **主要版號比對**：由左至右依序比對 `major` ➔ `minor` ➔ `patch` 數值。
- **預發布版 (Prerelease)**：
  - 無預發布標籤版本優先級高於有預發布標籤版本（例：`1.0.0 > 1.0.0-alpha`）。
  - 各識別碼分割比對：純數字以數值大小比對，字母以 ASCII 字典序比對。
- **建置元數據 (Build Metadata)**：
  - 依照 SemVer 2.0.0 第 10 條規範，建置元數據不參與優先級比對（例：`1.0.0+build1 == 1.0.0+build2`）。

---

## 3. VersionConstraint 相依約束表達式

支援在模組 `manifest.json` 之 `dependencies` 欄位宣告豐富的約束表達式：

| 約束語法 | 語意說明 | 匹配範例 |
| :--- | :--- | :--- |
| `*` 或 `""` | 萬用字元（相容任何版本） | `1.0.0`, `2.5.0` 皆通過 |
| `==1.0.0` 或 `1.0.0` | 精確版本匹配 | 僅 `1.0.0` 通過 |
| `>=1.0.0, <2.0.0` | 複合區間匹配 | `1.0.0` ~ `1.9.9` 通過，`2.0.0` 拒絕 |
| `^1.2.3` | Caret 相容（鎖定 Major） | `>=1.2.3, <2.0.0`（0.x 則鎖定 Minor） |
| `~1.2.0` | Tilde 相容（鎖定 Major.Minor） | `>=1.2.0, <1.3.0` |

### 代碼調用範例
```python
from yscb_core import VersionConstraint

vc = VersionConstraint(">= 2.0.0, < 3.0.0")
assert vc.matches("2.1.0") is True
assert vc.matches("3.0.0") is False

# 解析相依宣告
mod_name, constraint = VersionConstraint.parse_dependency_spec("core >= 2.0.0")
# mod_name: "core", constraint: VersionConstraint(">= 2.0.0")
```
