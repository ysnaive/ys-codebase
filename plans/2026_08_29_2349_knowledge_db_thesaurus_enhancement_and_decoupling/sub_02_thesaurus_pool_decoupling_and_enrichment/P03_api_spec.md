# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_thesaurus_pool_decoupling_and_enrichment  
> 建立日期：2026-08-30  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ThesaurusEngine.__init__` | `knowledge_db/thesaurus.py` | Public | 支援接收 `ThesaurusConfig` 或三個自訂集合，預設無傳參為純淨空容器 |
| `SpaceManager.create_thesaurus_engine` | `knowledge_db/space.py` | Public | 聚合 Contributes 詞庫並裝配 `ThesaurusEngine` 之標準工廠方法 |
| `contributes/knowledge-db.json` | `source/knowledge-db/` | Asset | 宣告六大維度初始高質量詞庫（thesaurus, aliases, related） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `ThesaurusEngine` (`thesaurus.py`)
```python
class ThesaurusEngine:
    """純淨無狀態三階同義詞與關聯詞擴展容器"""

    def __init__(
        self,
        config: Optional[ThesaurusConfig] = None,
        custom_groups: Optional[List[List[str]]] = None,
        custom_aliases: Optional[Dict[str, List[str]]] = None,
        custom_related: Optional[List[List[str]]] = None,
    ):
        """
        初始化純淨詞庫容器。若未傳入任何參數，預設內部字典為空。
        :param config: 結構化 ThesaurusConfig 物件
        :param custom_groups: 額外雙向同義詞清單
        :param custom_aliases: 額外單向別名字典
        :param custom_related: 額外領域關聯詞清單
        """
```

### 2.2 `SpaceManager.create_thesaurus_engine` (`space.py`)
```python
class SpaceManager:
    def create_thesaurus_engine(
        self,
        extra_config: Optional[ThesaurusConfig] = None,
    ) -> ThesaurusEngine:
        """
        工廠方法：自 core.contribute 體系載入並聚合全系統詞庫，
        可選擇性疊加 extra_config，返回裝配完成之 ThesaurusEngine 實例。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌────────────────────────────────────────────────────────┐
│ Step 1: source/knowledge-db/contributes/knowledge-db.json│
│         (宣告 6 大維度初始高質量詞彙庫)               │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Step 2: thesaurus.py (ThesaurusEngine 解耦為純容器)    │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Step 3: space.py (SpaceManager.create_thesaurus_engine)│
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Step 4: tests/test_thesaurus_decoupling.py (Unit Tests)│
└────────────────────────────────────────────────────────┘
```
