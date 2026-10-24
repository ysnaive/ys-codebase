# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_04_onboarding_and_config_coaching  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ArtifactCompiler._resolve_source_path` | `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Internal | 解析語意 URI 或相對路徑至本機實體檔案/目錄路徑，支援跨模組同級目錄安全 Fallback。 |
| `tokens(cmd_bags: Any) -> int` | `ys_codebase/source/agents-workflow/scripts/cli.py` | Public CLI | 輸出全系統已註冊之 Token 錨點清單，相容 `TokenAnchorDef` 之 `value` 與 `name` 欄位。 |
| `PROJECT_ROLE_AND_BOUNDARIES` | `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Public Token | `AgentsStandards.md` 頂部之專案角色與主客體空間邊界選配注入錨點。 |
| `HOW_TO_CONFIG_MODULES` | `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Public Token | `how-to-config-yscb/SKILL.md` 內供各已安裝模組注入「模組設定與健康度速查卡」之錨點。 |
| `HOW_TO_YSCB_MODULES` | `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Public Token | `how-to-yscb/SKILL.md` 內供各已安裝模組注入「標準用法速查卡」之錨點。 |
| `how-to-config-yscb` | `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md` | Public Skill | 主動指令型設定體檢、三處聯動對齊草擬與確認後代寫修復技能。 |
| `how-to-yscb` | `ys_codebase/source/agents-workflow/assets/skills/how-to-yscb/SKILL.md` | Public Skill | 主動指令型互動式教練引導、跨模組速查與新開實戰 Session 隔離技能。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. ys_codebase/source/agents-workflow/agents_workflow/compiler.py
class ArtifactCompiler:
    def _resolve_source_path(self, path_or_uri: str) -> str:
        """
        解析語意 URI 或相對路徑至本機實體檔案/目錄路徑。
        - Pre-conditions: path_or_uri 為非空字串（如 'module://core/assets/config_guide.md' 或本地路徑）。
        - Post-conditions:
          1. 優先透過 core.uri.resolve(path_or_uri, interactive=False) 解析並檢查檔案存在。
          2. 若為 'module://<mod>/<rel_p>' 且 Step 1 未命中：
             - 當 <mod> == 'agents-workflow' 時，檢查 os.path.join(self.module_root, rel_p)。
             - 當 <mod> != 'agents-workflow' 時，檢查同級目錄 os.path.join(os.path.dirname(self.module_root), <mod>, rel_p)，嚴禁跨模組誤退回 self.module_root。
          3. 若仍不存在則回傳空字串 ""。
        """

# 2. ys_codebase/source/agents-workflow/scripts/cli.py
def tokens(cmd_bags: Any) -> int:
    """
    檢視全系統已註冊之 Token 錨點清單與語意 URI 說明。
    - Pre-conditions: 讀取 compiler.get_registered_tokens() 清單。
    - Post-conditions: 對每一筆 tok 字典取 val = tok.get("value") or tok.get("name") or ""，確保使用 'value' 或 'name' 註冊之 Token 皆完整顯示名稱並回傳 0。
    """
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `_resolve_source_path` 遇無效 URI 或不存在檔案時優雅返回 `""`，不拋出未捕獲例外；`compile_stage1` 對無法讀取之 `export` 項目記入 `errors` 清單。
  - 跨模組注入片段若含未以反引號包裹之動態標籤，`check_unenclosed_tags` 必定於 `stderr` 輸出 `[compiler:warning] Unenclosed placeholder tag`。
- **階段決策紀錄**：`[P03:DR-01]` 統一四大核心模組之跨模組注入片段路徑為 `module://<mod>/assets/config_guide.md`（注入 `HOW_TO_CONFIG_MODULES`）與 `module://<mod>/assets/usage_guide.md`（注入 `HOW_TO_YSCB_MODULES`），標題格式分別固定為 `### ⚙️ <模組名稱> 設定與體檢` 與 `### 📦 <模組名稱> (<一句話定位>)`。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1 (底層編譯器與 CLI 修復):
  compiler.py (_resolve_source_path 跨模組同級目錄防串線)
  + scripts/cli.py (tokens 兼容 value/name)
      │
      ▼
Step 2 (agents-workflow 錨點、標準規範與雙星技能建置):
  assets/standards/AgentsStandards.md (__@{PROJECT_ROLE_AND_BOUNDARIES}__)
  + assets/skills/how-to-config-yscb/SKILL.md (__@{HOW_TO_CONFIG_MODULES}__)
  + assets/skills/how-to-yscb/SKILL.md (__@{HOW_TO_YSCB_MODULES}__)
  + assets/skills/context-init/SKILL.md (提取 Role 邊界與狀態卡提示)
  + contributes/agents-workflow.json & _manifest.md
      │
      ▼
Step 3 (四大核心模組跨模組雙片段與 Contributes 宣告):
  core / dev / server / knowledge-db:
  assets/{config_guide.md, usage_guide.md} + contributes/{agents-workflow.json, _manifest.md}
      │
      ▼
Step 4 (單元測試與三層文檔同步，後續由 /how-to-config-yscb 實機探勘代寫 project_role.md & testing_guide.md):
  tests/{test_compiler.py, test_plans_model_record.py}
  + docs/agents-workflow/ & source/agents-workflow/README.md
```

