# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Core Contributes 系統檔案結構升級 (Core Contributes File Structure Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_01)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `core.contributes.ContributesAggregator` | `source/core/core/contributes.py` | Public | 掃描已安裝模組與專案組態，執行拓撲聚合並寫入快取 |
| `core.contributes.get` | `source/core/core/contributes.py` | Public | 查詢指定目標模組之已合併 Contributes 字典或特定鍵值（具 Auto-Healing） |
| `core.contributes.get_for_current_module` | `source/core/core/contributes.py` | Public | 依當前活躍模組上下文快速查詢 Contributes 資料 |
| `core.contributes._tag_provider` | `source/core/core/contributes.py` | Internal | 遞迴為宣告字典/清單注入 `__provider__ = donor` 標記 |
| `core.providers.get_agents_cli_guild` | `source/core/core/providers.py` | Public | 動態產生 `AGENTS_CLI_GUILD` Markdown 表格（改由 SDK 驅動） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
from typing import Dict, Any, List, Optional

def _tag_provider(data: Any, donor_name: str) -> Any:
    """
    遞迴為 contributes 宣告中的 Dict 與 List[Dict] 項目注入 __provider__ 標記。
    若物件已顯式宣告 __provider__ 則予以保留不覆蓋。
    
    :param data: 待標記之任意結構資料 (dict, list, or primitive)
    :param donor_name: 貢獻者模組名稱
    :return: 遞迴注入 __provider__ 後之資料副本
    """
    pass


def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    標準 Contributes 查詢 SDK：
    查詢指定目標模組之已合併 Contributes 字典或特定鍵值。
    
    1. 優先從 cache://{target_module}/contributes.merged.json 讀取。
    2. 若快取不存在或損毀，自動調用 scan_and_inject() 即時自愈 (Auto-Healing)。
    3. 若指定 key 則返回該特定欄位，否則返回全字典。
    
    :param target_module: 目標模組識別碼 (例如 'core', 'agents-workflow', 'knowledge-db')
    :param key: 可選特定子鍵名 (例如 'commands', 'uri_schemes', 'spaces')
    :param default: 查無資料時之預設值 (預設 None)
    :return: 合併後之貢獻資料
    """
    pass


def get_for_current_module(key: Optional[str] = None, default: Any = None) -> Any:
    """
    從當前活躍模組上下文 (uri.get_module_context()) 獲取 Contributes 字典或特定鍵值。
    """
    pass


class ContributesAggregator:
    """
    Contributes 雙階聚合引擎：
    負責掃描已安裝模組之 contributes/<target>.json 與專案級 config.project.json，
    執行拓撲合併，並物化寫入 cache://{target}/contributes.merged.json。
    """
    def __init__(self):
        pass

    def scan_and_inject(
        self,
        topological_order: Optional[List[str]] = None,
        clean: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        雙階掃描聚合：
        階層 ① (模組層級)：掃描 module://<donor>/contributes/<target>.json，注入 __provider__。
        階層 ② (專案層級)：掃描 config://<target>/config.project.json (及 config.local.json)。
        物化持久化至 cache://<target>/contributes.merged.json。
        
        :param topological_order: 可選之模組有序拓撲清單
        :param clean: 是否清理舊快取
        :return: 所有目標模組之全量聚合字典 { target_name: { ... } }
        """
        pass

    def _deep_merge(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        """
        遞迴深度合併字典與清單（清單執行去重追加）。
        """
        pass
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 資產建立] 建立 4 大模組之 source/<module>/contributes/<target>.json
       │
       ▼
[Step 2: Manifest 瘦身] 剝除 4 大模組 source/<module>/manifest.json 內之 "contributes" 區塊
       │
       ▼
[Step 3: Core 聚合引擎] 重構 source/core/core/contributes.py (ContributesAggregator & SDK)
       │
       ▼
[Step 4: Core 消費端] 重構 source/core/core/providers.py 與 source/core/core/engine.py
       │
       ▼
[Step 5: 業務模組消費端] 重構 source/knowledge-db/knowledge_db/space.py 與 source/agents-workflow/agents_workflow/compiler.py
       │
       ▼
[Step 6: 測試與回歸] 更新 source/core/tests/test_contributes.py 並執行 dev test --all
```
