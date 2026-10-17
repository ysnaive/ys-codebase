# API 與介面規格書 (API & Interface Specification)

> 功能名稱：純淨安裝環境下游反饋 4 項缺陷修復與設定引導校準  
> 建立日期：2026-10-15  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `DEFAULT_PROVIDER_URL` | `yscb.py` | Public Const | 定義官方預設模組 Provider 下載路徑（指向 `.../main/ys_codebase/release`） |
| `DEFAULT_SELF_UPDATE_URL` | `yscb.py` | Public Const | 定義官方唯一宿主腳本更新來源（指向 `.../main/yscb.py`） |
| `_resolve_self_update_target_url` | `yscb.py` | Internal Function | 解析自更新目標 URL，優先使用 `--url`，否則使用 `DEFAULT_SELF_UPDATE_URL` |
| `release_target` | `ys_codebase/source/agents-workflow/scripts/cli.py` | Public CLI Handler | 支援 `--add` / `--remove` / `--list` 與 `add` / `remove` / `list` 雙向 CLI 派發 |
| `ReleasePublisher._soft_unmerge_agents_text` | `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Internal Method | 剝離文字中 YSCB 管理區塊與預設空殼章節，回傳 (是否包含自訂內容, 剩餘乾淨文字) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `yscb.py` 自更新與 Provider 常數與解算函式

```python
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release"
DEFAULT_SELF_UPDATE_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py"

def _resolve_self_update_target_url(custom_url: Optional[str] = None) -> str:
    """
    解算 self-update 目標 URL。
    優先使用 custom_url (--url 指定之值)，否則直接使用 DEFAULT_SELF_UPDATE_URL。
    完全廢除從 provider 字串切割 /release 的脆弱推導。
    """
```

### 2.2 `agents-workflow` CLI Handler: `release_target`

```python
def release_target(cmd_bags: Any) -> int:
    """
    管理 release-target 清單與狀態。
    解析順序：
    1. 檢查 cmd_bags.has_option("add") 或 bags.args[0] in ("add", "--add")
       -> target_name = bags.get_option_value("add") or (bags.args[1] if len(bags.args) > 1 else None)
    2. 檢查 cmd_bags.has_option("remove") 或 bags.args[0] in ("remove", "--remove", "--rm")
       -> target_name = bags.get_option_value("remove") or (bags.args[1] if len(bags.args) > 1 else None)
    3. 否則（包含明確 --list / list 或完全無參數）進入 list_targets 渲染清單。
    """
```

### 2.3 `ReleasePublisher` 軟剝離安全方法

```python
def _soft_unmerge_agents_text(self, existing_text: str) -> Tuple[bool, str]:
    """
    安全剝離文字中 YSCB 管理區塊：
    1. 透過 re.sub 移除 <!-- YSCB_AGENTS_BEGIN --> ... <!-- YSCB_AGENTS_END --> 區塊。
    2. 檢查剩餘文字是否僅包含 YSCB 預設自動生成的空殼章節：
       ## 4. 專案特化工程規範 (Project Specific Standards)
       *(專案特化工程規範填寫於此，不受中央標準庫覆蓋)*
    3. 若剩餘文字扣除預設空殼後仍有非空白內容：
       回傳 (True, 剝離後的乾淨文字) -> 表示需保留檔案。
    4. 若剩餘文字全為空或僅有預設空殼：
       回傳 (False, "") -> 表示可安全物理刪除。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. yscb.py 常數重構與 self-update 解耦
   └── 驗證 yscb.py init 與 self-update 語意獨立性
2. contributes/core.json 補齊 release-target 參數契約
   └── agents-workflow/scripts/cli.py release_target 雙向解析改寫
3. agents-workflow/publisher.py 軟剝離防禦實作
   └── release_all 步驟 1 陳舊檔案清理串接 _soft_unmerge_agents_text
4. 知識庫與 Onboarding 引導文檔修正
   ├── README.md & source/knowledge-db/README.md
   ├── source/knowledge-db/manifest.json (onboarding)
   └── docs/knowledge-db/contributes_guide.md
5. 單元測試落地 (test_cli_router.py, test_cli.py, test_release_publisher.py)
```

