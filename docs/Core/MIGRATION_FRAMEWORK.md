---
target: "Core/MigrationFramework"
doc_type: "topic_doc"
status: "active"
source_paths:
  - "source/core/scripts/migration.py"
related_docs:
  - "./README.md"
  - "./SEMVER_ENGINE.md"
  - "../Installer/UPGRADE_PIPELINE.md"
last_updated: "2026-08-23"
---

# 鏈式線性增量遷移框架 (MigrationRunner) 手冊

本文件說明 `yscb_core.migration` 模組的運作原理、裝飾器步階定義與版本代際遷移生命週期。

---

## 1. 核心設計架構

當模組發生 Minor 代際變更（資料格式/設定結構調整）時，模組應在其根目錄或 `scripts/` 提供 `_migration.py` 腳本。

`MigrationRunner` 透過裝飾器 `@runner.step("X.Y.x")` 註冊各代際遷移邏輯。當跨多個版本升級時（例如從 `v1.0.0` 升級至 `v1.3.0`），執行器會以 $O(N)$ 線性時間依序執行滿足 `old_version < step <= new_version` 區間內的所有步階，保證無縫跨版本平滑升級。

---

## 2. 步階宣告語法範例 (`_migration.py`)

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
from yscb_core import MigrationRunner

runner = MigrationRunner()

@runner.step("1.1.x")
def migrate_to_1_1(project_root: Path, module_dir: Path):
    """1.0.x ➔ 1.1.x: 設定檔結構轉移"""
    print("[MIGRATE] 升級至 1.1.x...")

@runner.step("1.2.x")
def migrate_to_1_2(project_root: Path, module_dir: Path):
    """1.1.x ➔ 1.2.x: 資料庫欄位補齊"""
    print("[MIGRATE] 升級至 1.2.x...")

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        old_v = sys.argv[1]
        new_v = sys.argv[2]
        runner.run(old_v, new_v)
```

---

## 3. 升級與回滾保護

- **執行順序保證**：步階會自動依據基準 SemVer 由小到大排序執行。
- **異常拋出與回滾觸發**：若任何單一步階 handler 拋出例外，執行將立即中止並向上拋出，由 `InstallerManager` 捕獲後觸發 `_rollback_snapshot()`，保障升級失敗時 100% 還原至升級前快照。
