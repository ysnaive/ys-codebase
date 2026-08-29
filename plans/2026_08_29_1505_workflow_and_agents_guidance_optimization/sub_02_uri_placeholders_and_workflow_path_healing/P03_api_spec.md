# API 與介面規格書 (API & Interface Specification)

> 功能名稱：`sub_02_uri_placeholders_and_workflow_path_healing`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ArtifactCompiler.resolve_stage2_uri` | `source/agents-workflow/agents_workflow/compiler.py` | Public | 執行 Stage 2 佔位符二分法解算（Standalone 剝除反引號，Inline 保留反引號） |
| `LOCAL_URI_EXACT_REGEX` | `source/agents-workflow/agents_workflow/compiler.py` | Internal | 精確匹配純 `__#{uri}__` 標籤（前後可帶微量空格） |
| `PROJECT_URI_EXACT_REGEX` | `source/agents-workflow/agents_workflow/compiler.py` | Internal | 精確匹配純 `__${uri}__` 標籤（前後可帶微量空格） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# Regular Expressions for Exact Match
LOCAL_URI_EXACT_REGEX = re.compile(r"^__#\{\s*([^}]+)\s*\}__$")
PROJECT_URI_EXACT_REGEX = re.compile(r"^__\$\{\s*([^}]+)\s*\}__$")

def resolve_stage2_uri(
    self,
    content: str,
    current_dst_path: str,
    deployment_map: Dict[str, str]
) -> str:
    """
    Stage 2: 依三層重映射階層動態轉譯 `__#{uri}__` (自身相對路徑) 與 `__${uri}__` (專案根目錄相對路徑)。
    
    規格契約：
    1. 若 code span (`...`) 內部 inner.strip() 精確匹配 LOCAL_URI_EXACT_REGEX 或 PROJECT_URI_EXACT_REGEX：
       - 解算 URI 後直接返回解析字串 (純字串，剝除外層反引號)。
    2. 若 code span 內部 inner 為複合字串 (穿插佔位符)：
       - 替換內部所有 __#{}__ 與 __${}__，並返回 f"`{inner}`" (保留外層反引號)。
    3. 若 code span 不含任何 Stage 2 佔位符：
       - 原樣返回 span_text。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. [Base Engine] compiler.py
   └── 實作 EXACT Regex 與 _replace_in_code_span 二分法邏輯
2. [Assets Source] source/agents-workflow/assets/ & source/dev/assets/
   └── 批次校正工作流與標準資產中之佔位符協議 (__${...}__) 與前綴拼寫
3. [Test Suite] tests/test_compiler.py
   └── 補齊 Standalone 與 Inline 解析之單元測試用例
4. [Build & Sync] 構建、全生態系跑測與消費空間部署同步
```
