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
        src_uri = f"module.source://{name}"
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
                        
        # 4. Check test classes inherit from YSCBTestCase (Gate 1: Static Type Guard)
        tests_real_dir = os.path.join(real_dir, "tests")
        if os.path.isdir(tests_real_dir):
            for t_file in os.listdir(tests_real_dir):
                if t_file.startswith("test_") and t_file.endswith(".py"):
                    t_full = os.path.join(tests_real_dir, t_file)
                    try:
                        with open(t_full, "r", encoding="utf-8") as tf:
                            tree = ast.parse(tf.read(), filename=t_file)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                                base_names = []
                                for b in node.bases:
                                    if isinstance(b, ast.Name):
                                        base_names.append(b.id)
                                    elif isinstance(b, ast.Attribute):
                                        base_names.append(b.attr)
                                if "TestCase" in base_names and "YSCBTestCase" not in base_names:
                                    errors.append(
                                        f"Security Guard: Test class '{node.name}' in tests/{t_file}:{node.lineno} "
                                        f"directly subclasses 'unittest.TestCase'. Must inherit from 'dev.testing.case.YSCBTestCase'."
                                    )
                    except Exception as e:
                        errors.append(f"Error parsing test file tests/{t_file}: {e}")

        passed = (len(errors) == 0)
        return passed, errors

    def check_all(self) -> Dict[str, Tuple[bool, List[str]]]:
        results = {}
        src_root_uri = "module.source://"
        if not uri.exists(src_root_uri):
            return results
        
        for item in uri.listdir(src_root_uri):
            item_uri = f"module.source://{item}"
            if uri.is_dir(item_uri) and uri.exists(f"{item_uri}/manifest.json"):
                results[item] = self.check_module(item)
                
        return results
