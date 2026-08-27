<!--

Phase 3 執行指引：
1. 目標：完成所有 Public/Internal API 簽名、型態契約、錯誤處理策略與實作依賴拓撲順序。
2. 介面契約：明確定義類別/函式/介面之命名、職責、參數型態、返回值型態與顯式物理/數學單位。
3. 錯誤策略：定義所有可能拋出的自定義例外與邊界防禦處理契約。
4. 依賴拓撲：定義由底層至上層的無環依賴實作拓撲順序 (Implementation Topology)，作為 Phase 5 依序實作之剛性依據。
5. Checkpoint 等待關卡：等待開發者明確確認 P03 內容（狀態更新為 Confirmed）後推進至 Phase 4。

-->

# API 與介面規格書 (API & Interface Specification)

> 功能名稱：agents-workflow 添加 codex 與 claude code release targets  
> 建立日期：2026-08-27  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `contributes.agents-workflow.release_target` | `manifest.json` | Public (Declarative) | 宣告 `claude` 與 `codex` 之名稱、描述與 workflow/template/standard 路徑投影與 Header 規格 |
| `ReleaseTargetManager` | `agents_workflow/targets.py` | Public | 讀取與管理可用/已啟用的 Targets 清冊（支援 `claude`、`codex`、`antigravity`） |
| `ReleasePublisher` | `agents_workflow/publisher.py` | Public | 執行發布流水線，動態解析各 Target 之拓撲並物化檔案 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `manifest.json` 宣告契約

```json
{
  "name": "claude",
  "description": "Anthropic Claude Code 原生 Slash Commands 與標準規範輸出",
  "projections": {
    "workflow": {
      "target_dir": "project://.claude/commands",
      "extension": ".md",
      "header": [
        "---",
        "description: {export.description}",
        "---"
      ]
    },
    "template": {
      "target_dir": "project://.claude/.yscb/templates",
      "extension": ".md"
    },
    "standard": {
      "target_dir": "project://.claude/.yscb/standards",
      "extension": ".md"
    }
  }
},
{
  "name": "codex",
  "description": "OpenAI Codex CLI / VS Code Extension 原生工作流與標準規範輸出",
  "projections": {
    "workflow": {
      "target_dir": "project://.codex/workflows",
      "extension": ".md",
      "header": [
        "---",
        "description: {export.description}",
        "---"
      ]
    },
    "template": {
      "target_dir": "project://.codex/.yscb/templates",
      "extension": ".md"
    },
    "standard": {
      "target_dir": "project://.codex/.yscb/standards",
      "extension": ".md"
    }
  }
}
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Manifest Declaration]
  └─► ys_codebase/source/agents-workflow/manifest.json (宣告 claude 與 codex targets)
       │
       ▼
[Step 2: Automated Tests]
  └─► ys_codebase/source/agents-workflow/tests/test_targets.py (編寫 Target 掃描與發布物化測試)
       │
       ▼
[Step 3: Verification & Sandbox Run]
  └─► python yscb.py dev test agents-workflow (虛擬沙盒全量回歸)
       │
       ▼
[Step 4: Documentation]
  └─► docs/agents-workflow/user_guide.md (更新知識庫)
```
