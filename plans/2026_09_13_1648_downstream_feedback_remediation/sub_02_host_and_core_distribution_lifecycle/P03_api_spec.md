# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `_resolve_self_update_target_url` | `yscb.py` | Internal | 自 Provider 或自訂參數解析最新 `yscb.py` 腳本下載位址 |
| `cmd_self_update` | `yscb.py` | Host CLI | 執行 Host 入口自身腳本的語法檢驗與原子覆寫備份升級 |
| `_parse_simple_semver` | `yscb.py` | Internal | 零外部相依之輕量 4-tuple 語意版本數值解析 |
| `_discover_latest_core` | `yscb.py` | Internal | 動態探測本地或遠端 Provider 之最高版本 core 壓縮包 |
| `cmd_init` | `yscb.py` | Host CLI | 專案初始化與 `--fix` 自癒修復引擎，連鎖觸發 `core reload` |
| `UpdateChecker.invalidate_cache` | `source/core/core/update_checker.py` | Public SDK | 清除或刷新指定模組之更新提示快取紀錄 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 Host Bootstrapper 擴充規格 (`yscb.py`)

```python
# 官方預設發布庫常數
DEFAULT_PROVIDER_URL: str = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/release"

def _resolve_self_update_target_url(provider: str, custom_url: Optional[str] = None) -> str:
    """
    解算 self-update 目標 URL：
    - 若傳入 custom_url，直接使用。
    - 若 provider 結尾為 /release 或包含 /release/，上層目錄即為 repo 根目錄：
      例：https://raw.githubusercontent.com/ysnaive/ys-codebase/main/release
      -> https://raw.githubusercontent.com/ysnaive/ys-codebase/main/yscb.py
    - 若為本地目錄，優先檢查同層或父層之 yscb.py。
    """
    ...

def cmd_self_update(argv: List[str]) -> int:
    """
    自遠端或本機更新 yscb.py。
    支援參數：--provider=<url>, --url=<direct_url>
    防呆：下載後強制 ast.parse() 語法驗證，備份現有至 yscb.py.bak，原子 replace。
    """
    ...

def _parse_simple_semver(v_str: str) -> Tuple[int, int, int, int, bool]:
    """
    輕量語意版本解析：返回 (major, minor, patch, revision, is_build)。
    """
    ...

def _discover_latest_core(provider: str) -> Tuple[Optional[str], Optional[str]]:
    """
    自 Provider 探測可用最新 core 版本。
    返回 (version_str, package_path_or_url)。
    - 本地目錄：列舉 core/*.zip 與 release/core/*.zip，取最高 semver。
    - 遠端 HTTP：GET <provider>/core/index.json 解析 versions 列表取最高。
    - 若失敗退化為安全候選清單 (如 1.1.0.1, 1.1.0.0)。
    """
    ...

def cmd_init(argv: List[str]) -> int:
    """
    初始化工作區或執行自癒修復。
    支援參數：[yscb_root] (預設 ".yscb"), --fix, --provider=<url>
    - 若設定檔不存在：全新初始化，建立 .yscb/.modules/core 與 yscb.config.json，連鎖 reload。
    - 若設定檔已存在：
        * 若指定 --fix 或檢測到 core 模組損毀/缺失：讀取既有組態，抓取最新 core 重建並更新版本，連鎖 reload。
        * 若無 --fix 且 core 完好：輸出提示已初始化 (使用 --fix 修復) 並返回 1。
    """
    ...
```

### 2.2 Core UpdateChecker 快取失效規格 (`source/core/core/update_checker.py`)

```python
class UpdateChecker:
    ...
    def invalidate_cache(self, module_name: Optional[str] = None) -> None:
        """
        及時失效更新快取：
        - 若 module_name 為 None：全量清空快取中的 updates 並重設 last_checked_at。
        - 若指定 module_name：自 cached["updates"] 中移除該模組並立即回寫磁碟。
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[1. yscb.py 常數與輔助函式]
  ├── DEFAULT_PROVIDER_URL 修正
  ├── _resolve_self_update_target_url
  ├── _parse_simple_semver & _discover_latest_core
  ├── cmd_self_update
  └── cmd_init (--fix 支援、預設 ".yscb" 與連鎖 reload)
       │
       v
[2. core.installer & core.update_checker]
  ├── INTERNAL_IGNORE_PATTERNS 增加 yscb.py.bak
  ├── UpdateChecker.invalidate_cache 實作
  └── Installer.cmd_install / cmd_update 呼叫 invalidate_cache
       │
       v
[3. test_distribution_lifecycle.py]
  └── 全套單元測試 FT-01 ~ FT-08
```
