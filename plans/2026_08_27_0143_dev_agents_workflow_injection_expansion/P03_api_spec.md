# API 與介面規格書 (API & Interface Specification)

> 功能名稱：擴充 Dev 模組對 Agents-Workflow 注入之工程規範與指令防呆 (Dev Injection Expansion & Command Abuse Guardrails)  
> 建立日期：2026-08-27  
> 所屬主計畫：2026_08_27_0143_dev_agents_workflow_injection_expansion  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別 / 檔案 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `get_agents_cli_guild` | `source/core/core/providers.py` | `Public` | 動態 Token Provider：掃描 `contributes.core.commands`，過濾 pros/cons 皆空項目，生成 Markdown 防呆對照表。 |
| `_get_installed_module_commands` | `yscb.py` | `Internal` | 宿主 CLI 輔助函式：僅讀取 `contributes.core.commands`，提取 `description` 渲染標準 CLI Help。 |
| `contributes.core.commands` Schema | `source/<module>/manifest.json` | `Contract` | 宣告式 CLI 指令與防呆情境之 JSON Schema 規範。 |
| `AgentsCliGuild.md` | `source/agents-workflow/assets/standards/AgentsCliGuild.md` | `Standard` | 標準文檔資產：內嵌 `__@{AGENTS_CLI_GUILD}__` 錨點自動物化全系統 CLI 防呆指南。 |
| `AgentsStandards.md` | `source/agents-workflow/assets/standards/AgentsStandards.md` | `Standard` | 規範資產：注入 CLI 比對與未列情境強制向開發者確認之剛性守門。 |
| `ContextInit.md` | `source/agents-workflow/assets/workflows/ContextInit.md` | `Workflow` | 工作流模板：使用 `__#{module://...}__` 原文件指針轉譯，清理過時設定。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `core.providers.get_agents_cli_guild`
```python
from typing import Dict, Any, Optional, List

def get_agents_cli_guild(contributes_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
    """
    動態編譯已安裝/宣告模組之 contributes.core.commands 為 Markdown 防呆對照表。
    
    過濾與格式化規則：
    1. 遍歷 contributes_data 或本機 modules/ 下所有模組之 contributes.core.commands。
    2. 若指令之 case_pros 與 case_cons 兩者皆無或皆為空陣列/空字串，則自動排除於清單。
    3. 對於有定義者，防禦性支援字串與陣列型別，格式化為：
       | 指令 (Command) | 說明 (Description) | ✅ 推薦/適用情境 (case_pros) | 🚨 絕對禁止/不適用情境 (case_cons) |
    4. 若全系統無任何模組定義有效防呆指令，回傳友善提示字串。
    
    :param contributes_data: 可選之全域 merged contributes 字典 (由編譯器傳入)
    :return: 格式化完成之 Markdown 表格字串 (純 ASCII 排版)
    """
```

### 2.2 `yscb.py:_get_installed_module_commands`
```python
def _get_installed_module_commands(base_dir: str, yscb_root: str) -> Dict[str, Dict[str, str]]:
    """
    掃描 modules/ 下所有已安裝模組，僅讀取 manifest.json 中之 contributes.core.commands。
    
    適配規則：
    1. 僅讀取 mf_data.get("contributes", {}).get("core", {}).get("commands", {})。
    2. 徹底忽略舊版頂層 mf_data.get("contributes", {}).get("commands")。
    3. 對於每個子指令，若值為 dict 則提取 desc = val.get("description", "")；
       若值為 str 則 desc = val。
    4. 回傳格式為 { module_name: { subcommand: description } }。
    """
```

### 2.3 `contributes.core.commands` JSON Schema 契約
```json
{
  "type": "object",
  "patternProperties": {
    "^[a-zA-Z0-9_-]+$": {
      "type": "object",
      "required": ["description"],
      "properties": {
        "description": { "type": "string" },
        "case_pros": {
          "type": "array",
          "items": { "type": "string" }
        },
        "case_cons": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "additionalProperties": false
    }
  }
}
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Core 模組升級]
  ├── 1.1 source/core/core/providers.py 實作 get_agents_cli_guild (過濾與 Markdown 表格生成)
  ├── 1.2 source/core/manifest.json 宣告 contributes.core.commands 與 AGENTS_CLI_GUILD Token
  └── 1.3 source/core/tests/test_cli_guild.py 單元測試 (驗證過濾演算法與型別防禦)
       │
       ▼
[Step 2: yscb.py 宿主起手腳本適配]
  └── 2.1 yscb.py 修改 _get_installed_module_commands 僅自 contributes.core.commands 讀取
       │
       ▼
[Step 3: Dev 模組防呆宣告更新]
  ├── 3.1 source/dev/manifest.json 遷移並宣告 6 大指令之 description, case_pros, case_cons
  └── 3.2 source/dev/assets/standards/DevEngineeringStandards.md 精簡並引導至 AgentsCliGuild.md
       │
       ▼
[Step 4: Agents-Workflow 標準與導出更新]
  ├── 4.1 source/agents-workflow/manifest.json 遷移 commands 並宣告 export AgentsCliGuild.md
  ├── 4.2 source/agents-workflow/assets/standards/AgentsCliGuild.md 新增資產 (內嵌 Token)
  ├── 4.3 source/agents-workflow/assets/standards/AgentsStandards.md 注入強制確認守門鐵律
  └── 4.4 source/agents-workflow/assets/workflows/ContextInit.md 修復原文件超連結指針與清理過時設定
```

---
