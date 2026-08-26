# Dev 模組擴充貢獻格式說明書 (Dev Contributes Specification)

> 模組名稱：`dev`  
> 模組版本：`1.0.0`  
> 職責定位：YS-Codebase 官方開發者工具箱（模組腳手架、靜態檢查、純淨打包、單元測試引擎）。

---

## 1. 宣告式擴充點 (Contribution Points)

`dev` 模組透過 `contributes.core` 命名空間向微內核 `core` 自宣告注入以下開發者專屬空間協議：

```json
{
  "contributes": {
    "core": {
      "uri_schemes": [
        {
          "token": "module.source.root",
          "type": "const",
          "value": "yscb://source/",
          "description": "模組源碼空間根目錄"
        },
        {
          "token": "module.source",
          "type": "const",
          "value": "yscb://source/{module}/",
          "description": "模組專屬源碼目錄"
        },
        {
          "token": "module.build.root",
          "type": "const",
          "value": "yscb://build/",
          "description": "純淨安裝產物根目錄"
        },
        {
          "token": "module.build",
          "type": "const",
          "value": "yscb://build/{module}/",
          "description": "純淨安裝產物專屬目錄"
        }
      ]
    }
  }
}
```

---

## 2. 擴充說明

- **`module.source://`**：供開發者編輯源碼、建立單元測試。
- **`module.build://`**：供建置工具輸出版本化純淨產物包（`module.build://{version}/`），自動排除開發期雜項。
