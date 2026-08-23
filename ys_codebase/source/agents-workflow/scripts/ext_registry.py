"""
ext_registry.py — 雙層 Extension 發現與優先級調度器
"""

import re
from pathlib import Path
from typing import Any, Dict, Optional, List


class ExtensionRegistry:
    """雙層 Extension 發現與優先級調度器"""

    @classmethod
    def discover_all(cls, context: Any, start_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
        """
        掃描並建立全域 Extension 註冊表。
        第一層: sop_ext:// (專案根目錄 extensions/，最高優先)
        第二層: 各已安裝模組 contributes["agents-workflow"]["sop_extensions"]

        :param context: yscb_core.ProjectContext 實例或類別
        :param start_dir: 起始搜尋目錄
        :return: Dict[ext_name, Dict[屬性]]
        """
        registry: Dict[str, Dict[str, Any]] = {}

        # 1. 載入第二層：跨模組貢獻 Extension
        try:
            if hasattr(context, "get_contributions"):
                try:
                    contributions = context.get_contributions("agents-workflow", start_dir=start_dir)
                except TypeError:
                    contributions = context.get_contributions("agents-workflow")
            else:
                contributions = []
        except Exception:
            contributions = []

        for mod_name, mod_dir, payload in contributions:
            if not isinstance(payload, dict):
                continue
            ext_list = payload.get("sop_extensions", [])
            if not isinstance(ext_list, list):
                continue
            for ext in ext_list:
                if not isinstance(ext, dict):
                    continue
                name = ext.get("name")
                if not name:
                    continue
                script_rel = ext.get("script")
                doc_rel = ext.get("doc")
                registry[name] = {
                    "name": name,
                    "source_type": "module",
                    "module_name": mod_name,
                    "script_path": (mod_dir / script_rel).resolve() if script_rel else None,
                    "doc_path": (mod_dir / doc_rel).resolve() if doc_rel else None,
                    "trigger": ext.get("trigger", "on_demand")
                }

        # 2. 載入主機內建 Extension 目錄 (若存在)
        try:
            if hasattr(context, "get_module_dir"):
                try:
                    mod_dir = context.get_module_dir("agents-workflow", start_dir=start_dir)
                except TypeError:
                    mod_dir = context.get_module_dir("agents-workflow")
                host_ext_dir = mod_dir / "workflows" / "extensions"
                if host_ext_dir.is_dir():
                    for doc_file in host_ext_dir.glob("*.md"):
                        name = doc_file.stem
                        script_file = host_ext_dir / f"{name}_verify.py"
                        if name not in registry:
                            registry[name] = {
                                "name": name,
                                "source_type": "module",
                                "module_name": "agents-workflow",
                                "script_path": script_file.resolve() if script_file.is_file() else None,
                                "doc_path": doc_file.resolve(),
                                "trigger": "on_demand"
                            }
        except Exception:
            pass

        # 3. 載入第一層：專案本地 extensions/ (覆蓋同名項目)
        try:
            if hasattr(context, "get_project_root"):
                try:
                    project_root = context.get_project_root(start_dir=start_dir)
                except TypeError:
                    project_root = context.get_project_root()
            elif start_dir:
                project_root = start_dir
            else:
                project_root = Path.cwd()

            project_ext_dir = project_root / "extensions"
            if project_ext_dir.is_dir():
                for doc_file in project_ext_dir.glob("*.md"):
                    name = doc_file.stem
                    trigger = "always" if "dogfooding" in name else "on_demand"

                    # 嘗試自 Frontmatter 解析精確 name 與 trigger
                    try:
                        content = doc_file.read_text(encoding="utf-8", errors="ignore")
                        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                        if fm_match:
                            for line in fm_match.group(1).splitlines():
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    k = k.strip().lower()
                                    v = v.strip().strip("[]'\"")
                                    if k == "name":
                                        name = v
                                    elif k == "trigger":
                                        trigger = v.lower()
                    except Exception:
                        pass

                    script_file = project_ext_dir / f"{name.replace('_ext', '')}_verify.py"
                    if not script_file.is_file():
                        script_file = project_ext_dir / f"{name}_verify.py"

                    registry[name] = {
                        "name": name,
                        "source_type": "sop_ext",
                        "module_name": None,
                        "script_path": script_file.resolve() if script_file.is_file() else None,
                        "doc_path": doc_file.resolve(),
                        "trigger": trigger
                    }

                for script_file in project_ext_dir.glob("*_verify.py"):
                    base = script_file.stem.replace("_verify", "")
                    ext_name = f"{base}_ext" if not base.endswith("_ext") else base
                    if ext_name not in registry and base not in registry:
                        doc_file = project_ext_dir / f"{ext_name}.md"
                        if not doc_file.is_file():
                            doc_file = project_ext_dir / f"{base}.md"
                        registry[ext_name] = {
                            "name": ext_name,
                            "source_type": "sop_ext",
                            "module_name": None,
                            "script_path": script_file.resolve(),
                            "doc_path": doc_file.resolve() if doc_file.is_file() else None,
                            "trigger": "always" if "dogfooding" in base else "on_demand"
                        }
        except Exception:
            pass

        return registry
