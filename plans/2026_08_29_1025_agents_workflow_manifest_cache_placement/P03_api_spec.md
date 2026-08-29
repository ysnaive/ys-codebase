# API 與介面規格書 (API & Interface Specification)

> 功能名稱：agents_workflow_manifest_cache_placement  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ReleasePublisher` | `agents_workflow/publisher.py` | Public | 核心發布引擎：負責 Target 拓撲、雙軌 Manifest 儲存、`project://` 轉換與檔案物化 |
| `ReleaseTargetManager` | `agents_workflow/targets.py` | Public | Target 管理器：提供各層級 (Local/Project) Targets 存取與分類介面 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# agents_workflow/publisher.py

PROJECT_MANIFEST_STORAGE_URI: str = "storage://agents-workflow/release_manifest.json"
LOCAL_MANIFEST_CACHE_URI: str = "cache://agents-workflow/release_manifest.json"

class ReleasePublisher:
    """發布引擎：負責 Target 拓撲映射、Header 巨集插值、雙軌 Diff 檢測與 4 步原子交易。"""

    def _to_project_uri(self, abs_path: str, proj_root: str) -> str:
        """
        將本機實體絕對路徑轉換為 project:// 語意協議路徑。
        - 若路徑位於 proj_root 內，轉為 project://<rel_path> (斜線統一為 /)。
        - 具備防禦機制，若無法計算相對路徑則安全 fallback。
        """
        pass

    def _resolve_project_uri(self, uri_str: str, proj_root: str) -> str:
        """
        將 project:// 協議路徑或歷史絕對路徑轉換為本機實體絕對路徑。
        - 若以 project:// 開頭：解析為 os.path.join(proj_root, rel_path)。
        - 若為歷史絕對路徑 (如 H:\... 或 D:\...)：直接 normpath 回傳，具備相容容錯。
        """
        pass

    def _load_manifest(self, manifest_uri: str) -> Dict[str, Any]:
        """安全讀取指定 URI (storage:// 或 cache://) 之 Manifest 字典。"""
        pass

    def _save_manifest(self, manifest_uri: str, data: Dict[str, Any]) -> bool:
        """安全寫入 Manifest 至指定 URI，格式化縮排 2 格並強制以 LF 換行。"""
        pass

    def compute_source_fingerprint(self, target_names: Optional[List[str]] = None) -> str:
        """
        計算特定 Target 清單或全域來源特徵指紋 (SHA-256 Hex Digest)。
        """
        pass

    def release_all(self, force: bool = False, interactive: bool = False) -> Dict[str, Any]:
        """
        執行 4 步原子發布交易流水線（支援 Project/Local 雙軌獨立 Manifest 與 Diff 優化）。
        """
        pass
```

```python
# agents_workflow/targets.py

class ReleaseTargetManager:
    @classmethod
    def get_classified_targets(cls) -> Dict[str, List[str]]:
        """
        回傳分類 Targets 字典：
        {
            "project": List[str],  # 來自 config.project.json
            "local": List[str],    # 來自 config.local.json (已去重)
            "union": List[str]     # 兩者聯集
        }
        """
        pass
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Root .gitattributes]
   └── 建立 .gitattributes 宣告跨平台純 LF 規範
[Step 2: targets.py]
   └── 擴充 ReleaseTargetManager.get_classified_targets()
[Step 3: publisher.py]
   └── 實作 _to_project_uri / _resolve_project_uri
   └── 實作雙軌 Manifest 獨立指紋、讀取、更新與孤立 Pruning
   └── 落地寫檔全面顯式指定 newline="\n"
[Step 4: storage manifest conversion]
   └── 標準化現存 release_manifest.json 為 project:// 格式
[Step 5: test suite]
   └── 新增 test_manifest_placement.py 驗證雙軌儲存與 LF
```
