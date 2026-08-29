# Dev 模組擴充貢獻格式說明書 (Dev Contributes Specification)

> 模組名稱：`dev`  
> 模組版本：`1.0.0`  
> 職責定位：YS-Codebase 官方開發者工具箱（模組腳手架、靜態檢查、純淨打包、單元測試引擎）。

---

## 1. 宣告式擴充點 (Contribution Points)

`dev` 模組透過 `source/dev/contributes/` 目錄向全系統宣告擴充：

### 1.1 向 `core` 貢獻 (`contributes/core.json`)
注入開發者專屬空間協議與 CLI 開發指令清冊：
```json
{
  "uri_schemes": [
    {
      "token": "module.source",
      "type": "const",
      "value": "yscb://source/",
      "description": "模組源碼空間根目錄"
    },
    {
      "token": "module.build",
      "type": "const",
      "value": "yscb://build/",
      "description": "本地開發完整建置產物空間根目錄"
    },
    {
      "token": "module.release",
      "type": "const",
      "value": "yscb://release/",
      "description": "模組發布來源空間根目錄"
    }
  ],
  "commands": {
    "test": {
      "description": "Run module tests inside an isolated sandbox",
      "case_pros": [
        "正在開發當前模組，需驗證單元邏輯或整體功能 (Phase 5/6)",
        "微調時優先附加 --no-build 或 -k <pattern> 快速跑測"
      ],
      "case_cons": [
        "🚨 嚴禁在跑測前手動執行 dev build",
        "🚨 嚴禁在日常開發中執行 dev test --all",
        "🚨 嚴禁調用內部原子操作 dev op-test"
      ]
    }
  }
}
```

### 1.2 向 `agents-workflow` 貢獻 (`contributes/agents-workflow.json`)
注入開發者專屬 Agent 行為準則與 Dogfooding 工程規範：
```json
{
  "insert": [
    {
      "type": "uri",
      "token": "AGENTS_STANDARDS",
      "value": "module://dev/assets/standards/DevAgentsStandards.md",
      "mode": "below"
    }
  ]
}
```
