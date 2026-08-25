# API 規格定義書 (API Specification)

> 功能名稱：Core 模組功能打磨 (Core Module Polish)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01 / P02：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.3  

---

## 1. 介面定義 (Interface Definitions)

### 1.1 `core.uri.ExecutionContext`

```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass(frozen=True)
class ExecutionContext:
    """執行期語意上下文介面 (Execution Context Interface)"""
    module_name: str                                # 發起端或目標模組名稱 (例: "core", "dev", "agents-workflow")
    command: Optional[str] = None                   # 當前觸發的操作指令 (例: "install", "reload", "build")
    args: List[str] = field(default_factory=list)   # 命令列參數清單
    metadata: Dict[str, Any] = field(default_factory=dict) # 額外附帶之元數據
```

### 1.2 `core.uri.resolve`

```python
def resolve(
    uri: str, 
    current_module: Optional[str] = None, 
    context: Optional[ExecutionContext] = None
) -> str:
    """
    解析語意 URI 為實體絕對路徑。
    
    :param uri: 語意 URI 字串 (例 "project://AGENTS.md", "config://config.project.json")
    :param current_module: 指定當前模組名稱 (若為 None 則讀取全域 context)
    :param context: 執行期上下文 (供動態佔位符 handler 解算使用)
    :return: 實體作業系統路徑
    :raises TypeError: 當 uri 不為字串型別時拋出
    :raises ValueError: 
        1. 當 project:// 未在 config/core/config.project.json 中定義 project_root 時拋出
        2. 當遇上無法解析之未註冊 protocol 時拋出
    """
```

### 1.3 `core.engine.AtomicEngine.act_broadcast_event`

```python
def act_broadcast_event(
    self, 
    emit_module: str, 
    event_name: str, 
    context: Optional[ExecutionContext] = None
) -> Dict[str, Any]:
    """
    廣播生命週期事件至所有已安裝模組之命名空間 Hook。
    
    :param emit_module: 發起事件的模組名稱 (例: "core", "dev")
    :param event_name: 事件名稱 (例: "on_installed", "on_before_build", "on_reload")
    :param context: 執行期上下文 (若為 None 則自動包裝為預設 Context)
    :return: 各模組調度結果字典 {module_name: "success" | "warning: <error_msg>"}
    """
```

### 1.4 `core.engine.AtomicEngine._seed_or_update_config`

```python
def _seed_or_update_config(self, module_name: str, template_dir: str) -> None:
    """
    為指定模組自動分發或增量補齊專案組態。
    
    :param module_name: 目標模組名稱
    :param template_dir: 模組發布包或鏡像目錄路徑
    :behavior:
        1. 檢查 template_dir 中是否存在 config.project.json 或 config.local.json。
        2. 若 target config/ 不存在：完整複製範本。
        3. 若 target config/ 已存在：遞迴深度比對，自動補齊缺失鍵，既有用戶設定值 100% 保持不變。
    """
```

---

## 2. 資料結構與設定檔 Schema (Data Schemas)

### 2.1 `yscb://config/core/config.project.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "project_root": "./",
  "description": "Core infrastructure module project configuration"
}
```

| 欄位名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :---: | :--- |
| **`project_root`** | `string` | **是** | `project://` 相對於宿主工作目錄之相對或絕對路徑（例：`"./"` 或 `"../"`）。**未配置將導致 `project://` 解析拋出 `ValueError`**。 |

### 2.2 命名空間 Hook 檔案介面 (`module://scripts/hook.{emit_module}.py`)

```python
# 檔案路徑範例: module.root://agents-workflow/scripts/hook.dev.py
from core.uri import ExecutionContext

def on_before_build(context: ExecutionContext) -> None:
    """
    當 dev 模組執行 build 之前觸發。
    :param context: 執行期上下文
    """
    ...

def on_after_build(context: ExecutionContext) -> None:
    """
    當 dev 模組執行 build 之後觸發。
    :param context: 執行期上下文
    """
    ...
```

---

## 3. 實作依賴拓撲 (Implementation Topology)

```text
[Step 1: core.uri]
  ├── 定義 ExecutionContext 介面
  ├── 重構 _find_host_config() 與 resolve() 移除 project:// 隱式 fallback
  ├── 支援 config/ 與 config.root/ 顯式目錄
  └── 打通 contributes.merged.json 之 type: "config" 與動態佔位符解算

[Step 2: core.engine]
  ├── 實作 _deep_infill_dict 遞迴增量補齊演算法
  ├── 實作 _seed_or_update_config 於 reload 與安裝流程自動調用
  └── 實作 act_broadcast_event 命名空間掃描與 try-except 例外隔離

[Step 3: core.installer]
  ├── 於 cmd_install / cmd_update / cmd_reload / cmd_remove 串接 event 與 config 補齊
  └── 移除 source/core/ 與 modules/core/ 之非標準 config.project.json

[Step 4: 官方持久化測試套件更新]
  ├── test_uri.py (驗證 project:// 顯式解析與零 Fallback 阻斷、config/ 協議)
  ├── test_engine.py (驗證 hook.{emit_mod}.py 廣播、例外隔離、組態增量補齊)
  └── test_installer.py (驗證安裝時組態自動種入與補齊)

[Step 5: 主計畫白皮書 R01~R04 對齊回填]
  └── 全面同步更新 R01, R02, R03, R04 文檔
```

---

## 4. 本階段決策紀錄 (Phase 3 Decision Records)

- **[P03:DR-01] ExecutionContext 宣告為不可變凍結 Dataclass**：`@dataclass(frozen=True)`，確保在事件廣播與 handler 調度時 Context 屬性無法被下游模組惡意竄改。
- **[P03:DR-02] 零猜測阻斷錯誤訊息格式**：`ValueError: 'project://' is undefined. Please configure 'project_root' in config://config.project.json (core)`。
- **[P03:DR-03] 命名空間動態 Hook 模組鍵名防護**：載入 hook 時使用模組隔離鍵 `f"_yscb_hook_{receiver}_{emit_mod}"` 註冊至 `sys.modules`，防止全域命名快取覆蓋。
