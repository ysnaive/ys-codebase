# API 規格說明書 (API Specification)

> 功能名稱：框架骨架最終打磨與 CLI UX 體驗優化 (Framework Final Polish & CLI UX)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據架構設計：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 狀態：Confirmed (Phase 3 已確認)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 介面與函式簽名定義 (Interface Specifications)

### 1.1 宿主層 (`yscb.py`) 格式化與輔助介面

```python
def _print_global_help() -> None:
    """
    輸出 YSCB 全域標準化 Help 資訊：
    包含 Banner, USAGE, CORE COMMANDS (含 init), MODULE COMMANDS (動態聚合) 與 GLOBAL OPTIONS。
    """

def _get_installed_module_commands(host_dir: str) -> Dict[str, Dict[str, str]]:
    """
    動態掃描已安裝模組並回傳指令字典：
    回傳格式: { "dev": { "create": "Create a new module skeleton", "build": "...", ... } }
    在尚未安裝任何模組或 yscb_root 未就緒時優雅回傳空字典 {}。
    """

def _suggest_command(unknown_cmd: str, candidate_pool: List[str]) -> Optional[str]:
    """
    使用 difflib 比對相近指令：
    若相似度 >= 0.6，回傳最接近之候選字串；否則回傳 None。
    """
```

### 1.2 Core 微內核層 (`source/core/core/engine.py`) 聚合查詢 API

```python
class AtomicEngine:
    def act_get_installed_commands_summary(self) -> Dict[str, Dict[str, str]]:
        """
        掃描 cache://contributes.merged.json 或 modules/*/manifest.json，
        彙整並回傳各已安裝模組所貢獻之 CLI 指令與說明字典。
        
        Returns:
            Dict[module_name, Dict[subcommand_name, description]]
        """
```

### 1.3 Dev 工具層 (`source/dev/dev/releaser.py`) 發布守門精簡

```python
class Releaser:
    def check_preflight_gates(
        self, 
        module_name: str, 
        target_ver: str, 
        run_tests: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        執行發布前置守門檢查 (Pre-flight Gates)：
        - [移除 Gate 1]: 不再阻斷 Git 工作區 Dirty 狀態。
        - Gate 2: 自動化回歸測試 (run_tests=True 時觸發)。
        - Gate 3: 版本不可變性檢查 (release/<mod>/<ver>.zip 禁止已存在)。
        - Gate 4: Manifest 合規檢查 (驗證 entry point 等必填欄位)。
        
        Returns:
            Tuple[is_passed: bool, failure_reasons: List[str]]
        """
```

---

## 2. 實作依賴拓撲順序 (Dependency Topology)

1. **Step 1（Dev 模組守門精簡）**：修改 `source/dev/dev/releaser.py` 移除 Gate 1 檢查。
2. **Step 2（Core 微內核指令查詢）**：修改 `source/core/core/engine.py` 提供 `act_get_installed_commands_summary`。
3. **Step 3（宿主 Help 與拼寫建議）**：修改 `yscb.py` 實作層次化 `_print_global_help` 與 `_suggest_command`。
4. **Step 4（測試套件）**：建立 `source/core/tests/test_cli_help.py` 與更新 `source/dev/tests/test_releaser.py`。
