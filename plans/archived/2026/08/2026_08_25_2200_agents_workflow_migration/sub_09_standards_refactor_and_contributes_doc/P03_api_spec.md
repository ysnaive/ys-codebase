# API 與介面規格書 (API & Interface Specification)

> 功能名稱：開發標準規範與流程分離重構及 Contributes 文檔建立 (Standards & Workflow Separation & Contributes Doc)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ReleasePublisher` | `source/agents-workflow/agents_workflow/publisher.py` | Public | 負責解析 Target 拓撲、 Header 渲染、 `AgentsStandards` 提取、 `enable_agents_md` 守門與 4 步原子發布交易。 |
| `ArtifactCompiler` | `source/agents-workflow/agents_workflow/compiler.py` | Public | 負責 Stage 1 多輪 Token 替換解算與 Stage 2 語意 URI 轉譯（相容雙 Standard 資產）。 |
| `manifest.json` | `source/agents-workflow/manifest.json` | Public Schema | 宣告 `AgentsStandards.md` 與 `DevelopmentStandards.md` export 與 Token 注入點。 |
| `config.project.json` | `source/agents-workflow/config.project.json` | Config Schema | 定義 `paths`、 `release_targets` (預設 `[]`)、 `enable_agents_md` 與 `enable_project_changelog`。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `ReleasePublisher._soft_merge_agents_md`
```python
def _soft_merge_agents_md(self, agents_standards_content: str, proj_root: str) -> bool:
    """
    執行 AGENTS.md 軟合併注入 (僅注入精簡版 AgentsStandards)：
    1. 若 AGENTS.md 不存在，建立全新骨架並注入 AgentsStandards 內容至 YSCB 標記區塊。
    2. 若已存在，以正則替換 <!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END --> 內部為最新 agents_standards_content。
    3. 100% 完整保留使用者在標籤外定義之 ## 4. 專案特化工程規範。
    
    Args:
        agents_standards_content: 已完成 Stage 2 URI 轉譯之 AgentsStandards 內文。
        proj_root: 宿主工程根目錄實體絕對路徑。
    Returns:
        bool: 軟合併成功返回 True，異常返回 False。
    """
```

### 2.2 `ReleasePublisher.release_all`
```python
def release_all(self, interactive: bool = False) -> Dict[str, Any]:
    """
    執行 4 步原子發布交易流水線：
    1. compile_stage1() 解算包含 AgentsStandards.md 與 DevelopmentStandards.md 之所有資產。
    2. 讀取 config.project.json 中的 release_targets, enable_agents_md, enable_project_changelog。
    3. 若 release_targets 為空 []，安全略過 IDE 目錄檔案寫入 (published_count = 0)。
    4. 若 enable_agents_md 為 True 且提取到 AgentsStandards，執行 _soft_merge_agents_md。
    5. 若 enable_agents_md 為 False，跳過 AGENTS.md 軟合併。
    6. 原子寫入 storage:// release_manifest.json。
    
    Returns:
        Dict[str, Any]: {
            "success": bool,
            "published_count": int,
            "active_targets": List[str],
            "orphan_targets": List[str],
            "removed_count": int
        }
    """
```

### 2.3 `manifest.json` 擴充宣告
```json
{
  "contributes": {
    "agents-workflow": {
      "export": [
        {
          "type": "standard",
          "source": "module://agents-workflow/assets/standards/AgentsStandards.md",
          "description": "Agent 專案核心原則與防呆紀律規範"
        },
        {
          "type": "standard",
          "source": "module://agents-workflow/assets/standards/DevelopmentStandards.md",
          "description": "標準開發流程手冊與作業規範"
        }
      ],
      "insert": [
        {
          "type": "uri",
          "token": "AGENTS_STANDARDS",
          "value": "module://agents-workflow/assets/standards/AgentsStandards.md",
          "mode": "replace"
        },
        {
          "type": "uri",
          "token": "DEVELOPMENT_STANDARDS",
          "value": "module://agents-workflow/assets/standards/DevelopmentStandards.md",
          "mode": "replace"
        }
      ]
    }
  }
}
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 資產拆分]
  ├── 1.1 新增 source/agents-workflow/assets/standards/AgentsStandards.md (收斂第 1 章核心原則)
  └── 1.2 重構 source/agents-workflow/assets/standards/DevelopmentStandards.md (收斂工作目錄/ID/SOP流程)

[Step 2: Contributes 宣告與組態調整]
  ├── 2.1 修改 source/agents-workflow/manifest.json (註冊 AgentsStandards export & Token)
  ├── 2.2 修改 source/agents-workflow/config.project.json (release_targets 預設值改為 [])
  └── 2.3 建立 source/agents-workflow/contributes.format.md (官方完整 Contributes 規格書)

[Step 3: 發布引擎邏輯重構]
  └── 3.1 修改 source/agents-workflow/agents_workflow/publisher.py
        ├── 提取 AgentsStandards 替代 DevelopmentStandards
        ├── 落實 enable_agents_md: false 守門跳過
        └── 支援 release_targets: [] 空清單安全發布

[Step 4: 單元測試與回歸驗證]
  ├── 4.1 修改 source/agents-workflow/tests/test_publisher.py (擴充單元測試覆蓋新行為)
  └── 4.2 執行 dev test agents-workflow 與 dev test --all (回歸驗證)
```
