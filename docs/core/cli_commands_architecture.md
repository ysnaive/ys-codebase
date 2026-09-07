# Core Commands 架構與 CLI 派發合約手冊 (Core Commands Architecture)

> 模組名稱：`core.commands`  
> 所屬模組：`core`  
> 職責定位：YS-Codebase 核心命令引擎、Contributes Commands Schema 解析、正交選項解析、強型別 CmdBags 容器與雙管道派發管線。

---

## 1. 架構概覽 (Architecture Overview)

`core.commands` 作為微內核標準 CLI 派發中樞，取代傳統各模組自造 `argparse` 與宿主腳本硬編碼黑名單的做法。

```text
yscb.py (Thin Host) ──► core.commands.dispatch()
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   [server_compatible: true]         [server_compatible: false]
             │                                 │
             ▼                                 ▼
      Server Warm Worker               Local Cold Dispatch
             │                                 │
             └────────────────┬────────────────┘
                              ▼
           pre_cli_dispatch Hook (core.events)
                              ▼
           OptionResolver (Orthogonal Groups & CmdBags)
                              ▼
           Module Contract: def cmd_name(cmd_bags: CmdBags)
           (Fallback: mod.process(args) for unmigrated modules)
                              ▼
           post_cli_dispatch Hook (core.events)
```

---

## 2. Contributes Commands Schema 規範

模組於 `contributes/core.json` 宣告提供的 CLI 能力。架構採用**同構遞迴指令樹 (Homogeneous Recursive Command Tree)**，徹底分離指令分支與葉子節點的參數作用域：

```json
{
  "commands": {
    "module_alias": ["mod_alias1"],
    "description": "模組領域簡介",
    "cmd": {
      "command_name": {
        "description": "指令或分支功能說明",
        "tier": "safe | gated | conditional",
        "server_compatible": true,
        "args": {
          "param_name": {
            "description": "位置參數說明",
            "required": true,
            "choice": ["val_a", "val_b"]
          }
        },
        "options": {
          "orthogonal_group_name": {
            "option_canonical_name": {
              "description": "選項說明",
              "alias": ["opt_alias"],
              "args": {
                "val_name": {
                  "description": "選項值說明",
                  "choice": ["opt_a", "opt_b"]
                }
              }
            }
          }
        },
        "cmd": {
          "subcommand_name": {
            "description": "同構遞迴子命令宣告 (結構與父層完全一致)",
            "tier": "safe",
            "args": { ... },
            "options": { ... }
          }
        },
        "usage": {
          "pros": ["推薦情境"],
          "cons": ["禁止情境"]
        }
      }
    }
  }
}
```

### 關鍵欄位約束與規範
1. **`module_alias`**：模組別名清單，可替代模組名稱進行命令派發匹配（不同模組宣告重複別名時拋出 EC-06）。
2. **同構遞迴 `cmd` 樹**：任何節點均可透過 `cmd` 巢狀掛載子指令，支援無限層級遞迴。
3. **參數模型收斂 (`args` 字典)**：
   - 徹底移除歷史 `has_value` 旗標，不向下相容。
   - 指令本體之位置參數與 Option 之參數統一以 `args` 字典組織 (`{ "<arg_name>": { "description", "required", "choice" } }`)。
   - Option 若具備 `args` 則為帶參選項；若無 `args` 則為布林旗標 (Flag)。
   - `choice`：支援枚舉約束清單。`OptionResolver` 自動校驗合法值 (EC-07)，`HelpRenderer` 自動格式化提示（如 `<mode=[auto | safe]>`）。
4. **`tier`**：安全權限等級（`safe` 🟢 / `gated` 🔴 / `conditional` 🟡）。
5. **`server_compatible`**：**指令層級**獨立宣告之原生布林值。為 `true` 且常駐在線時走 HTTP IPC 熱派發。
6. **`options`**：外層為正交群組名稱。同群組內的選項強制互斥 (EC-02)。

### 2.1 參數型態之結構化推導原則 (Structural Derivation Rules)

為保持 Contributes JSON 的語法精煉，系統**全面採用結構化推導 (Structural Derivation)** 來判定 CLI 參數型態，無需冗餘的 `"type": "var"` 標籤：

| 參數型態 | CLI 語法形式 | JSON 宣告位置 | 結構特徵 (Structural Signature) | 派發與驗證行為 |
| :--- | :--- | :--- | :--- | :--- |
| **位置變數 (Positional Var)** | `install <module>`<br/>`uri resolve <uri>` | `cmd.<name>.args` | 位於指令頂層 `args` 字典內（無前綴 `--`） | 由位置循序消耗；未傳入拋出 `MissingArgumentError` (EC-08)；不符 choice 拋出 `InvalidChoiceError` (EC-07)。 |
| **布林旗標 (Boolean Flag)** | `search --json`<br/>`remove -f` | `cmd.<name>.options.<group>.<opt>` | 位於 `options` 內，且**無 `args`** 字典 | 具有前綴 `--` / `-`；存在即判定為 True（亦支援 `--flag=false`）；不消耗後續參數。 |
| **帶值選項 (Option Var)** | `config list --mod=<mod>`<br/>`update -p <url>` | `cmd.<name>.options.<group>.<opt>.args` | 位於 `options` 內，且**掛載 `args`** 字典 | 具有前綴 `--` / `-`；強制消耗後續值（或透過 `--opt=val` 賦值）；缺少值拋出 `MissingValueError` (EC-03)。 |

#### 結構宣告對照範例：
```json
{
  "cmd": {
    "install": {
      "description": "Install package",
      "args": {
        "module": { "description": "模組名稱", "required": true }      // 👈 [Positional Var] 必填位置變數
      },
      "options": {
        "flags": {
          "force": { "description": "強制重裝", "alias": ["f"] }       // 👈 [Boolean Flag] 布林旗標 (無 args)
        },
        "source": {
          "provider": {
            "description": "指定來源",
            "args": { "url": { "description": "Provider URL" } }       // 👈 [Option Var] 帶值選項 (有 args)
          }
        }
      }
    }
  }
}
```

---

## 3. 三態指令派發模型 (Tri-State Dispatch Model)

派發器由左至右走訪 CLI Tokens 匹配指令樹，支援三種自然節點型態：

1. **純葉子指令 (Pure Leaf)**：
   - 未宣告 `cmd` 子項。
   - 實體函式：必須於模組 `scripts/cli.py` 提供對應函式（如 `cli.install(cmd_bags)`）。
2. **純分支指令 (Pure Group)**：
   - 宣告 `cmd` 子項，但模組未定義自身的實作函式（例如純作為命令分類）。
   - 執行行為：CLI 直接呼叫時（如 `python yscb.py uri`），**自動渲染該分支的 `AVAILABLE SUBCOMMANDS:` 清單與詳細說明**，無須模組編寫重複的幫助代碼。
3. **可呼叫複合分支 (Callable Group / Hybrid Node)**：
   - 宣告 `cmd` 子項，且模組亦提供了自身實體函式（如 `cli.config(cmd_bags)`）。
   - 執行行為：
     - 若下一個 Token **命中** `cmd` 子項（如 `python yscb.py config get`）➔ 轉派至子指令 `cli.config_get(cmd_bags)`，享有獨立參數作用域。
     - 若下一個 Token **未命中**子項或無後續參數 ➔ 視為當前層級參數，直接執行 `cli.config(cmd_bags)`。

---

## 4. 強型別 `CmdBags` 容器

模組精確命令函式接收不可變 `CmdBags`：

```python
@dataclass(frozen=True)
class CmdOption:
    name: str          # 規範名稱 (不含前綴 --)
    params: Any = True # 選項值

@dataclass(frozen=True)
class CmdBags:
    raw_cmd: str                          # 完整原始字串
    command: str                          # 目標子命令規範名 (底線平鋪)
    args: List[str]                       # 循序位置參數 (已隔離且已完成 required/choice 校驗)
    options: Dict[str, CmdOption]         # 規範名索引之選項

    def has_option(self, name: str) -> bool: ...
    def get_option_value(self, name: str, default: Any = None) -> Any: ...
```

---

## 5. 模組精確合約 (Module Execution Contract)

模組於 `scripts/cli.py` 定義獨立函式，函式名稱依指令路徑以底線連接平鋪：

```python
from core.commands.bags import CmdBags
from core.guard import guard_dispatch

# 葉子指令直接命名
def status(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    return 0

# 巢狀子指令以底線平鋪 (如 'uri resolve' -> uri_resolve)
def uri_resolve(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    target_uri = cmd_bags.args[0] # OptionResolver 已保證必填性
    return 0

# 複合分支自身實作 (如 'config' 本體呼叫)
def config(cmd_bags: CmdBags) -> int:
    guard_dispatch("core")
    return 0
```

### 雙軌向後相容過渡層 (Backward Compatibility)
若目標模組尚未遷移為精確函式模式，派發器靜默退化至舊契約 `mod.process(args)`（無 warning 輸出）。本過渡層為暫存債務，於 `sub_02` 全模組遷移完成後剛性移除。

