# 介面與測試契約規格書 (API & Test Specifications)

> 功能名稱：全主計畫二次驗收、測試集子系統 1:1 純化、歷史目錄清理與三層文檔收官 (sub_08_final_acceptance_and_suite_purification)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

---

## 1. 介面契約清單 (Interface Inventory)

本子計畫核心為測試集純化與工作區收官，無新增/變更之 Public API 介面；本節定義純化後 6 大子系統測試類別之繼承與契約介面：

| 測試模組檔案 | 測試案例類別 (TestCase Classes) | 對應被測子系統 | 關鍵測試職責 |
| :--- | :--- | :--- | :--- |
| `tests/test_compiler.py` | `TestArtifactCompiler`<br>`TestWorkflowAssetsCompliance` | `agents_workflow.compiler` | Stage 1 錨點、Stage 2 URI 展開、Fenced Code 保護、內建 17 Skills / 16 Templates 合規檢查 |
| `tests/test_publisher.py` | `TestReleasePublisher`<br>`TestPublisherManifestPlacement`<br>`TestPublisherCrossPlatform` | `agents_workflow.publisher` | 發布物化、JIT 雜湊變更比對、目錄遞迴清理、LF 換行符正規化、`cache://` 清單本地隔離 |
| `tests/test_initializer.py` | `TestWorkflowInitializer` | `agents_workflow.initializer` | 專案工作流初始化、組態產生與路徑解析 |
| `tests/test_targets.py` | `TestReleaseTargets`<br>`TestCliTargets` | `agents_workflow.targets` | 多平台投影設定解析、CLI 目標列表與驗證 |
| `tests/test_roadmap.py` | `TestRoadmapManager`<br>`TestTodoManager` | `agents_workflow.roadmap` | 路線圖掃描/篩選/實體搬移 (`roadmap promote`)、待辦帳本盲寫/篩選/打包立項 (`todo add/promote`) |
| `tests/test_plans_toolchain.py` | `TestPlanStatus`<br>`TestPlanVerifier`<br>`TestPlanScanner`<br>`TestPlanArchiver` | `agents_workflow.plans.*` | ACI 狀態機領航 (`--resume`)、雙檔 left-shift 檢核、`P01<->P06` 追溯差集、`_auto.md` 雙軌相容 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

> **[Signature-Only 契約] 僅列測試類別契約與防護簽名，嚴禁預貼實作碼**：

### 2.1 子系統測試隔離契約
```python
class YSCBSubsystemTestCase(YSCBTestCase):
    """6 大子系統測試之共用基底契約。"""
    temp_dir: Optional[str]

    def setUp(self) -> None:
        """建立隔離測試沙盒或 tempfile.mkdtemp。"""
        ...

    def tearDown(self) -> None:
        """強制包覆 try...finally 徹底清理 temp_dir 與工作區變更。"""
        ...
```

### 2.2 核心決策紀錄
- **[P03:DR-01] 消除寬容放行與歷史墓碑契約**：
  - 核心斷言全面替換為 `self.assertTrue(uri.exists(...))`、`self.assertEqual(...)`，嚴禁使用 `if uri.exists:` 條件包覆。
  - 徹底移除已除役符號之 `assertFalse(hasattr(...))` 與 `assertNotIn(...)` 墓碑。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```
[Phase A: 工作區清理] ──> git rm -r scratch/ scripts/
                             │
                             ▼
[Phase B: 主幹擴充] ────> 擴充 test_publisher.py (吸收 3 支發布碎片)
                             │
                             ├─> 擴充 test_plans_toolchain.py (吸收 3 支 Plans 碎片)
                             ├─> 擴充 test_roadmap.py (吸收 todo 測試並補齊 tearDown)
                             └─> 擴充 test_compiler.py (吸收資產檢核並刪除墓碑)
                             │
                             ▼
[Phase C: 碎片刪除] ────> 物理刪除 7 支碎片/殭屍測試檔 (git rm)
                             │
                             ▼
[Phase D: 文檔對齊] ────> 更新 FACTORY_PIPELINE.md & README.md
                             │
                             ▼
[Phase E: 回歸驗收] ────> dev check & dev test 雙全綠守門
```

