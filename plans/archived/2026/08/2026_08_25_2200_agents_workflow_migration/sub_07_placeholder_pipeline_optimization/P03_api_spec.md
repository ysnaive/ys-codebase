# API 規格說明書 (Phase 3: API & Interface Specification)

> 功能名稱：佔位符解析管線優化 (Placeholder Pipeline Optimization)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. Public API 簽名與型態契約 (Public Interfaces)

### 1.1 `ArtifactCompiler` (`agents_workflow/compiler.py`)

```python
from typing import Dict, List, Any, Optional

class ArtifactCompiler:
    """工廠編譯器：負責 Stage 1 內容展開與 Stage 2 URI 解析。"""
    
    def __init__(self, host_dir: Optional[str] = None):
        ...

    def resolve_stage1_content(
        self,
        content: str,
        inserts: List[Dict[str, Any]],
        context: Optional[Any] = None
    ) -> str:
        """Stage 1: 5-Step 狀態機多輪遞迴解算 `__@{token}__` 內容佔位符。"""
        ...

    def compile_stage1(self) -> Dict[str, Any]:
        """
        搜集全模組 export 與 insert，解算所有資產並物化寫入快取中繼：
        cache.root://agents-workflow/resolved_contents/{standards|workflows|templates}/
        """
        ...

    def resolve_stage2_uri(
        self,
        content: str,
        current_dst_path: str,
        deployment_map: Dict[str, str]
    ) -> str:
        """
        Stage 2: 依三層重映射階層將 `__#{uri}__` 動態轉譯為相對於 current_dst_path 之實體相對路徑。
        - Tier 1: 命中 deployment_map 查表計算。
        - Tier 2: 專案級協議調用 uri.resolve 計算。
        - Tier 3: 未知/未決協議安全降級並發出 Warning。
        """
        ...
```

### 1.2 `ReleasePublisher` (`agents_workflow/publisher.py`)

```python
from typing import Dict, List, Any, Optional

class ReleasePublisher:
    """發布引擎：負責 Target 拓撲映射、Header 巨集插值與 4 步原子交易。"""

    def __init__(self, compiler: Optional[ArtifactCompiler] = None):
        ...

    def get_registered_release_targets(self) -> List[Dict[str, Any]]:
        """搜集全系統 contributes 中所有註冊的 release_target 宣告。"""
        ...

    def build_deployment_map(
        self,
        target_cfg: Dict[str, Any],
        resolved_items: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """建立本次發布之「來源 URI ➔ 最終實體目標絕對路徑」1:1 拓撲映射表。"""
        ...

    def render_header(
        self,
        export_item: Dict[str, Any],
        proj_cfg: Dict[str, Any],
        target_name: str
    ) -> str:
        """
        解析純文字/陣列 header 模板，動態替換 {export.description}、{export.name} 等巨集變數。
        """
        ...

    def release_all(self, interactive: bool = False) -> Dict[str, Any]:
        """
        執行 4 步原子發布交易：
        1. 檢查 storage://agents-workflow/release_manifest.json 清理過往檔案。
        2. 提前解算所有已啟用 Target 之目標檔案內容。
        3. 原子寫入 storage:// 最新發布清單。
        4. 建立目錄並落地輸出檔案（含 AGENTS.md 軟合併）。
        """
        ...
```

### 1.3 `ReleaseTargetManager` (`agents_workflow/targets.py`)

```python
from typing import List, Dict, Any

class ReleaseTargetManager:
    """釋出目標組態管理器：負責 config.project.json 之 targets 讀寫。"""

    @classmethod
    def list_targets(cls) -> List[Dict[str, Any]]:
        """列出全系統可用 Targets，標註 [ENABLED], [DISABLED] 或 [ORPHAN / NOT FOUND]。"""
        ...

    @classmethod
    def add_target(cls, target_name: str) -> bool:
        """啟用 Target，更新 config.project.json 並自動觸發 release_all()。"""
        ...

    @classmethod
    def remove_target(cls, target_name: str) -> bool:
        """停用 Target，更新 config.project.json 並自動觸發 release_all()（清理檔案）。"""
        ...
```

---

## 2. Contributes 擴充宣告規格 (`release_target`)

```json
{
  "contributes": {
    "agents-workflow": {
      "release_target": [
        {
          "name": "antigravity",
          "description": "Google Antigravity IDE 原生 Slash Commands 與標準規範輸出",
          "projections": {
            "workflow": {
              "target_dir": "project://.agents/workflows",
              "extension": ".md",
              "header": [
                "---",
                "description: {export.description}",
                "---"
              ]
            },
            "template": {
              "target_dir": "project://.agents/templates",
              "extension": ".md"
            },
            "standard": {
              "target_dir": "project://.agents/standards",
              "extension": ".md"
            }
          }
        }
      ]
    }
  }
}
```

---

## 3. 實作依賴拓撲順序 (Implementation Dependency Topology)

```text
[Task 1: config.project.json 模板升級 (release_targets: ["antigravity"])]
                               │
                               ▼
[Task 2: manifest.json 宣告 release_target (antigravity)]
                               │
                               ▼
[Task 3: compiler.py (Stage 1 快取中繼 + Stage 2 三層 URI 重映射)]
                               │
                               ▼
[Task 4: publisher.py (發布拓撲映射 + Header 巨集插值 + 4 步原子交易 + AGENTS.md 軟合併)]
                               │
                               ▼
[Task 5: targets.py & cli.py (實作 release, release-target 指令體系)]
                               │
                               ▼
[Task 6: assets/ (全面更新所有 standards/workflows/templates 的路徑引用為 __#{uri}__)]
                               │
                               ▼
[Task 7: test_compiler.py (單元測試 ST-01~08 與全量回歸驗證)]
```

---

## 4. 決策紀錄 (Traceability)

- 本規格直接落實 [P01_requirements_spec.md](./P01_requirements_spec.md) 之 FR-01 ~ FR-07 與 [P02_architecture_plan.md](./P02_architecture_plan.md)。
