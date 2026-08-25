# Phase 7: 成果展示與結案報告 (Walkthrough) - core contribute 系統優化與路徑系統打磨

> 計畫名稱：`sub_02_core_contribute_optimization_and_uri_polish`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據任務：[P05_task.md](./P05_task.md)  
> 測試驗證：[P06_test_plan.md](./P06_test_plan.md)  
> 狀態：`Completed` (全功能實作與 1:1 知識庫交付完畢)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述 (Overview)

本子計畫針對 YS-Codebase 核心基礎設施之 **Contribute 聚合機制** 與 **語意 URI 系統** 進行了深度打磨與工業級防呆升級：
1. **Contribute 來源自動標記 (`__provider__`)**：在微內核搜集階段遞迴為 Dict 與 List[Dict] 項目自動注入 `"__provider__": donor_name`，保證下游模組可無痛自省貢獻來源。
2. **依賴拓撲聚合排序 (Topological Ingestion Order)**：依模組安裝之拓撲排序有序合併，保證底層基礎設施優先註冊，上層擴充模組隨後覆蓋。
3. **微內核標準 Contribute 查詢 SDK**：提供 `core.contributes.get(target_module, key=None, default=None)` 與 `get_for_current_module()`，內建自愈快取。
4. **JIT `!undefined` URI 熱更新補齊機制**：在 `uri.resolve()` 探測到 `!undefined` 或未配置路徑時，於 TTY 終端主動彈出 `[-y <path> / -n / --help]` 互動選單，以 `yscb://` 為相對基準展開，支援連鎖未定義依賴遞迴解算與自引用死鎖防護，自動原子寫回所屬模組之 `config.project.json` 並刷新快取無縫繼續運行。
5. **語意協議高度對稱化與自省清冊**：
   - 徹底清除歷史殘留別名 `build://`。
   - 將鏡像空間與發布空間納入 `module` 分支（`module.mirror.root://` / `module.mirror://`、`module.release.root://` / `module.release://`），與 `module.source` / `module.build` / `module` 達成 6 大空間高度對稱。
   - 新增 `python yscb.py uri list` / `--list`、`resolve`、`to-uri`、`check` CLI 自省命令，清晰展示原始定義值與展開後實體路徑。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/core/core/contributes.py` | `MODIFY` | 實作 `_tag_provider()`、拓撲排序聚合、`get()` 與 `get_for_current_module()` SDK |
| `source/core/core/uri.py` | `MODIFY` | 定義 `UndefinedURIError` / `CyclicURIDependencyError`，實作 `reconcile_undefined_uri()`、`list_registered_schemes_summary()`，對齊 `module.mirror` / `module.release` 協議 |
| `source/core/core/engine.py` | `MODIFY` | 更新 `act_download`、`act_delete`、`act_prepare`、`act_reload` 協議路徑至 `module.mirror.root` 與 `module.release.root`，修正簽名 |
| `source/core/scripts/cli.py` | `MODIFY` | 新增 `uri` 子命令路由器（`list` / `--list`、`resolve`、`to-uri`、`check`） |
| `source/core/manifest.json` | `MODIFY` | 註冊 `module.mirror.root` 與 `module.mirror` 協議 |
| `source/dev/manifest.json` | `MODIFY` | 註冊 `module.release.root` 與 `module.release` 協議，移除 `build` 別名 |
| `source/dev/dev/builder.py` | `MODIFY` | 更新發布打包輸出路徑至 `module.release.root://` |
| `source/dev/dev/releaser.py` | `MODIFY` | 更新發布檢核與 Rollback 路徑至 `module.release.root://` |
| `source/core/tests/test_contributes.py` | `MODIFY` | 新增 FT-01~05 測試（`__provider__` 標記、顯式保護、拓撲排序、SDK） |
| `source/core/tests/test_uri.py` | `MODIFY` | 新增 FT-06~08、ET-01~03 測試（JIT 熱補齊、`--help` 摘要、循環依賴阻斷、`UndefinedURIError`） |
| `source/core/tests/test_remote_zip_bootstrap.py` | `MODIFY` | 更新測試路徑至 `module.mirror.root://` |
| `source/dev/tests/test_builder.py` | `MODIFY` | 更新測試路徑至 `module.release.root://` |
| `source/dev/tests/test_release_pipeline.py` | `MODIFY` | 更新測試路徑至 `module.release.root://` |
| `yscb.py` | `MODIFY` | 在 `CORE_COMMANDS` 註冊 `uri` 指令以支援一級 CLI 調度 |

---

## 3. 關鍵程式碼展示 (Key Implementations)

### 3.1 Contributes `__provider__` 注入與標準 SDK (`core/contributes.py`)
```python
def _tag_provider(data: Any, donor_name: str) -> Any:
    if isinstance(data, dict):
        result = {k: _tag_provider(v, donor_name) if isinstance(v, (dict, list)) else v for k, v in data.items()}
        if "__provider__" not in result:
            result["__provider__"] = donor_name
        return result
    elif isinstance(data, list):
        return [_tag_provider(item, donor_name) for item in data]
    return data

def get(target_module: str, key: Optional[str] = None, default: Any = None) -> Any:
    cache_file = f"cache.root://{target_module}/contributes.merged.json"
    data = uri.read_json(cache_file) if uri.exists(cache_file) else None
    if data is None or not isinstance(data, dict):
        all_merged = ContributesAggregator().scan_and_inject()
        data = all_merged.get(target_module, {})
    return data.get(key, default) if key is not None else (data or default)
```

### 3.2 JIT `!undefined` 熱更新補齊與自引用防護 (`core/uri.py`)
```python
def reconcile_undefined_uri(
    scheme_token: str,
    raw_target: str,
    provider: Optional[str] = None,
    config_binding: Optional[str] = None,
    description: Optional[str] = None,
    interactive: bool = True
) -> str:
    global _reconciling_tokens
    if scheme_token in _reconciling_tokens:
        raise CyclicURIDependencyError(f"Cyclic or self-referencing URI dependency detected for '{scheme_token}://'")
    
    is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
    if not interactive or not is_tty:
        raise UndefinedURIError(scheme=scheme_token, provider=provider or "core", binding=config_binding or "unknown")

    # 提示選單、-y <path> 解析寫回設定檔、--help 清冊自省展示...
```

---

## 4. 驗證結果 (Verification Results)

- **微內核單元測試**：`python yscb.py dev test core` -> **56/56 Passed (100%)**
- **全系統回歸測試**：`python yscb.py dev test --all` -> **97/97 Passed (100%)**
- **CLI 自省驗證**：
  ```text
  $ python yscb.py uri list
  YS-Codebase Registered URI Schemes Catalog:
  ==============================================================================================================
  SCHEME                  TYPE     PROVIDER     RAW TARGET / VALUE           RESOLVED PATH
  --------------------------------------------------------------------------------------------------------------
  yscb://                 const    core         {yscb_root}                  H:\UseFolder\CodeRepo\ys_codebase\ys_codebase
  module.mirror.root://   const    core         yscb://.mirror/              H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\.mirror
  module.mirror://        const    core         yscb://.mirror/{module}/     H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\.mirror\core
  temp://                 const    core         yscb://.temp/                H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\.temp
  snapshot://             const    core         yscb://.snapshots/           H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\.snapshots
  module.root://          const    core         yscb://modules/              H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\modules
  module://               const    core         yscb://modules/{module}/     H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\modules\core
  config.root://          const    core         yscb://config/               H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\config
  config://               const    core         yscb://config/{module}/      H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\config\core
  cache.root://           const    core         yscb://.cache/               H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\.cache
  cache://                const    core         yscb://.cache/{module}/      H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\.cache\core
  storage.root://         const    core         yscb://storage/              H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\storage
  storage://              const    core         yscb://storage/{module}/     H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\storage\core
  module.source.root://   const    dev          yscb://source/               H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\source
  module.source://        const    dev          yscb://source/{module}/      H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\source\core
  module.build.root://    const    dev          yscb://build/                H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\build
  module.build://         const    dev          yscb://build/{module}/       H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\build\core
  module.release.root://  const    dev          yscb://release/              H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\release
  module.release://       const    dev          yscb://release/{module}/     H:\UseFolder\CodeRepo\ys_codebase\ys_codebase\release\core
  project://              config   core         project_root                 H:\UseFolder\CodeRepo\ys_codebase
  ==============================================================================================================
  ```

---

## 5. 提交建議 (Conventional Commit Recommendations)

```bash
git add source/core/ source/dev/ yscb.py plans/ docs/ CHANGELOG.md
git commit -m "feat(core): optimize contributes injection and polish URI protocol system

- Auto-inject __provider__ in contributes scan and aggregate with topological order
- Provide standard core.contributes.get and get_for_current_module query SDK
- Implement JIT !undefined URI prompt reconciliation with cascading auto-recovery
- Unify module URI schemes (module.mirror, module.release) and remove legacy build alias
- Introduce yscb uri list/resolve/to-uri/check introspection CLI commands"
```
