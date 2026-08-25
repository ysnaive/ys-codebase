# Phase 3: API 與介面規格說明書 (API Spec) - workflow 佔位符格式修改

> 計畫名稱：`sub_03_workflow_placeholder_format_migration`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據架構設計：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 當前狀態：`Confirmed` (Phase 3 API 設計確認完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 佔位符語法 Schema 規範 (Placeholder Schemas)

### 1.1 插入佔位符 (Token Anchor Schema)
- **語法結構**：`__@{TOKEN_IDENTIFIER}__`
- **正則定義**：`r"__@\{\s*([A-Za-z0-9_]+)\s*\}__"`
- **合法字元**：英文大小寫字母、數字、底線 (`[A-Za-z0-9_]+`)，大括號兩側允許微量空格。
- **示例**：
  - `__@{PHASEXX_STANDARD_HEADER}__`
  - `__@{PROJECT_SPECIFIC_STANDARDS}__`
  - `__@{DYNAMIC_CONTEXT_MAP}__`
  - `__@{ MY_CUSTOM_TOKEN }__` (空白容錯)

### 1.2 路徑佔位符 (URI Reference Schema)
- **語法結構**：`__#{URI_OR_PATH}__`
- **正則定義**：`r"__#\{\s*([^}]+)\s*\}__"`
- **合法字元**：非大括號之所有有效字元 (`[^}]+`)。
- **編譯行為**：100% 保持原樣保留於 Markdown 文檔中，不進行內容展開替換。
- **示例**：
  - `__#{module.root://agents-workflow/assets/standards/DocumentationStandards.md}__`
  - `__#{standards/DevelopmentStandards.md}__`

---

## 2. 編譯器內部 API 簽名 (Compiler Internal APIs)

### 2.1 正則工廠函式
```python
def make_token_tag_regex(token_name: str) -> re.Pattern:
    """
    構造匹配指定 Token 標籤之正則表達式，支援大括號內部微量空格。
    
    :param token_name: Token 識別名稱 (例: "PHASEXX_STANDARD_HEADER")
    :return: 編譯後之 re.Pattern 物件
    """
    return re.compile(r"__@\{\s*" + re.escape(token_name) + r"\s*\}__")


def make_purge_regex(token_name: str) -> re.Pattern:
    """
    構造用於抹除殘留 Token 錨點行之正則表達式，自動吞噬行首縮排與行尾換行。
    
    :param token_name: Token 識別名稱
    :return: 編譯後之 re.Pattern 物件
    """
    return re.compile(r"([ \t]*__@\{\s*" + re.escape(token_name) + r"\s*\}__[ \t]*\r?\n?)")
```

### 2.2 `ArtifactCompiler.resolve_single_artifact`
```python
def resolve_single_artifact(
    self,
    content: str,
    inserts: List[Dict[str, Any]],
    mod_order: Optional[List[str]] = None,
    max_passes: int = 10
) -> str:
    """
    單一 Export 檔案之多輪遞迴解算狀態機。
    
    :param content: 原始未展開 Markdown 文本 (含 __@{token}__ 與 __#{uri}__)
    :param inserts: 全系統已收集之 insert 宣告清單
    :param mod_order: 模組依賴拓撲順序 (可選)
    :param max_passes: 最大遞迴輪數 (預設 10)
    :return: 展開與清洗完畢之純淨 Markdown 文本 (路徑佔位符 __#{uri}__ 保持原樣)
    """
```

---

## 3. 錯誤與邊界處理規格 (Error Handling Specifications)

| 異常/邊界情境 | 觸發條件 | 處理策略與預期返回值 |
| :--- | :--- | :--- |
| **自指同名 Token 注入** | 注入內容含同名 `__@{token}__` 標籤 | 該輪僅替換當前快照中既有之錨點，新注入之同名標籤在 Step 3 作為殘留行抹除，絕不陷入無窮遞迴。 |
| **無匹配 Token 錨點** | 文本中存在未被任何 donor 宣告的 `__@{UNKNOWN}__` | Step 3 自動調用 `make_purge_regex` 乾淨抹除該標籤行，編譯流程正常完成。 |
| **多輪嵌套展開達上限** | Token 相互嵌套超過 `max_passes` 輪 | 達到 10 輪後強制 break，自動清除文本中剩餘所有 `__@{...}__` 標籤並返回當前文字。 |
| **路徑佔位符不變性** | 文本包含任意 `__#{uri}__` 標籤 | 正則狀態機完全忽略此標籤，物化產物中 100% 原樣保留。 |

---

## 4. 當前階段確認狀態

- **當前狀態**：`Draft` (Phase 3 API 設計草擬完成)  
- **推進關卡**：請開發者審查本 API 規格說明書，若確認無誤，請明確指示「**確認無誤，推進至 Phase 4**」！
