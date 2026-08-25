# 技術調研報告：完全對標微型虛擬環境沙盒與真實指令流 (Virtual Environment Sandbox & Command Flow)

> 功能名稱：測試框架生命週期與全隔離虛擬沙盒重構  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.0  

---

## 1. 核心願景：完全對標的微型虛擬世界 (The Conforming Virtual World)

為徹底破除「鏡像巢狀遞迴」與「父子環境混血污染」的根本悖論，測試沙盒的定位必須從原先的「單一暫存工作資料夾 (CWD Folder)」，升級為**「100% 對標真實世界（工具庫宿主 + 被管理專案）的完全隔離微型虛擬環境 (Virtual Environment Sandbox)」**。

```text
┌────────────────────────────────────────────────────────────────────────┐
│              完全對標微型虛擬沙盒 (temp://sandbox_<uuid>/)             │
│                                                                        │
│  ┌───────────────────────────────┐  ┌────────────────────────────────┐  │
│  │ 1. 虛擬專案空間 (project://)   │  │ 2. 虛擬宿主空間 (host_dir)    │  │
│  │    [mock_downstream_project/] │  │    [host_env/]                 │  │
│  ├───────────────────────────────┤  ├────────────────────────────────┤  │
│  │ • 模擬真實下游專案代碼庫       │  │ • yscb.py (宿主進入點)         │  │
│  │ • 專案源碼 src/               │  │ • yscb.config.json             │  │
│  │ • project:// 100% 關在此處    │  │   (宣告 yscb_root = "./engine") │  │
│  │                               │  │                                │  │
│  │                               │  │ 3. 工具庫空間 (yscb://)        │  │
│  │                               │  │    [engine/]                   │  │
│  │                               │  │ • config/core/                 │  │
│  │                               │  │   config.project.json          │  │
│  │                               │  │ • modules/ (安裝運行產物)      │  │
│  │                               │  │ • .cache/ (中介層快照)         │  │
│  │                               │  │ • .mirror/ (下載套件鏡像)      │  │
│  │                               │  │ • .snapshots/ (備份快照)       │  │
│  └───────────────────────────────┘  └────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 4. 虛擬 Provider 套件庫 (mock_provider/)                         │  │
│  │ • 提供測試用的 Mock 套件 (mod_a, mod_b, 1.0.0, index.json)        │  │
│  │ • 支援雙層源：本地讀取父層 build/，外部依賴共享父層 .mirror/ 快取│  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 三大真實使用情境與端到端指令流模擬

### 情境 1：全新下游專案初次接入與自舉指令流 (Downstream Consumer Bootstrap Flow)
* **情境定位**：模擬使用者在一個全新的外部專案中，首次引入 `yscb` 並安裝核心套件。
* **沙盒預設狀態**：`mock_downstream_project/` 為乾淨專案目錄，`host_env/` 尚未初始化。
* **端到端指令調用流**：
  1. `run_cli(["init", "--provider=file:///sandbox/mock_provider"])`
     - 於 `sandbox/host_env/` 生成 `yscb.config.json`。
     - 廣播調用 `scripts/hook.dev.py : on_test_setup`，`core` 自動配置 `config/core/config.project.json` 指向 `"../mock_downstream_project"`。
  2. `run_cli(["core", "install", "mock_app"])`
     - 拓撲解析並下載至 `sandbox/host_env/engine/.mirror/`。
     - 安裝至 `sandbox/host_env/engine/modules/mock_app/`。
     - 快照存於 `sandbox/host_env/engine/.snapshots/`。
  3. `run_cli(["core", "remove", "mock_lib"])`
     - 反向依賴檢查，阻斷被依賴模組之移除（帶 `--force` 允許）。

### 情境 2：專案空間 (`project://`) 跨層級操作與設定檔隔離流 (Project URI Isolation Flow)
* **情境定位**：模擬模組存取被管理專案的設定檔與代碼。
* **沙盒預設狀態**：
  - `host_env/engine/config/core/config.project.json` 配置 `"project_root": "../mock_downstream_project"`。
* **端到端指令調用流**：
  - 調用 `uri.resolve("project://src/main.py")`。
  - 精準解析為 `sandbox/mock_downstream_project/src/main.py`。
  - 100% 絕不碰觸父層真實專案。

### 情境 3：源碼即時測試與快速單元驗證流 (Source-Direct In-Place Test Flow)
* **情境定位**：開發者在修改 `source/core/` 或 `source/dev/` 時進行毫秒級 TDD 測試。
* **端到端指令調用流**：
  - `TestDiscovery` 直接將 `source/<mod>` 前置注入 `sys.path[0]`。
  - 零 build 依賴直接載入執行。
  - 沙盒僅作為臨時安全 IO 工作區。

---

## 3. 技術落地改造架構

### 改造 1：`core.uri` 支援 `YSCB_ROOT` 動態重定向
```python
# source/core/core/uri.py
def _get_yscb_root() -> str:
    env_root = os.environ.get("YSCB_ROOT")
    if env_root and os.path.isdir(env_root):
        return os.path.abspath(env_root)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

### 改造 2：`core` 提供測試前置自治 Hook (`scripts/hook.dev.py`)
```python
# source/core/scripts/hook.dev.py
from typing import Any

def on_test_setup(context: Any) -> None:
    context.set_module_config("core", "config.project.json", {
        "project_root": "../mock_downstream_project"
    })

def on_test_teardown(context: Any) -> None:
    pass
```

### 改造 3：`YSCBTestCase` 提供微型虛擬環境生命週期流水線
- `setUp()`：建立 `mock_downstream_project/`, `host_env/`, `mock_provider/`。
- 注入 `YSCB_ROOT` 與 `YSCB_HOST_DIR`。
- 調度執行 `hook.dev.py : on_test_setup`。
- `tearDown()`：測試通過秒級 `rmtree`，失敗保留現場。

### 改造 4：CLI 參數過濾健全化
- `TestDiscovery` 對接 `--type` 參數與 `@require(Requirement.<TYPE>)` 標籤過濾。
- 實作遞迴 `filter_suite(suite, pattern)` 健全 `-k` 巢狀測試篩選。
