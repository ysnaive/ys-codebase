# API 與介面規格書 (API & Interface Specification)

> 功能名稱：optional_manifest_and_daemon_cleanup  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ModuleInstaller._check_optional_dependencies` | `source/core/core/installer.py` | Protected | 讀取已安裝模組之 `optional` 字典，檢查未安裝項並印出友善提示 |
| `Checker._check_manifest` | `source/dev/dev/checker.py` | Protected | 擴充驗證 `optional` 欄位型態與鍵值格式 |
| `manifest.json` (Schema) | `source/knowledge-db/manifest.json` | Public/Config | 宣告 `dependencies` (硬相依) 與 `optional` (擴充相依) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `core.installer.ModuleInstaller._check_optional_dependencies`

```python
def _check_optional_dependencies(self, manifest_data: Dict[str, Any]) -> None:
    """
    走訪 manifest 中宣告的 optional 模組清單。
    若工作區尚未安裝該模組，於終端輸出結構化建議卡片與安裝指令引導。

    :param manifest_data: 目標模組之 manifest.json 反序列化字典
    """
```

### 2.2 `dev.checker.Checker._check_manifest`

```python
def _check_manifest(self, manifest_path: str, m_data: Dict[str, Any]) -> List[CheckViolation]:
    """
    靜態合規性檢核：
    1. 既有必填欄位 (name, version, entry, dependencies) 檢查。
    2. 若包含 optional 欄位：
       - 驗證型態為 dict。
       - 驗證每項鍵值均為 dict，且包含 'version' (str) 與 'hint' (str)。
       - 若不符規則生成 CheckViolation (Level: CRITICAL)。
    """
```

### 2.3 `manifest.json` 結構規範

```json
{
  "name": "knowledge-db",
  "version": "1.1.0",
  "dependencies": {
    "core": ">=1.0.2"
  },
  "optional": {
    "server": {
      "version": ">=1.0.0",
      "hint": "提供常駐背景檔案監聽熱自癒與極速預熱派發"
    }
  }
}
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. [Core]   core.installer._check_optional_dependencies 實作與單元測試
      │
      ▼
2. [Dev]    dev.checker._check_manifest 支援 optional 檢核與單元測試
      │
      ▼
3. [Domain] knowledge-db 刪除 daemon.py、hook.core.py、清理 cli.py 引用
      │
      ▼
4. [Manifest] knowledge-db/manifest.json 轉移 server 至 optional
      │
      ▼
5. [Regression] 全模組 dev test 與 dev check 100% 通過
```
