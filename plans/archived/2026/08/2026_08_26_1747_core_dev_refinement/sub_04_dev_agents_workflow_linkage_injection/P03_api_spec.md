# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Dev 與 Agents-Workflow 模組連動注入 (Dev & Agents-Workflow Linkage Injection)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PackageManager.act_download` | `source/core/core/engine.py` | Public | 下載/物化 zip 至鏡像庫；擴充 `@build` 特例優先級。 |
| `PackageManager._get_module_manifest_from_provider_or_local` | `source/core/core/engine.py` | Internal | 依賴拓撲解算期解析 Manifest；擴充 `@build` 特例解析。 |
| `dev/manifest.json` | `source/dev/manifest.json` | Public Schema | 宣告 `contributes["agents-workflow"]` 向 `WORKFLOW_SOP_STANDARDS` 注入規範。 |
| `DevEngineeringStandards.md` | `source/dev/assets/standards/DevEngineeringStandards.md` | Asset | YS-Codebase 模組開發專案特化工程規範本文檔。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `PackageManager.act_download` `@build` 特例解析
```python
def act_download(self, module_name: str, version: str, provider_url: str) -> str:
    """
    下載/物化指定版本之單檔 zip 至 module.mirror://{module_name}/{version}.zip。
    
    特例情境 (@build 特例):
    - 若 version 為 "build" 或以 ".build" 結尾：
      1. 強制直接掃描 module.build://{module_name}/
      2. 優先尋找 *.build.zip 或最新生成之 build zip
      3. 若找到，複製物化至 module.mirror://{module_name}/{version}.zip 並回傳 URI
      4. 若本地 module.build:// 找不到任何檔案，拋出 FileNotFoundError:
         "Build package not found for '{module_name}'. Please run 'python yscb.py dev build {module_name}' first."
    - 若非 @build 特例，維持標準 3-Tier 解析階層 (Tier 1 build -> Tier 2 release -> Tier 3 remote)。
    """
```

### 2.2 `PackageManager._get_module_manifest_from_provider_or_local` `@build` 特例
```python
def _get_module_manifest_from_provider_or_local(
    self, 
    module_name: str, 
    provider_url: str, 
    version_constraint: Optional[str] = None
) -> Dict[str, Any]:
    """
    特例情境 (@build 特例):
    - 若 version_constraint 為 "build" 或以 ".build" 結尾：
      1. 優先讀取 module.build://{module_name}/ 內之 *.build.zip 中的 manifest.json
      2. 若 zip 內讀取成功，回傳其 manifest 資料
      3. 若無 zip，回退嘗試讀取 module.source://{module_name}/manifest.json (將版本修正為 *.build)
    """
```

### 2.3 `source/dev/manifest.json` Contributes 擴充宣告
```json
{
  "name": "dev",
  "version": "1.0.0.0",
  "description": "YS-Codebase Developer Tools (Scaffold, Checker, Builder, Tester, Releaser)",
  "entry": "scripts/cli.py",
  "dependencies": {
    "core": ">=1.0.0"
  },
  "contributes": {
    "core": {
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
      ]
    },
    "agents-workflow": {
      "insert": [
        {
          "type": "uri",
          "token": "WORKFLOW_SOP_STANDARDS",
          "value": "module://dev/assets/standards/DevEngineeringStandards.md",
          "mode": "below"
        }
      ]
    }
  }
}
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 資產建立]
  └── 1.1 建立 source/dev/assets/standards/DevEngineeringStandards.md
        ├── 定義「YS-Codebase 模組開發專案特化工程規範」
        ├── 注入「禁止 Agent 主動 release/install」剛性防呆條款
        └── 納入三層空間 SSOT、虛擬沙盒測試加速、靜態 AST 守門

[Step 2: Contributes 宣告]
  └── 2.1 修改 source/dev/manifest.json
        └── 註冊 contributes["agents-workflow"].insert (WORKFLOW_SOP_STANDARDS, mode: below)

[Step 3: Core 引擎 @build 特例實作]
  └── 3.1 修改 source/core/core/engine.py
        ├── _get_module_manifest_from_provider_or_local 支援 @build 解析
        └── act_download 支援 @build 特例直接自 module.build:// 下載

[Step 4: 單元測試、回歸驗證與發布物化]
  ├── 4.1 新增/擴充 source/core/tests/test_engine.py 測試 install @build
  ├── 4.2 執行 agents-workflow release 驗證規範是否成功注入至 DevelopmentStandards.md
  └── 4.3 執行全系統沙盒回歸測試 dev test --all (114/114 Passed)
```
