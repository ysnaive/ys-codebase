# API 與介面規格書 (API & Interface Specification)

> 功能名稱：dev_test_output_purification_and_info_aggregation  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `Tester._run_test` | `source/dev/dev/tester.py` | Internal | 宿主端測試調度器，負責沙盒構建、JSON IPC 子進程調用、終端輸出屏蔽與雙模式報告組裝。 |
| `Tester._run_op_test` | `source/dev/dev/tester.py` | Internal | 沙盒內部原地測試執行器，負責宿主直接執行守門阻斷、測試探索、執行並導出 JSON 報告。 |
| `ASCIIReportFormatter.format_summary` | `source/dev/dev/testing/runner.py` | Public | 格式化一般模式 ASCII 診斷報告，支援子進程警告計數折疊與底部乾淨安裝提示。 |
| `TestRunner.run_suite` | `source/dev/dev/testing/runner.py` | Public | 執行單元測試套件，徹底移除偽造 `YSCB_TEST_SANDBOX` 標識之行為。 |
| `YSCBTestCase.setUp` | `source/dev/dev/testing/case.py` | Public | 測試前置設定，剛性校驗沙盒環境合法性，若路徑不符拋出 `SecurityError`，絕不回退 `cwd`。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. Tester._run_test (source/dev/dev/tester.py)
def _run_test(self, argv: List[str]) -> int:
    """
    高階宿主測試調度門面：
    1. 執行事前 Dev Build (除非 --no-build)。
    2. Provision 虛擬沙盒環境 SandboxProvisioner.create_sandbox()。
    3. 調用沙盒內部 op-test，強制附加 '--report-json=<path>' 與 '--quiet-report'。
    4. 透過 subprocess.run(..., capture_output=True) 屏蔽沙盒全部 stdout/stderr。
    5. 讀取 JSON 報告：
       - quiet_mode 且成功：嚴格僅輸出單行 'Pass: X(100.0%), Fail: 0, Skip: 0' (零 stderr/stdout 洩漏)。
       - quiet_mode 且失敗：輸出統計首行與 FAILED LIST (若子進程崩潰無報告，附加 stderr 尾部 20 行)。
       - normal mode：輸出結構化摘要、警告折疊與完整診斷報表。
       - verbose mode：完整展開原始沙盒 stdout/stderr。
    6. 依據策略安全銷毀或保留沙盒。
    """

# 2. Tester._run_op_test (source/dev/dev/tester.py)
def _run_op_test(self, argv: List[str]) -> int:
    """
    沙盒內部原地測試執行器：
    - 守門守則：檢驗當前是否處於真實沙盒環境中（YSCB_TEST_SANDBOX="1" 且當前或上層目錄含 'host_env' 與 'engine'）。
      若於宿主直接執行，輸出警示並回傳 returncode=1 阻斷，嚴禁在宿主落地執行測試！
    - 執行測試探索並調用 TestRunner。
    - 若指定 '--report-json'，將結構化數據持久化至檔案；若指定 '--quiet-report'，抑制所有終端直接 print。
    """

# 3. YSCBTestCase.setUp (source/dev/dev/testing/case.py)
def setUp(self) -> None:
    """
    前置環境設置與沙盒路徑剛性檢驗：
    - 檢驗 os.environ.get("YSCB_TEST_SANDBOX") == "1"。
    - 向上探測沙盒目錄：當前目錄或父目錄必須包含 'host_env' 且根目錄名稱必須為 'sandbox_' 開頭或合法沙盒結構。
    - 🚨 剛性守門：若探測失敗，強制拋出 SecurityError，嚴禁回退為 os.getcwd()！
    """

# 4. TestRunner.run_suite (source/dev/dev/testing/runner.py)
def run_suite(self, suite: unittest.TestSuite) -> Tuple[unittest.TestResult, str]:
    """
    套件執行器：
    - 🚨 拔除主動設置 os.environ["YSCB_TEST_SANDBOX"] = "1" 的偽造邏輯，該變數僅允許由真正之沙盒初始化進程帶入。
    - 調用 TextTestRunner 並透過 OutputCapturer 捕獲測試方法主動輸出。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Layer 1: 防穿透剛性守門]
  ├── source/dev/dev/testing/runner.py: 拔除 TestRunner.run_suite 偽造環境變數
  └── source/dev/dev/testing/case.py: YSCBTestCase.setUp 移除 cwd 回退，加入 SecurityError 阻斷
            │
            ▼
[Layer 2: 原地執行器守門與純淨輸出]
  └── source/dev/dev/tester.py (_run_op_test): 增加宿主直接調用阻斷，保證 --quiet-report 不洩漏
            │
            ▼
[Layer 3: 宿主調度器 JSON IPC 統一與輸出屏蔽]
  ├── source/dev/dev/tester.py (_run_test): 統一使用 report-json，屏蔽子進程 stdout/stderr
  └── source/dev/dev/testing/runner.py (ASCIIReportFormatter): 雙模式信息聚合與警告折疊
            │
            ▼
[Layer 4: 測試套件驗證]
  └── source/dev/tests/test_output_purification.py: 全面驗證 FT-01~04, ET-01~02
```
