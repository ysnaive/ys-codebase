# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_existing_injection_mode_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `release_target.agents_md` | `contributes/agents-workflow.json` | Schema | 宣告 Target 專屬規範軟合併目標路徑（例 `"project://AGENTS.md"`） |
| `ReleasePublisher._soft_merge_agents_text` | `agents_workflow/publisher.py` | Internal | 純文字演算法：將新標準文本軟合併至既有文本之 YSCB 標記區塊 |
| `ReleasePublisher._compute_target_fingerprint` | `agents_workflow/publisher.py` | Internal | 計算單一 Target 之 SHA-256 指紋（納入 `agents_md` 配置） |
| `ReleasePublisher.release_all` | `agents_workflow/publisher.py` | Public | 執行發布流水線，依啟用 Targets 之 `agents_md` 進行軟合併與 Manifest 追蹤 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class ReleasePublisher:
    def _soft_merge_agents_text(
        self,
        existing_text: str,
        new_standards: str
    ) -> str:
        """
        純文字軟合併演算法 (Pure String Soft-Merge).
        
        Args:
            existing_text: 既有檔案文字內容（若檔案不存在則傳入空字串 ""）。
            new_standards: 已解算完成之新 AgentsStandards 內容。
            
        Returns:
            str: 軟合併後之完整檔案內容，保證非 YSCB 區塊（使用者自訂規則）100% 不變。
        """

    def _compute_target_fingerprint(
        self,
        target_cfg: Dict[str, Any],
        resolved_items: List[Dict[str, Any]]
    ) -> str:
        """
        計算單一 Release Target 之 SHA-256 綜合指紋。
        
        納入要素：
            - Target 名稱與 Projections 規則
            - Target 宣告之 agents_md 路徑
            - 所有 Stage 1 導出產物內容雜湊
        """

    def release_all(
        self,
        target_name: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        執行多目標 IDE 發布物 4 步原子發布流水線。
        
        行為變更：
            - 徹底移除讀取 config["enable_agents_md"] 邏輯。
            - 遍歷啟用之 active_targets，若 target.agents_md != ""：
                * 執行 Stage 2 URI 解析
                * 執行 _soft_merge_agents_text
                * 將目標檔案路徑登載至該軌之 published_files 集合
            - 透過雙軌 Manifest 機制自動管理 rules 檔案之 Diff 與 Pruning。
        """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. 宣告層更新:                                               │
│    - source/agents-workflow/contributes/agents-workflow.json │
│    - source/agents-workflow/contributes.format.md            │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. 組態與初始化層更新:                                       │
│    - source/agents-workflow/agents_workflow/initializer.py   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 核心發布引擎重構:                                         │
│    - source/agents-workflow/agents_workflow/publisher.py     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. 單元與回歸測試套件:                                       │
│    - source/agents-workflow/tests/test_publisher.py          │
│    - source/agents-workflow/tests/test_targets.py            │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. 文檔手冊更新:                                             │
│    - docs/agents-workflow/user_guide.md                      │
│    - docs/agents-workflow/README.md                          │
└─────────────────────────────────────────────────────────────┘
```
