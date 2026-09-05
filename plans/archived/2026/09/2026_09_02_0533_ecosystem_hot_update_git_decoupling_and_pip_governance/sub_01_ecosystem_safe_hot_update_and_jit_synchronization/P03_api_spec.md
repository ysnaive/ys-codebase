# API 與介面規格書 (API & Interface Specification)

> 功能名稱：ecosystem_safe_hot_update_and_jit_synchronization  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `core.contributes._is_contributes_dirty` | `source/core/core/contributes.py` | Internal | 比對輸入 contribute 檔案與 `contributes.meta.json` 之 mtime/size |
| `core.contributes.get` | `source/core/core/contributes.py` | Public | 前置 Freshness Gate 嗅探，必要時觸發自愈聚合後返回 Contributes 資料 |
| `core.update_checker.UpdateChecker` | `source/core/core/update_checker.py` | Public | 12 小時節流遠端版本探測、快取維護與溫和提示格式化 |
| `agents_workflow.scripts.cli._ensure_jit_release` | `source/agents-workflow/agents_workflow/scripts/cli.py` | Internal | CLI 前置指紋檢查，若資產變更則自動原子物化至 Target 目錄 |
| `dev.tester.Tester.run` | `source/dev/dev/tester.py` | Public | 支援 `--sync` 旗標，測試通過時鏈式直裝並提供直裝引導提示 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. core.contributes JIT 嗅探與自愈 API
def _get_contributes_meta_uri() -> str:
    """返回 contributes 快照元資料存儲 URI (cache://core/contributes.meta.json)。"""
    ...

def _scan_contributes_inputs() -> Dict[str, Tuple[float, int]]:
    """
    掃描所有 contributes 輸入檔案（yscb.config.json, module://*/contributes/*.json,
    module://*/contributes.json, config://*/contribute.json）。
    返回 {abs_path: (mtime, size)} 映射。
    """
    ...

def _is_contributes_dirty(current_inputs: Dict[str, Tuple[float, int]]) -> bool:
    """
    比對 current_inputs 與快取之 contributes.meta.json。
    若快照不存在、格式錯誤或任一檔案之 (mtime, size) 變更，返回 True。
    比對耗時嚴格要求 <= 2ms。
    """
    ...

def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    增強版 Contributes 查詢 SDK：
    1. 執行 _is_contributes_dirty() 嗅探。
    2. 若 dirty 或 cache://{target_module}/contributes.merged.json 遺失，
       調用 ContributesAggregator().scan_and_inject() 原地自愈，並原子覆寫 contributes.meta.json。
    3. 返回請求的鍵值或全量字典。
    """
    ...


# 2. core.update_checker 來源更新探測器
class UpdateChecker:
    """
    安裝來源 12 小時週期版本探測與升級提示管理器。
    """
    def __init__(
        self,
        cache_uri: str = "cache://core/update_check.json",
        throttle_seconds: int = 43200,  # 12 小時
        timeout_seconds: float = 2.0
    ): ...

    def check_updates(self, force: bool = False) -> Dict[str, Any]:
        """
        執行版本新鮮度檢查：
        若距上次探測未達 throttle_seconds 且非 force，直接返回快取。
        若超過 12 小時，對各 installed_modules 比對 Provider 端 index.json 之最新 SemVer 版本。
        所有網路層異常安全捕獲，不拋出任何中斷例外。
        """
        ...

    def get_tips(self) -> List[str]:
        """讀取快取中偵測到的新版本更新，返回格式化之非阻塞 Tip 訊息清單。"""
        ...


# 3. agents-workflow JIT 投影同步 API
def _ensure_jit_release(force: bool = False) -> bool:
    """
    在 agents-workflow 執行任何 CLI 指令前調用：
    利用 ReleasePublisher.compute_source_fingerprint() 檢查來源指紋是否與 Manifest 一致。
    若不一致，安靜調用 ReleasePublisher.release_all() 完成 JIT 原子同步。
    返回 True 表示觸發了熱物化，False 表示快取完好 (Clean)。
    """
    ...


# 4. dev Dogfooding 閉環加固
class Tester:
    def run(self, args: List[str]) -> int:
        """
        擴充支援 --sync 參數：
        若跑測全部 100% Passed 且目標模組包含本機已安裝模組：
          - 若包含 --sync：自動執行本機直裝邏輯 (install <mod>@build)
          - 若無 --sync：輸出提示 '💡 提示: 測試通過！可執行 python yscb.py install <mod>@build 直裝最新產物。'
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: core.contributes JIT]
       │
       ▼
[Step 2: core.update_checker]
       │
       ▼
[Step 3: agents-workflow JIT release]
       │
       ▼
[Step 4: dev tester --sync]
```
