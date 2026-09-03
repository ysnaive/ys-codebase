# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Plan Filter Bug Fix 與 SessionAnalysis 工作流重構  
> 建立日期：2026-09-03  
> 所屬主計畫：無 (獨立計畫)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PlanVerifier.verify_all_plans` | `source/agents-workflow/agents_workflow/plans/verifier.py` | Public | 全量檢核合法時間戳計畫，忽略非時間戳資源目錄 |
| `PlanScanner.scan_active_plans` | `source/agents-workflow/agents_workflow/plans/scanner.py` | Public | 掃描活躍時間戳計畫，輸出狀態矩陣 |
| `PlanSearcher.find_all_plans` | `source/agents-workflow/agents_workflow/plans/searcher.py` | Public | 收集所有時間戳計畫目錄供關鍵字與 DR 檢索 |
| `SessionAnalysis.md` | `source/agents-workflow/assets/workflows/SessionAnalysis.md` | Workflow Asset | 階段歷程自檢與四大維度行為/Token 分析工作流 |
| `contributes/agents-workflow.json` | 各模組 `contributes/agents-workflow.json` | Declarative | 導出 `SessionAnalysis` 工作流與宣告 `WORKFLOW_SESSIONANALYSIS` / `SESSION_ANALYSIS_CHECK_ITEMS` 錨點 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
import re
from pathlib import Path
from typing import Dict, List, Optional
from agents_workflow.plans.models import PlanReport

PLAN_DIR_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}")

# 1. PlanVerifier 全量檢驗過濾簽名
class PlanVerifier:
    def verify_all_plans(self, include_archived: bool = False) -> Dict[str, PlanReport]:
        """
        全量檢核所有活躍（及歷史）計畫。
        
        過濾規則：
        - self.plans_dir 下僅檢核 item.is_dir() 且 PLAN_DIR_PATTERN.match(item.name) 為 True 之目錄。
        - 其餘如 'roadmap'、'archived' 或非時間戳資源目錄嚴格略過。
        """

# 2. PlanScanner 活躍計畫掃描簽名
class PlanScanner:
    def scan_active_plans(self) -> List[Dict]:
        """
        掃描 workflow.plans:// 下的所有活躍進行中計畫。
        
        過濾規則：
        - 僅收錄 d.is_dir() 且 not d.name.startswith(".") 且 PLAN_DIR_PATTERN.match(d.name) 為 True 之目錄。
        """

# 3. PlanSearcher 計畫目錄收集簽名
class PlanSearcher:
    def find_all_plans(self, year: Optional[str] = None, month: Optional[str] = None) -> List[Path]:
        """
        收集進行中與歷史歸檔目錄下的所有計畫資料夾。
        
        過濾規則：
        - 進行中計畫：無論是否傳入 year/month，目錄名稱均必須滿足 PLAN_DIR_PATTERN。
        """
```

### 2.2 SessionAnalysis 工作流契約定義

```markdown
# 流程與四大維度分析標定輸出 (Standard Output Contract)

# 🔍 對話階段歷程分析報告 (Session Analysis Report)

### 📌 流程與紀律自檢 (Guardrails Audit)
- [✅ 全部核心紀律合規 | ⚠️ 發現 X 項不合規項目]
- 不合規項目與文檔根因溯源（若有）...

### 📊 四大維度行為與 Token 消耗分析 (Dimension Breakdown)
- **總 Token 消耗預估**：約 [N] Tokens
- **維度分析與佔比**：
  - **Skills**：佔比 [A]%，觸發 [S1, S2]，時機判定：[正確 / 偏差說明]
  - **Workflows**：佔比 [B]%，觸發 [/W1, /W2]，執行判定：[正確 / 偏差說明]
  - **CLI (包含命令與 I/O 讀寫)**：佔比 [C]%，調用 [X] 次
  - **Other (思考推理/一般問答)**：佔比 [D]%

### 🧩 模組特化評測 (Modular Evaluations)
- [knowledge-db: 工具使用率、合理性與效益對比]

### 💡 工作流優化建議 (Optimization Insights)
1. [具體優化建議]
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: core 移除注入]
  └─ source/core/contributes/agents-workflow.json (移除 RETRO_CHECK_ITEMS)
  └─ 刪除 source/core/assets/retro_check.md
         │
         ▼
[Step 2: knowledge-db 注入對齊]
  └─ source/knowledge-db/contributes/agents-workflow.json (轉為 SESSION_ANALYSIS_CHECK_ITEMS)
  └─ 新建 source/knowledge-db/assets/session_analysis_check.md
  └─ 刪除 source/knowledge-db/assets/retro_check.md
         │
         ▼
[Step 3: agents-workflow Plans 工具鏈收斂]
  └─ verifier.py (verify_all_plans 收斂正則)
  └─ scanner.py (scan_active_plans 收斂正則)
  └─ searcher.py (find_all_plans 收斂正則)
         │
         ▼
[Step 4: agents-workflow 資產與 Token 更名]
  └─ 新建 source/agents-workflow/assets/workflows/SessionAnalysis.md
  └─ 刪除 source/agents-workflow/assets/workflows/Retro.md
  └─ 更新 source/agents-workflow/contributes/agents-workflow.json (導出與 Token 清冊)
         │
         ▼
[Step 5: 單元測試撰寫與回歸]
  └─ test_plans_toolchain.py (追加非時間戳目錄略過測試)
  └─ test_session_analysis_workflow.py (新建專屬測試套件)
         │
         ▼
[Step 6: 編譯發布與全模組驗證]
```
