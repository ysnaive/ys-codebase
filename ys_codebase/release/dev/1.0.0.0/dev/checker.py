"""
Compliance Checker implementation for YS-Codebase modules.
"""
import os
import ast
from typing import Tuple, List, Dict
from core import uri

class Checker:
    def __init__(self):
        pass

    def check_module(self, name: str) -> Tuple[bool, List[str]]:
        errors = []
        src_uri = f"module.source.root://{name}"
        if not uri.exists(src_uri):
            return False, [f"Module source not found at {src_uri}."]
        
        # 1. Check manifest.json
        manifest_uri = f"{src_uri}/manifest.json"
        if not uri.exists(manifest_uri):
            errors.append("Missing 'manifest.json'.")
        else:
            try:
                m_data = uri.read_json(manifest_uri)
                for field in ("name", "version", "entry"):
                    if field not in m_data:
                        errors.append(f"Missing required field '{field}' in manifest.json.")
                if m_data.get("name") != name:
                    errors.append(f"Manifest name '{m_data.get('name')}' does not match directory name '{name}'.")
            except Exception as e:
                errors.append(f"Invalid JSON in manifest.json: {e}")
                
        # 2. Check entry point
        cli_uri = f"{src_uri}/scripts/cli.py"
        if not uri.exists(cli_uri):
            errors.append("Missing entry point 'scripts/cli.py'.")
            
        # 3. Static AST syntax check on all python files
        real_dir = uri.resolve(src_uri)
        for root, _, files in os.walk(real_dir):
            if "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, real_dir).replace("\\", "/")
                    try:
                        with open(full_p, "r", encoding="utf-8") as py_f:
                            ast.parse(py_f.read(), filename=rel_p)
                    except SyntaxError as se:
                        errors.append(f"SyntaxError in {rel_p}:{se.lineno}: {se.msg}")
                    except Exception as e:
                        errors.append(f"Error parsing {rel_p}: {e}")
                        
        passed = (len(errors) == 0)
        return passed, errors

    def check_all(self) -> Dict[str, Tuple[bool, List[str]]]:
        results = {}
        src_root_uri = "module.source.root://"
        if not uri.exists(src_root_uri):
            return results
        
        for item in uri.listdir(src_root_uri):
            item_uri = f"module.source.root://{item}"
            if uri.is_dir(item_uri) and uri.exists(f"{item_uri}/manifest.json"):
                results[item] = self.check_module(item)
                
        return results
