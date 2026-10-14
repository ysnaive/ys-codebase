# API 與介面規格書 (API & Interface Specification)

> 功能名稱：2026_10_14_1554_downstream_onboarding_and_ux_guidance  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `format_undefined_uri_hint` | `ys_codebase/source/core/core/uri.py` | Public | 根據未定義之 `scheme`、`provider` 與 `binding` 生成可直接執行的 CLI 修復指令提示 |
| `UndefinedURIError` | `ys_codebase/source/core/core/uri.py` | Public | 當語意 URI 為 `!undefined` 時拋出之例外，尾部附帶 `Quick fix` CLI 指令 |
| `Installer._print_onboarding_guide` | `ys_codebase/source/core/core/installer.py` | Internal | 讀取已安裝模組 `manifest.json` 之 `onboarding` 清單並輸出 `[Next Steps]` 引導卡片 |
| `_print_init_next_steps` | `yscb.py` | Internal | 於 `yscb.py init` 全新初始化完成後輸出工作區啟動下一步指引 |
| `Checker._check_manifest` | `ys_codebase/source/dev/dev/checker.py` | Public | 校驗 `manifest.json` 結構，新增選填 `onboarding: List[str]` 格式驗證 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ys_codebase/source/core/core/uri.py
def format_undefined_uri_hint(
    scheme: str,
    provider: Optional[str] = None,
    binding: Optional[str] = None,
) -> str:
    """
    針對未定義 (!undefined) 之語意 URI 協議生成可直接複製執行的 CLI 修復指令提示。

    Args:
        scheme: 協議名稱（不含 '://'，如 'project' 或 'workflow.plans'）。
        provider: 宣告該協議之模組名稱（預設 'core'）。
        binding: 綁定之組態鍵路徑（如 'project_root' 或 'paths.plans'）。

    Returns:
        str: 單行可執行之 CLI 修復建議字串。
    """

# ys_codebase/source/core/core/installer.py
class Installer:
    def _print_onboarding_guide(self, module_name: str) -> None:
        """
        讀取 module://{module_name}/manifest.json 中選填之 'onboarding' 步驟清單，
        於模組安裝完成後輸出結構化 Next Steps 引導卡片。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: core.uri (format_undefined_uri_hint + UndefinedURIError + cli.py:uri_check)
  └──> Step 2: core.installer (_print_onboarding_guide) & yscb.py (_print_init_next_steps)
         └──> Step 3: dev.checker (_check_manifest onboarding validation) & 5 module manifest.json files
                └──> Step 4: Root README.md, docs/README.md, and 5 source/<mod>/README.md files
                       └──> Step 5: Unit tests & dogfooding build/install verification
```

