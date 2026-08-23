# API 規格書 (API Specification)

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Draft  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.2  

---

## 1. 類別與成員總覽

| 類別 / 模組名稱 | 命名空間 / 檔案路徑 | 類型 | 職責概述 |
|:---|:---|:---:|:---|
| `ProjectContext` | `yscb_core.context` (`source/core/yscb_core/context.py`) | Modify | 擴充跨模組貢獻查詢通道 `get_contributions()` |
| `ModuleManager` | `yscb_installer` (`yscb_installer.py`) | Modify | 新增批次完成後單次生命週期廣播 `_broadcast_modules_changed()` |
| `SOPSynthesizer` | `agents_workflow.sop_synthesizer` (`source/agents-workflow/scripts/sop_synthesizer.py`) | Add | SOP Slot 插槽注入、內容拼接與標記安全正則剝除引擎 |
| `IDECacheTracker` | `agents_workflow.ide_sync` (`source/agents-workflow/scripts/ide_sync.py`) | Add | IDE 生成檔案快取追蹤與孤兒檔案自動清理機制 |
| `ExtensionRegistry` | `agents_workflow.ext_registry` (`source/agents-workflow/scripts/ext_registry.py`) | Add | 雙層 Extension 發現鏈（`sop_ext://` 優先於 `modules/<plugin>/`）解析器 |

---

## 2. API 介面定義 (Python Signature & Contracts)

### 2.1 Core SDK: `yscb_core.ProjectContext` 擴充

```python
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class ProjectContext:
    """專案環境與語意上下文管理器"""

    def get_contributions(self, namespace: str) -> List[Tuple[str, Path, Dict[str, Any]]]:
        """
        安全掃描已安裝模組 (modules/) 與源碼模組 (source/) 之 manifest.json，
        提取指定命名空間下宣告之貢獻字典。

        :param namespace: 目標主機命名空間 (例: "agents-workflow")
        :return: 清單，每項為 Tuple(模組名稱, 模組實體目錄路徑, 貢獻 Payload 字典)
        :note: 若模組未宣告 contributes 或格式非 dict，安全略過不拋出例外。
        """
        results: List[Tuple[str, Path, Dict[str, Any]]] = []
        manifests = self.get_all_installed_manifests()
        
        for mod_name, (mod_dir, manifest) in manifests.items():
            contributes = manifest.get("contributes")
            if isinstance(contributes, dict) and namespace in contributes:
                payload = contributes[namespace]
                if isinstance(payload, dict):
                    results.append((mod_name, mod_dir, payload))
        return results
```

---

### 2.2 Installer: `yscb_installer.ModuleManager` 廣播派發

```python
class ModuleManager:
    """模組生命週期與安裝管理器"""

    def _broadcast_modules_changed(self, changes: List[Tuple[str, str]]) -> None:
        """
        於整批安裝/更新/移除事務完成後，單次向所有具備 Hook 之已安裝模組派發廣播。

        :param changes: 本次指令所有異動模組清單，每項為 Tuple(action, module_name)
                        action 可為: "installed" | "updated" | "removed"
        :note: 
          1. 嚴禁在 build() 指令後調用此方法（保持建置產物純淨）。
          2. 子進程調用格式: python <module_dir>/scripts/_on_modules_changed.py <action:module> ...
          3. 若 Hook 拋出非 0 退出碼或例外，僅記錄 [WARN] 日誌，絕不回滾安裝事務。
        """
        if not changes:
            return

        arg_payload = [f"{action}:{mod_name}" for action, mod_name in changes]
        installed_mods = self.get_installed_modules()

        for mod_name, mod_info in installed_mods.items():
            mod_dir = Path(mod_info.get("path", f"modules/{mod_name}"))
            hook_script = mod_dir / "scripts" / "_on_modules_changed.py"
            
            if hook_script.exists():
                try:
                    cmd = [sys.executable, str(hook_script)] + arg_payload
                    subprocess.run(cmd, cwd=self.project_root, check=False, timeout=30)
                except Exception as e:
                    self._log_warn(f"Hook failed for module '{mod_name}': {e}")
```

---

### 2.3 `agents-workflow`: `SOPSynthesizer` 補丁合成引擎

```python
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

class SOPSynthesizer:
    """SOP 模板 Slot 插槽動態注入與標記剝除合成引擎"""

    SLOT_PATTERN = re.compile(r'<!--\s*YSCB_SLOT:([a-zA-Z0-9_]+)\s*-->')

    @classmethod
    def synthesize_sop(
        cls,
        template_content: str,
        patches: List[Dict[str, Any]],
        contributing_module_root: Path
    ) -> str:
        """
        將 patches 宣告之內容注入 template_content 對應的 Slot 插槽中。

        :param template_content: 原始基準模板字串 (來自 workflows/commands/*.md)
        :param patches: List of Dict (含 target_slot, position, content_file)
        :param contributing_module_root: 貢獻模組根目錄，用於解析 content_file 相對路徑
        :return: 注入後的 Markdown 字串 (尚未剝除標記，支援多模組鏈式疊加)
        """
        result = template_content
        for patch in patches:
            target_slot = patch.get("target_slot")
            position = patch.get("position", "append")
            content_rel_path = patch.get("content_file")
            
            if not target_slot or not content_rel_path:
                continue

            content_file = contributing_module_root / content_rel_path
            if not content_file.exists():
                continue
                
            injected_text = content_file.read_text(encoding="utf-8").strip()
            slot_marker = f"<!-- YSCB_SLOT:{target_slot} -->"
            
            if slot_marker in result:
                if position == "prepend":
                    replacement = f"\n\n{injected_text}\n\n{slot_marker}"
                else:  # append (default)
                    replacement = f"{slot_marker}\n\n{injected_text}\n"
                result = result.replace(slot_marker, replacement, 1)
                
        return result

    @classmethod
    def strip_slot_markers(cls, content: str) -> str:
        """
        安全正則剝除所有未命中或殘留的 YSCB_SLOT HTML 註解標記，確保輸出純淨。

        :param content: 包含 Slot 標記的 Markdown 字串
        :return: 100% 純淨的 Markdown 字串
        """
        return cls.SLOT_PATTERN.sub('', content)
```

---

### 2.4 `agents-workflow`: `IDECacheTracker` 快取與孤兒檔案清理

```python
import json
from pathlib import Path
from typing import List, Set

class IDECacheTracker:
    """IDE 工作流指令生成快取與檔案追蹤器"""

    CACHE_FILE = Path(".yscb_cache/ide_workflow_manifest.json")

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache_path = project_root / self.CACHE_FILE

    def get_tracked_files(self) -> Set[Path]:
        """取得上一次生成之檔案清單 (絕對路徑)"""
        if not self.cache_path.exists():
            return set()
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return {self.project_root / rel_path for rel_path in data.get("files", [])}
        except Exception:
            return set()

    def clean_orphans(self, current_files: List[Path]) -> List[Path]:
        """
        比對前次紀錄，安全刪除本次不再產出的孤兒指令檔案。

        :param current_files: 本次成功生成之檔案清單 (絕對路徑)
        :return: 已被刪除的檔案清單
        """
        tracked = self.get_tracked_files()
        current_set = set(current_files)
        orphans = tracked - current_set
        deleted: List[Path] = []

        for orphan in orphans:
            if orphan.exists() and orphan.is_file():
                try:
                    orphan.unlink()
                    deleted.append(orphan)
                except OSError:
                    pass

        return deleted

    def save_manifest(self, current_files: List[Path]) -> None:
        """更新快取紀錄清單"""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        rel_files = [str(f.relative_to(self.project_root)).replace("\\", "/") for f in current_files]
        self.cache_path.write_text(
            json.dumps({"files": sorted(rel_files)}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
```

---

### 2.5 `agents-workflow`: `ExtensionRegistry` 雙層發現器

```python
from pathlib import Path
from typing import Any, Dict, Optional

class ExtensionRegistry:
    """雙層 Extension 發現與優先級調度器"""

    @classmethod
    def discover_all(cls, context: ProjectContext) -> Dict[str, Dict[str, Any]]:
        """
        掃描並建立全域 Extension 註冊表。
        第一層: sop_ext:// (專案根目錄 extensions/，最高優先)
        第二層: 各已安裝模組 contributes["agents-workflow"]["sop_extensions"]

        :return: Dict[ext_name, Dict[屬性]]
        """
        registry: Dict[str, Dict[str, Any]] = {}

        # 1. 載入第二層：跨模組貢獻 Extension
        contributions = context.get_contributions("agents-workflow")
        for mod_name, mod_dir, payload in contributions:
            ext_list = payload.get("sop_extensions", [])
            for ext in ext_list:
                name = ext.get("name")
                if not name:
                    continue
                script_rel = ext.get("script")
                doc_rel = ext.get("doc")
                registry[name] = {
                    "name": name,
                    "source_type": "module",
                    "module_name": mod_name,
                    "script_path": (mod_dir / script_rel) if script_rel else None,
                    "doc_path": (mod_dir / doc_rel) if doc_rel else None,
                    "trigger": ext.get("trigger", "on_demand")
                }

        # 2. 載入第一層：專案本地 extensions/ (覆蓋同名項目)
        project_ext_dir = context.project_root / "extensions"
        if project_ext_dir.exists():
            for script_file in project_ext_dir.glob("*_verify.py"):
                name = script_file.stem.replace("_verify", "_ext")
                doc_file = project_ext_dir / f"{name}.md"
                registry[name] = {
                    "name": name,
                    "source_type": "sop_ext",
                    "module_name": None,
                    "script_path": script_file,
                    "doc_path": doc_file if doc_file.exists() else None,
                    "trigger": "always" if "dogfooding" in name else "on_demand"
                }

        return registry
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 依賴項目與檔案位置 | 呼叫方式 / 簽名 | 驗證狀態 |
|:---|:---|:---|:---:|
| 讀取模組貢獻 | `ProjectContext.get_contributions` (`context.py`) | `ctx.get_contributions("agents-workflow")` | ❌ 需新增 |
| 派發生命週期廣播 | `ModuleManager._broadcast_modules_changed` (`yscb_installer.py`) | `self._broadcast_modules_changed(changes)` | ❌ 需新增 |
| 動態 Slot 合成 | `SOPSynthesizer.synthesize_sop` (`sop_synthesizer.py`) | `SOPSynthesizer.synthesize_sop(text, patches, root)` | ❌ 需新增 |
| 標記剝除 | `SOPSynthesizer.strip_slot_markers` (`sop_synthesizer.py`) | `SOPSynthesizer.strip_slot_markers(text)` | ❌ 需新增 |
| 孤兒檔案清理 | `IDECacheTracker.clean_orphans` (`ide_sync.py`) | `tracker.clean_orphans(files)` | ❌ 需新增 |
| 雙層 Extension 發現 | `ExtensionRegistry.discover_all` (`ext_registry.py`) | `ExtensionRegistry.discover_all(ctx)` | ❌ 需新增 |

> **第三方依賴**：100% 使用 Python 標準庫（`re`, `json`, `pathlib`, `subprocess`, `sys`, `typing`），**無引入任何第三方外部套件**。

---

## 4. Decision Records

### [API:DR-01] 批次 Delta 清單作為 Hook CLI 傳參協定
- **議題**：`_on_modules_changed.py` 如何接收本次指令所異動的多個模組？
- **結論**：採用 CLI 位置參數列表格式 `action:module_name`（例：`installed:unity-ext updated:core`）。
- **理由**：Shell 友善且在 Windows / POSIX 均無引號轉義風險；接收端只需 `arg.split(":", 1)` 即可完成解析，極致輕量安全。
