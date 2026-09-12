# API 與介面規格書 (API & Interface Specification)

> 功能名稱：core.commands 活躍執行合約與 CLI 派發管線重構  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `CmdOption` | `core/commands/bags.py` | Public | 不可變選項封裝 (規範名與參數值) |
| `CmdBags` | `core/commands/bags.py` | Public | 結構化命令參數容器 (規範名、位置參數、選項字典) |
| `OptionSpec` / `CommandSpec` / `ModuleSpec` | `core/commands/registry.py` | Public | Contributes Schema 強型別規格模型 |
| `CommandsRegistry` | `core/commands/registry.py` | Public | 聚合載入 contributes、建立別名映射、檢索規格 |
| `OptionResolver` | `core/commands/resolver.py` | Public | 參數解析、正交群組互斥檢查、別名轉規範名 |
| `HelpRenderer` | `core/commands/help.py` | Public | 統一終端 Help 格式化輸出 (模組級與指令級) |
| `CommandDispatcher` | `core/commands/dispatcher.py` | Public | 派發管線調度、雙管道分流、對稱 Hook、向後相容調用 |
| `dispatch(argv)` | `core/commands/__init__.py` | Public | 核心命令引擎單一外部入口函式 |
| `<cmd_name>(cmd_bags)` | `source/<module>/scripts/cli.py` | Public | 模組端精確命令函式合約 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 強型別資料結構 (`core/commands/bags.py`)

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class CmdOption:
    """不可變命令選項資料結構。"""
    name: str          # Option 規範名稱 (Canonical Name, 不含前綴 --)
    params: Any = True # 參數值 (Flag 為 True；帶值選項為 str/int 等解析值)


@dataclass(frozen=True)
class CmdBags:
    """強型別命令參數封裝容器。"""
    raw_cmd: str                                      # 原始輸入參數字串 (例如 "status --json")
    command: str                                      # 目標子命令規範名 (例如 "status")
    args: List[str] = field(default_factory=list)     # 循序位置參數 (Positional Arguments)
    options: Dict[str, CmdOption] = field(default_factory=dict) # 以 Option 規範名索引

    def has_option(self, name: str) -> bool:
        """判定是否存在指定規範名稱之選項。"""
        return name in self.options

    def get_option_value(self, name: str, default: Any = None) -> Any:
        """取得選項之參數值，若不存在則返回 default。"""
        opt = self.options.get(name)
        return opt.params if opt is not None else default
```

### 2.2 規格定義與註冊中心 (`core/commands/registry.py`)

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class ArgSpec:
    """規格定義：參數規格 (指令位置參數或選項參數)。"""
    name: str
    description: str = ""
    required: bool = True
    choice: Optional[List[str]] = None

@dataclass
class OptionSpec:
    canonical_name: str
    description: str = ""
    alias: List[str] = field(default_factory=list)
    args: Dict[str, ArgSpec] = field(default_factory=dict)
    group_name: str = "default"

    @property
    def takes_value(self) -> bool:
        return bool(self.args)

@dataclass
class CommandSpec:
    name: str
    description: str = ""
    tier: str = "safe"              # safe | warning | danger | gated
    server_compatible: bool = False  # 原生布林值 (指令維度)
    args: Dict[str, ArgSpec] = field(default_factory=dict)        # ordered args specs
    options: Dict[str, OptionSpec] = field(default_factory=dict)  # canonical_name -> OptionSpec
    groups: Dict[str, List[str]] = field(default_factory=dict)    # group_name -> [canonical_names]
    usage_pros: List[str] = field(default_factory=list)
    usage_cons: List[str] = field(default_factory=list)
    cmd: Dict[str, "CommandSpec"] = field(default_factory=dict)   # 遞迴同構子指令樹 (FR-12)

@dataclass
class ModuleSpec:
    module_name: str
    description: str = ""
    module_alias: List[str] = field(default_factory=list)
    commands: Dict[str, CommandSpec] = field(default_factory=dict)

class CommandsRegistry:
    def __init__(self) -> None:
        self._modules: Dict[str, ModuleSpec] = {}
        self._alias_to_module: Dict[str, str] = {}

    def register_module(self, module_name: str, contributes_commands: Dict[str, Any]) -> ModuleSpec:
        """解析新 Schema 並註冊模組指令清單，支援同構遞迴 cmd 樹 (FR-12)，檢核模組別名衝突 (EC-06)。"""
        ...

    def resolve_module_name(self, candidate: str) -> Optional[str]:
        """依候選字串檢索模組名 (支援 module_name 與 module_alias)。"""
        ...

    def resolve_command_node(self, module_name: str, tokens: List[str]) -> Tuple[List[str], Optional[CommandSpec], List[str]]:
        """沿 tokens 走訪指令樹，返回 (matched_path, target_spec, remaining_tokens)。"""
        ...

    def get_command_spec(self, module_name: str, cmd_name: str) -> Optional[CommandSpec]:
        """取得特定模組之特定命令規格。"""
        ...
```

### 2.3 參數解析器與防呆校驗 (`core/commands/resolver.py`)

```python
class OptionResolver:
    @staticmethod
    def resolve(cmd_spec: CommandSpec, raw_args: List[str]) -> Tuple[List[str], Dict[str, CmdOption]]:
        """
        解析 CLI 原始參數為 (positional_args, options)。
        - 檢查同一正交群組多選互斥 (EC-02)，衝突拋出 MutualExclusionError
        - 檢查帶參選項缺少參數值 (EC-03)，缺少拋出 MissingValueError
        - 檢查位置參數與選項值之 choice 列舉合法性 (EC-07)，違規拋出 InvalidChoiceError
        - 檢查必填位置參數完整性 (EC-08)，缺少拋出 MissingArgumentError
        - 將選項別名映射為規範名稱 (FR-03)
        """
        ...
```

### 2.4 派發器與外部入口 (`core/commands/dispatcher.py` & `__init__.py`)

```python
def dispatch(argv: Optional[List[str]] = None) -> int:
    """
    核心命令引擎全域唯一入口函式。
    負責：
    1. 解析模組與命令名稱 (含別名比對與未知模糊建議 EC-01)
    2. --help 統一攔截與格式化輸出 (FR-05)
    3. 判定 server_compatible 指令級分流 (FR-06)
    4. 生命週期 pre_cli_dispatch / post_cli_dispatch 對稱廣播 (FR-10)
    5. 動態呼叫目標函式：優先 getattr(mod, cmd_name)(cmd_bags)，
       若未遷移則靜默退化至 mod.process(args) (FR-08)
    """
    ...
```

### 2.5 模組端精確合約 (`source/<module>/scripts/cli.py`)

```python
# 模組內部每個命令定義為獨立函式，接收 CmdBags 並返回 int 退出碼
def status(cmd_bags: CmdBags) -> int:
    """檢查狀態，透過 cmd_bags.has_option('json') 等判定選項。"""
    ...

def start(cmd_bags: CmdBags) -> int:
    """啟動常駐守護進程。"""
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
bags.py (CmdOption, CmdBags)
  │
  ├──► registry.py (SchemaParser, CommandsRegistry)
  │      │
  │      ├──► resolver.py (OptionResolver, MutualExclusionCheck)
  │      │      │
  │      │      ├──► help.py (HelpRenderer)
  │      │      │      │
  │      │      │      ▼
  │      └──────┴──► dispatcher.py (CommandDispatcher, dispatch)
  │                            │
  ▼                            ▼
core/__init__.py ◄── yscb.py (Host Router)
  │
  ▼
source/core/scripts/cli.py & source/server/scripts/cli.py (Pioneer Migration)
```
