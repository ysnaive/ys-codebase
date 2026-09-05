# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_05_jit_self_healing_integration  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `core.events.broadcast` | `ys_codebase/source/core/core/events.py` | Public | 微內核通用事件廣播主函式，尋址 `hook.<Sender>.py` 並觸發對應回呼 |
| `core.events.get_contributed_events` | `ys_codebase/source/core/core/events.py` | Public | 聚合並解析全生態系各模組在 `contributes` 中宣告之 `events` 清冊 |
| `hook.core.on_pre_cli_dispatch` | `ys_codebase/source/agents-workflow/scripts/hook.core.py` | Public Hook | `agents-workflow` JIT 資產指紋嗅探與熱自癒物化掛鉤 |
| `dev.testing.sandbox._dispatch_test_hooks` (移除) | `ys_codebase/source/dev/dev/testing/sandbox.py` | Internal | 移除自建函式，改呼叫 `core.events.broadcast(..., emit_module="dev")` |
| `yscb.cmd_event` | `yscb.py` | Public CLI | 提供 `python yscb.py event list` CLI 指令，快速查表全系統可用事件 |
| `yscb._ensure_jit_lifecycle_pre` | `yscb.py` | Private | 宿主分發前置管線：微環境檢查 + `pre_cli_dispatch` 事件廣播 |
| `yscb._ensure_jit_lifecycle_post` | `yscb.py` | Private | 宿主分發後置管線：`post_cli_dispatch` 事件廣播 + 12hr 更新檢查提示 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# === 1. core.events 模組介面 (ys_codebase/source/core/core/events.py) ===

from typing import List, Dict, Any, Optional
from core.context import ExecutionContext

def broadcast(
    event_name: str,
    context: Optional[Any] = None,
    emit_module: str = "core",
    search_roots: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    向已安裝模組廣播生命週期事件，動態尋址 module://{mod}/scripts/hook.{emit_module}.py。

    :param event_name: 事件名稱（如 "pre_cli_dispatch", "post_cli_dispatch", "on_reload"）
    :param context: 執行期上下文物件，預設自動建立 ExecutionContext(emit_module, event_name, [])
    :param emit_module: 事件發送者名稱，用於定位 hook.<emit_module>.py，預設為 "core"
    :param search_roots: 自訂掃描根目錄列表；若為 None 則預設掃描 module:// 運行端
    :return: 執行結果字典 { module_name: result_or_status }

    函式尋址與容錯規則：
      1. 依序比對 hook_mod 之函式：getattr(hook_mod, f"on_{event_name}") -> getattr(hook_mod, event_name) -> getattr(hook_mod, "on_event")
      2. 任何模組拋出例外均安全捕獲並輸出 Warning，絕不中斷主流程
    """

def get_contributed_events() -> Dict[str, List[Dict[str, str]]]:
    """
    聚合全生態系模組於 contributes 宣告之 events 清冊。
    支援 list[{"<name>": "description"}] 與 dict 格式雙向容錯相容。

    :return: 字典格式 { module_name: [ {"name": event_name, "description": desc} ] }
    """


# === 2. agents-workflow 生命週期 Hook (ys_codebase/source/agents-workflow/scripts/hook.core.py) ===

def on_pre_cli_dispatch(ctx: Optional[Any] = None) -> bool:
    """
    在 CLI 命令分發前觸發，呼叫 ReleasePublisher.ensure_jit_release()。
    若來源特徵指紋變更，原地執行 release_all(force=False) 自癒物化至 Targets；
    若無變更 (Clean)，<1ms 極速短路跳過。

    :return: 是否發生實質物化寫入
    """


# === 3. yscb.py CLI 指令分發與生命週期 ===

def cmd_event(argv: List[str]) -> int:
    """
    處理 'python yscb.py event <subcommand>'。
    - 'list': 讀取 get_contributed_events()，格式化印出 ASCII/Markdown 表格
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: core.events.py]
  - 實作 broadcast() 與 get_contributed_events()
  - 導出至 core/__init__.py
         |
         +---------------------------------------+
         v                                       v
[Step 2: core 模組內部解耦]              [Step 4: yscb.py 宿主整合]
  - 移除 Engine.act_broadcast_event        - 加入 cmd_event ("event list")
  - installer.py 改調用 core.events        - 分發前置呼叫 pre_cli_dispatch
  - engine.py 改調用 core.events           - 分發後置呼叫 post_cli_dispatch
  - contribute.json 加入 events 宣告             |
         |                                       v
         v                               [Step 5: agents-workflow 對齊]
[Step 3: dev 模組沙盒收斂]                 - hook.core.py 實作 on_pre_cli_dispatch
  - sandbox.py 移除重複實作                - scripts/cli.py 移除 Ad-hoc 攔截
  - 改調用 core.events.broadcast                 |
         |                                       v
         +---------------------------------------+
                                 |
                                 v
                 [Step 6: 單元與整合測試驗證]
                   - core/tests/test_events_pipeline.py
                   - 全生態系 dev test 回歸
```
