# API 與介面規格書 (API & Interface Specification)

> 功能名稱：優化 knowledge-db 輸出搜尋結果時的格式  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/`  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `scripts/cli.py::main` | `source/knowledge-db/scripts/cli.py` | Public | CLI 路由進入點，解析參數並分流輸出 |
| `scripts/cli.py::_format_simple` | `source/knowledge-db/scripts/cli.py` | Internal | 格式化簡易單行搜尋結果清冊 |
| `scripts/cli.py::_format_detailed` | `source/knowledge-db/scripts/cli.py` | Internal | 格式化詳細多行卡片式搜尋結果清冊 |
| `scripts/cli.py::_format_json` | `source/knowledge-db/scripts/cli.py` | Internal | 格式化標準 JSON 搜尋結果結構 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
def _format_simple(query_str: str, results: List[SearchResult]) -> None:
    """簡易單行格式輸出
    
    格式規範:
    [knowledge-db] 檢索查詢: '{query_str}' (共找到 {len(results)} 筆結果):
    #01 <file_path>:<line_number>
    #02 <file_path>:<line_number>
    """
    ...

def _format_detailed(query_str: str, results: List[SearchResult]) -> None:
    """詳細多行卡片式格式輸出
    
    格式規範:
    [knowledge-db] 檢索查詢: '{query_str}' (共找到 {len(results)} 筆結果):
    =====================================================================================
    #01 [51.79] DOC_HEADING_2: 2. 2x2 組態矩陣邊界規範 (markdown)
         檔案: _project/STANDARDS.md:31
         簽名: ## 2. 2x2 組態矩陣邊界規範
         說明: 全系統設定檔嚴格依據...
         命中詞: configuration, 組態, 設定
    -------------------------------------------------------------------------------------
    """
    ...

def _format_json(query_str: str, results: List[SearchResult]) -> None:
    """JSON 結構化輸出
    
    格式規範:
    {
      "query": str,
      "total": int,
      "results": [
        {
          "rank": int,
          "score": float,
          "space": str,
          "symbol": {
            "name": str,
            "kind": str,
            "language": str,
            "file_path": str,
            "line_number": int,
            "signature": str,
            "docstring": str
          },
          "snippet": str,
          "matched_terms": List[str]
        }
      ]
    }
    """
    ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: CLI Formatters]
  └─ scripts/cli.py (定義 _format_simple, _format_detailed, _format_json 與更新 main 參數解析)
       │
       ▼
[Step 2: CLI Unit Tests]
  └─ tests/test_cli.py (編寫 Simple, Detail, JSON 各模式斷言測試案例)
```
