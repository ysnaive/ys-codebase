# API 與介面規格書 (API & Interface Specification)

> 功能名稱：模組資料管理相關 URI 協議釐清與遷移 (Module Data Management URI Protocol Alignment & Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `resolve()` | `source/core/core/uri.py` | Public | 解析語意 URI，支援方案 B 全量 Root 化與 `@/` 當前模組自省展開。 |
| `module_scope()` | `source/core/core/uri.py` | Public | 上下文管理器，安全綁定並還原 `_active_module_context`。 |
| `UndefinedModuleContextError` | `source/core/core/uri.py` | Public | 當調用 `@/` 語法但當前缺乏 active module context 時拋出之結構化異常。 |
| `cmd_remove()` | `source/core/core/installer.py` | Public | 擴充支援 `purge: bool = False` 參數，落實標準卸載與深度清除。 |
| `act_delete()` | `source/core/core/engine.py` | Internal | 擴充支援 `purge: bool = False`，根據參數執行標準快取清理或持久化資料銷毀。 |
| `_clean_module_cache()` | `source/core/core/engine.py` | Internal | 物理清空指定模組之 `cache://{mod}/` 目錄。 |
| `MANIFEST_STORAGE_URI` | `source/agents-workflow/agents_workflow/publisher.py` | Internal | 修正為 `storage://@/release_manifest.json`。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 核心 URI 解算器與異常類別 (`source/core/core/uri.py`)

```python
class UndefinedModuleContextError(ValueError):
    """當 URI 中包含 '@/' 自省語法但缺乏當前模組上下文時拋出。"""
    def __init__(self, uri_str: str, message: Optional[str] = None):
        self.uri_str = uri_str
        default_msg = (
            f"Cannot resolve active module placeholder '@' in URI '{uri_str}'. "
            "No active module context is set. Please use 'with uri.module_scope(name):' "
            "or pass explicit module name like '{scheme}://{module}/path'."
        )
        super().__init__(message or default_msg)


def resolve(
    uri: str, 
    current_module: Optional[str] = None, 
    context: Optional[ExecutionContext] = None,
    interactive: bool = True
) -> str:
    """
    解析語意 URI 為實體絕對路徑（方案 B 定式標準）。

    :param uri: 語意 URI 字串 (例: "storage://@/data.json", "storage://core/data.json", "module://core")
    :param current_module: 顯式指定當前模組名稱 (覆蓋全域上下文)
    :param context: 執行期上下文物件
    :param interactive: 檢測到 !undefined 時是否允許 JIT 互動補齊
    :return: 正規化之本機作業系統絕對路徑
    :raises UndefinedModuleContextError: 當路徑包含 '@' 但無可用模組上下文時
    :raises SecurityError: 當檢測到路徑穿越企圖逃逸根空間時
    """
```

---

### 2.2 微內核生命週期與卸載清除介面 (`source/core/core/installer.py` & `engine.py`)

```python
class CoreInstaller:
    def cmd_remove(
        self, 
        module_name: str, 
        clean: bool = False, 
        purge: bool = False, 
        force: bool = False
    ) -> int:
        """
        卸載指定模組並根據參數執行資料生命週期治理。

        :param module_name: 目標模組名稱
        :param clean: 是否清理本地鏡像庫 (.mirror/<module>/)
        :param purge: 是否執行深度清除 (強制刪除 storage/ 與 config/)
        :param force: 是否忽略依賴檢查強制移除
        :return: 0 代表成功，非 0 代表失敗
        """


class CoreEngine:
    def act_delete(self, module_name: str, purge: bool = False) -> None:
        """
        刪除模組資產與資料。
        標準模式 (purge=False)：僅刪除 mirror/ 並自動清空 .cache/<module>/。
        深度清除模式 (purge=True)：額外物理刪除 storage/<module>/ 與 config/<module>/。
        """
        
    def _clean_module_cache(self, module_name: str) -> None:
        """物理刪除並重建 yscb://.cache/{module_name}/ 目錄。"""
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

為保證實作期間零循環相依與零未定義中斷，嚴格遵循以下 6 階段拓撲順序推進：

```text
[拓撲階段 1: 基礎協議層]
  └─ 1.1 source/core/core/uri.py (定義 UndefinedModuleContextError, 升級 _BOOTSTRAP_FALLBACK_SCHEMES 8大協議, 重構 resolve() @/ 展開)
  └─ 1.2 source/core/manifest.json (contributes uri_schemes 移除 8 個 *.root 與 temp)
  └─ 1.3 source/core/tests/test_uri.py (驗證方案 B, @/ 語法與無上下文異常)

[拓撲階段 2: 微內核狀態與生命週期層]
  └─ 2.1 source/core/core/engine.py (互斥鎖遷移至 cache://.yscb.lock, 消除 hardcoded storage/cache, 落實 act_delete purge 邏輯)
  └─ 2.2 source/core/core/installer.py (cmd_remove 支援 --purge)
  └─ 2.3 source/core/scripts/cli.py (CLI 說明與參數解析支援 --purge)
  └─ 2.4 source/core/tests/test_installer.py (追加 --purge 測試)

[拓撲階段 3: 開發工具鏈與沙盒測試層]
  └─ 3.1 source/dev/manifest.json (移除 module.source.root 等 3 個 *.root)
  └─ 3.2 source/dev/dev/testing/sandbox.py & case.py (沙盒遷移至 cache://sandbox/)
  └─ 3.3 source/dev/dev/ (builder.py, releaser.py, checker.py, runner.py, scaffold.py, contract.py 移除 *.root)
  └─ 3.4 source/dev/tests/ (更新所有測試案例斷言至新 URI)

[拓撲階段 4: 工作流資產與應用層]
  └─ 4.1 source/agents-workflow/agents_workflow/publisher.py (修復 release_manifest 路徑至 storage://@/ 並清理舊目錄)
  └─ 4.2 source/agents-workflow/agents_workflow/compiler.py (快取消除硬編碼走 cache://@/resolved_contents/)
  └─ 4.3 source/agents-workflow/manifest.json & assets/ (移除 module.root:// 改為 module://)
  └─ 4.4 source/agents-workflow/tests/ (更新斷言)

[拓撲階段 5: 全代碼庫殘留掃描與清理]
  └─ 5.1 物理清理舊目錄：刪除歷史誤建的 yscb://storage/core/agents-workflow/
  └─ 5.2 物理清理 yscb://.temp/，確認所有暫存進入 yscb://.cache/

[拓撲階段 6: 整合驗證與全量回歸]
  └─ 6.1 執行全專案全模組回歸測試套件 (python yscb.py dev test --all)
```
