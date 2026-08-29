# API 與介面規格書 (API & Interface Specification)

> 功能名稱：knowledge-db 快取隔離零 Fallback 固化與搜尋輸出 URI 連結格式重構  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `SpaceManager._get_storage_root` | `source/knowledge-db/knowledge_db/space.py` | Internal | 快取根目錄定位，實施零 Fallback 守門防護。 |
| `KnowledgeEngine.to_file_uri` | `source/knowledge-db/knowledge_db/engine.py` | Public | 將任意檔案路徑轉譯為標準 `file:///` 協議與 `#L{line}` 錨點。 |
| `KnowledgeEngine.format_file_link` | `source/knowledge-db/knowledge_db/engine.py` | Public | 將檔案路徑與行號區間轉譯為 IDE 相容之 Markdown 超連結標籤。 |
| `scripts/cli.py:main` | `source/knowledge-db/scripts/cli.py` | Public | CLI 檢索輸出呈現，注入 Markdown 連結與 JSON `file_uri`。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. SpaceManager._get_storage_root (space.py)
def _get_storage_root(self) -> Path:
    """
    取得資料庫本機快取根目錄 (cache://knowledge-db/)。
    
    :return: 快取根目錄 Path 物件
    :raises InvalidSpaceConfigError: 當無法透過 core.uri 解析 cache:// 且未顯式指定 storage_dir 時拋出
    """

# 2. KnowledgeEngine.to_file_uri (engine.py)
def to_file_uri(self, file_path: Union[str, Path], line: Optional[int] = None) -> str:
    """
    將指定路徑轉換為標準 RFC 8089 file:/// 協議 URI。
    
    :param file_path: 檔案路徑 (相對或絕對)
    :param line: 行號 (可選)
    :return: 標準 file:/// 格式字串 (例: file:///H:/path/file.py#L10)
    """

# 3. KnowledgeEngine.format_file_link (engine.py)
def format_file_link(
    self,
    file_path: Union[str, Path],
    line: Optional[int] = None,
    end_line: Optional[int] = None
) -> str:
    """
    格式化為 Markdown 檔案超連結標籤: [rel_path:Lxx~Lyy](file:///abs_path#Lxx)
    
    :param file_path: 檔案路徑
    :param line: 起始行號 (可選)
    :param end_line: 結束行號 (可選)
    :return: Markdown 格式字串 (例: [src/engine.py:L10-20](file:///.../engine.py#L10))
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Storage Layer]
  └── source/knowledge-db/knowledge_db/space.py (_get_storage_root 零 Fallback 固化)
        │
        ▼
[Step 2: Service Layer]
  └── source/knowledge-db/knowledge_db/engine.py (to_file_uri & format_file_link 實作)
        │
        ▼
[Step 3: Presentation Layer]
  └── source/knowledge-db/scripts/cli.py (search 輸出格式重構)
        │
        ▼
[Step 4: Verification Suite]
  ├── source/knowledge-db/tests/test_space.py
  ├── source/knowledge-db/tests/test_engine.py
  └── source/knowledge-db/tests/test_cli.py
```
