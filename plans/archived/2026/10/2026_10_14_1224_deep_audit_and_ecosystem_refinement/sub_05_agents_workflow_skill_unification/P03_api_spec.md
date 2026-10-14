# API 與介面規格書 (Interface & Protocol Spec)

> 功能名稱：sub_05_agents_workflow_skill_unification  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 介面契約與資料結構 (Interface Contracts & Data Structures)

```json
{
  "_types": {
    "ExportAssetDef": {
      "type": "enum(standard, template, skill)!",
      "name": "str?",
      "source": "str!",
      "description": "str?"
    }
  }
}
```

---

## 2. 核心 API 簽名與詳細規格 (API Signatures)

```python
# 1. 容錯別名與降級轉譯 (compiler.py)
class ArtifactCompiler:
    def _normalize_export_def(self, exp: Dict[str, Any]) -> Dict[str, Any]:
        """
        正規化導出資產宣告：
        若 exp["type"] == "workflow"，動態轉譯為 "skill"，
        以 source 檔名作為預設 skill.name，並於 stderr 輸出相容通知。
        """

# 2. 舊工作流目錄清理 (publisher.py)
class WorkflowPublisher:
    def _cleanup_legacy_workflows(self, target_root: str, target_name: str) -> List[str]:
        """
        於發布交易前/後安全清理歷史遺留之工作流檔案與空目錄 (.agents/workflows)。
        回傳被清理之檔案路徑清單。
        """
```

---

## 3. 依賴拓撲與實作順序 (Dependency Topology)

1. `_format.json` 與 `agents-workflow.json`（純化 Schema 與導出宣告）
2. `compiler.py`（歷史相容轉譯）
3. 遷移 `assets/skills/`（建立 8 大流程 `SKILL.md` 並移除 `assets/workflows/`）
4. `publisher.py`（清理舊 `.agents/workflows/`）
5. 單元測試更新與驗證

}
```

