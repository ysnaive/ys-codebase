# Core 模組貢獻擴充格式說明書 (contributes.format.md)

> 本文件定義其他模組在 `manifest.json` 或 `contributes.core.json` 中向 `core` 宣告擴充之標準格式。

---

## 1. 支援之擴充點清單 (Contribution Points)

| 擴充鍵名 (Key) | 說明 | 格式型別 |
| :--- | :--- | :--- |
| **`path_placeholders`** | 註冊自訂路徑佔位符（用於 URI 解算，例 `{workspace_id}`） | `array[object]` |
| **`uri_schemes`** | 註冊自訂語意 URI 協議（例 `plans://...`, `docs://...`） | `array[object]` |
| **`events`** | 訂閱核心生命週期事件（例 `on_install`, `on_reload`） | `array[object]` |

---

## 2. Schema 定義與宣告範例

### 2.1 路徑佔位符 (`path_placeholders`)
```json
{
  "path_placeholders": [
    {
      "token": "workspace_id",
      "handler": "scripts/resolvers.py:resolve_workspace",
      "description": "解析當前工作區識別碼"
    }
  ]
}
```

### 2.2 語意 URI 協議 (`uri_schemes`)
```json
{
  "uri_schemes": [
    {
      "token": "plans",
      "type": "config",
      "value": "paths.plans_dir",
      "description": "指向專案活躍開發計畫目錄"
    },
    {
      "token": "docs",
      "type": "config",
      "value": "paths.docs_dir",
      "description": "指向專案知識庫文檔目錄"
    },
    {
      "token": "custom_cache",
      "type": "const",
      "value": "yscb://.cache/{module}/custom/",
      "description": "模組自訂暫存快取目錄"
    }
  ]
}
```

### 2.3 生命週期事件訂閱 (`events`)
```json
{
  "events": [
    {
      "event_name": "on_reload",
      "handler": "scripts/hooks.py:on_env_reloaded",
      "description": "當環境重構刷新完成時觸發"
    }
  ]
}
```
