# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_skills_architecture  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ArtifactCompiler._scan_directory_files` | `source/agents-workflow/agents_workflow/compiler.py` | Internal | 遞迴掃描目錄下所有資產檔案，回傳相對路徑與內容清單 |
| `ArtifactCompiler.compile_stage1` | `source/agents-workflow/agents_workflow/compiler.py` | Public | Stage 1 Token 展開，支援目錄級 Skill 掃描與子目錄快取 |
| `ReleasePublisher.build_deployment_map` | `source/agents-workflow/agents_workflow/publisher.py` | Public | 支援 `projections.skill`、目錄巨集插值與多檔案相對路徑映射 |
| `ReleasePublisher.release_all` | `source/agents-workflow/agents_workflow/publisher.py` | Public | 4 步原子發布流水線，支援多檔案 Skill 落地、雙軌 Manifest 追蹤與 Pruning |
| `contributes.agents-workflow.json` | `source/agents-workflow/contributes/agents-workflow.json` | Schema | 定義三大 Target 之 `projections.skill` 與對齊 Codex 官方路徑 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `ArtifactCompiler._scan_directory_files`
```python
def _scan_directory_files(self, dir_path_or_uri: str) -> List[Tuple[str, str, str]]:
    """
    遞迴掃描指定目錄路徑（支援語意 URI 或實體路徑）下的所有檔案。
    
    Args:
        dir_path_or_uri (str): 目錄之語意 URI 或實體絕對/相對路徑。
        
    Returns:
        List[Tuple[rel_path, abs_or_uri, content]]:
            - rel_path (str): 檔案在該目錄下的相對路徑（如 "SKILL.md", "references/search.md"），統一以正斜線 '/' 分隔。
            - abs_or_uri (str): 檔案之實體路徑或子 URI。
            - content (str): 檔案文字內容。
    """
```

### 2.2 `ArtifactCompiler.compile_stage1` 擴充行為契約
```python
def compile_stage1(self) -> Dict[str, Any]:
    """
    執行 Stage 1 全量段落佔位符解算：
    - 支援 export.type == "skill"，當 source 為目錄時自動呼叫 _scan_directory_files。
    - 對目錄下所有文字檔案執行 resolve_single_artifact 展開 __@{token}__ 錨點。
    - 快取寫入 cache://agents-workflow/resolved_contents/skills/<skill_name>/<rel_path>。
    - 回傳 resolved_items 清單，每項包含 rel_path, is_skill, skill_name 欄位。
    """
```

### 2.3 `ReleasePublisher.build_deployment_map` 擴充契約
```python
def build_deployment_map(
    self,
    target_cfg: Dict[str, Any],
    resolved_items: List[Dict[str, Any]]
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    為指定 Target 計算檔案部署映射表：
    - 讀取 target_cfg.projections.skill（若無則 fallback 預設路徑）。
    - 解析 target_dir 中的 {export.name} / {export.basename} 巨集。
    - 對於 is_skill 項目，以 target_dir_abs + rel_path 組合為最終目標實體路徑。
    - 註冊別名: deployment_map[source_uri], deployment_map[f"skills/{skill_name}"], deployment_map[skill_name]。
    """
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1] JSON Schema 定義更新 (contributes/agents-workflow.json & contributes.format.md)
   │     - 為 antigravity, claude, codex 加入 projections.skill
   │     - 修正 codex 投影目錄至 project://.agents/
   ▼
[Step 2] 編譯器目錄走訪與 Stage 1 快取 (compiler.py)
   │     - 實作 _scan_directory_files
   │     - compile_stage1 支援 type="skill" 與目錄級掃描快取
   ▼
[Step 3] 發布引擎目錄巨集插值與投影 (publisher.py)
   │     - build_deployment_map 支援 target_dir 巨集插值與 rel_path 階層映射
   │     - release_all 落地寫入與雙軌 Manifest 追蹤
   │     - sync_gitignore 精準忽略個別 Skill 檔案
   ▼
[Step 4] 單元與邊界測試套件更新 (test_compiler.py, test_publisher.py, test_targets.py)
```
