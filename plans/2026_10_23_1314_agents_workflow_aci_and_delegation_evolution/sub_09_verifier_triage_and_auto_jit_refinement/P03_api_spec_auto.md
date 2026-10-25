# 介面與測試契約規格書 (API & Test Specifications)

> 功能名稱：PlanVerifier 缺失率分流處方、確定性標頭自癒、階段前瞻提示與 /auto 兩階段 JIT 讀模板瘦身 (sub_09_verifier_triage_and_auto_jit_refinement)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

---

## 1. 介面契約清單 (Interface Inventory)

| 模塊 / 類別 | 方法或屬性名稱 | 變更類型 | 用途說明 |
| :--- | :--- | :---: | :--- |
| `PlanReport` (`verifier.py`) | `header_healed: List[str]`, `next_phase_hint: Optional[str]` | Modify | 記錄自動補齊確定性標頭之檔案清單與 `PASSED` 時之下一階段前瞻提示字串。 |
| `PlanVerifier` (`verifier.py`) | `get_resolved_template_header_specs(template_name: str) -> List[Tuple[str, str]]` | New | 回傳標準模板之 `(normalized_title, raw_markdown_heading)` 序對清單。 |
| `PlanVerifier` (`verifier.py`) | `_auto_heal_deterministic_headers(...) -> List[str]` | New | 對缺失 `功能名稱`/`建立日期`/`所屬主計畫` 之檔案原地補齊確定性標頭並回傳補齊欄位清單。 |
| `PlanVerifier` (`verifier.py`) | `_build_next_phase_hint(target_dir: Path) -> Optional[str]` | New | 於單一計畫檢核 `PASSED` 且未結案時，推導下一階段目標模板路徑與必備原始章節預告。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
@dataclass
class PlanReport:
    plan_name: str
    plan_path: str
    status: PlanSeverity = PlanSeverity.PASS
    issues: List[PlanIssue] = field(default_factory=list)
    companion_created: List[str] = field(default_factory=list)
    header_healed: List[str] = field(default_factory=list)
    log_status: Optional[str] = None
    next_phase_hint: Optional[str] = None
```

```python
class PlanVerifier:
    def get_resolved_template_header_specs(self, template_name: str) -> List[Tuple[str, str]]:
        """解析指定模板之二/三級標題，回傳 [(norm_title, raw_heading_line), ...] 清單。"""
        ...

    def _auto_heal_deterministic_headers(
        self,
        md_file: Path,
        lines: List[str],
        headers: Dict[str, str],
        is_sub_plan: bool,
        target_dir: Path,
    ) -> Tuple[List[str], Dict[str, str], List[str]]:
        """
        若缺少 [功能名稱]、[建立日期] 或二級子計畫之 [所屬主計畫]，自動推導確定性值並寫回檔案。
        後置契約：絕不新增或修改 [狀態] 與 [模型]；回傳更新後之 (lines, headers, healed_keys)。
        """
        ...

    def _build_next_phase_hint(self, target_dir: Path) -> Optional[str]:
        """
        根據 PlanStatusResolver.resolve_next_action(target_dir) 推導下一階段：
        若 status != 'Completed' 且下一階段對應 P01~P07 模板，回傳包含模板路徑 (.agents/.yscb/templates/...) 與原始 ## 標題清單之前瞻提示字串。
        """
        ...
```

- **[P03:DR-01] 缺失率分流閾值與輸出格式契約**：
  - 設模板總章節數為 $N$，缺失章節數為 $M$ ($M > 0$)，缺失率 $R = M / N$：
    - 若 $R < 0.5$ (`QUICK_PATCH`)：訊息格式包含 `[TRIAGE: QUICK_PATCH (章節缺失 M/N)]` 與缺失章節之 `raw_heading_line`，指引以 `edit_file` 原地補齊。
    - 若 $R \ge 0.5$ (`FULL_REWRITE`)：訊息格式包含 `[TRIAGE: FULL_REWRITE (章節缺失 M/N，屬盲寫結構偏離)]`、`.agents/.yscb/templates/{tmpl_name}` 完整路徑與該模板全部 `raw_heading_line`，指引讀取模板並以 `write_file` 重寫。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

1. **Step 1**：更新 `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`（`PlanReport`、`get_resolved_template_header_specs`、`_auto_heal_deterministic_headers`、缺失率分流處方、`_build_next_phase_hint`）。
2. **Step 2**：更新 `ys_codebase/source/agents-workflow/scripts/cli.py`（輸出 `[SELF-HEAL]` 標頭自癒與 `[NEXT PHASE GATE]` 前瞻提示）。
3. **Step 3**：更新 `ys_codebase/source/agents-workflow/assets/skills/auto/SKILL.md`（拔除 §3 內聯骨架表、改為兩階段 JIT 讀模板、量化支柱二委派門檻）。
4. **Step 4**：更新 `test_plans_toolchain.py`、`test_compiler.py` 與雙軌知識庫文檔（`user_guide.md`、`DESIGN_NOTES.md`），執行編譯發布與沙盒測試驗證。

