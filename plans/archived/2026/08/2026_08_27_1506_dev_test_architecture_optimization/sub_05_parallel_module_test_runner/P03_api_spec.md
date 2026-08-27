# API 與介面規格說明書 (API Specification)

> 功能名稱：多進程多模組並行跑測 (Multi-Process Multi-Module Parallel Test Runner)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.3  

---

## 1. CLI 介面擴充規格 (CLI Interface)

### 1.1 `dev test` 指令參數擴充
```bash
# 預設模式（多模組自動啟用並行執行，最大 Worker 數為 CPU 核心數與模組數之較小值）
python yscb.py dev test --all

# 指定並行 Worker 數量 (-j / --jobs)
python yscb.py dev test --all -j 2
python yscb.py dev test --all --jobs=4

# 停用並行，強制順序阻塞執行 (--sequential / --no-parallel)
python yscb.py dev test --all --sequential
python yscb.py dev test --all --no-parallel
```

---

## 2. 內部方法與類別介面規格 (Internal APIs)

### 2.1 `dev.tester.Tester` 介面擴充

```python
class Tester:
    def _run_parallel_test(
        self,
        argv: List[str],
        modules: List[str],
        max_workers: Optional[int] = None
    ) -> int:
        """
        多模組多進程並行測試調度器。
        
        Args:
            argv: 原始命令列參數清單。
            modules: 待測模組名稱清單（如 ['agents-workflow', 'core', 'dev']）。
            max_workers: 最大 Worker 線程數（預設 min(os.cpu_count(), len(modules))）。
            
        Returns:
            int: 0 表示全部通過，1 表示有模組測試失敗。
        """
        ...

    def _run_single_module_worker(
        self,
        mod_name: str,
        worker_idx: int,
        op_test_args: List[str],
        keep_sandbox: bool = False,
        is_nested: bool = False
    ) -> Dict[str, Any]:
        """
        單模組 Worker 執行邏輯（由 ThreadPoolExecutor 派發）。
        
        執行步驟：
        1. 建立獨立虛擬沙盒 (SandboxProvisioner.create_sandbox())。
        2. 終端輸出: [dev:test] Create sandbox <worker_idx> at: "<dir>"。
        3. 設定環境變數 YSCB_SANDBOX_ID="sandbox <worker_idx>" 與 YSCB_SANDBOX_INDEX=<worker_idx>。
        4. 調用 subprocess 執行: sandbox_yscb dev op-test <mod_name> <op_test_args> --report-json=<json_path>。
        5. 讀取解析 <json_path> 取得 ModuleTestMetrics 與失敗列表。
        6. 若通過且 not keep_sandbox: 銷毀沙盒並輸出 [dev:test] Cleaned up sandbox <worker_idx>。
           若失敗: 保留沙盒並輸出 [dev:test] Test failed. Sandbox preserved at: ...。
        7. 回傳包含模組結果、耗時與日誌之字典物件。
        """
        ...
```

### 2.2 報告數據 IPC 協議 (`ReportDataPayload`)

```json
{
  "module": "core",
  "passed": true,
  "duration": 9.20,
  "contract_total": 3,
  "contract_passed": 3,
  "custom_total": 67,
  "custom_passed": 67,
  "logic_passed": 52,
  "env_passed": 15,
  "workflow_passed": 0,
  "perf_passed": 0,
  "errors": [],
  "failures_list": []
}
```
