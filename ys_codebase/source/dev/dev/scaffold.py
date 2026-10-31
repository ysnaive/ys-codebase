"""
Scaffolder implementation for YS-Codebase modules.
"""
import re
from typing import Tuple
from core import vfs


class Scaffolder:
    def create_module(self, name: str, description: str = "") -> Tuple[bool, str]:
        if not name:
            return False, "Module name cannot be empty."

        if not re.match(r"^[a-zA-Z0-9_][a-zA-Z0-9_-]*$", name):
            return False, f"Invalid module name '{name}'. Module name must contain only alphanumeric characters, underscores, or hyphens."

        target_src_uri = f"module.source://{name}"
        if vfs.exists(target_src_uri):
            return False, f"Module '{name}' already exists at {target_src_uri}."

        final_desc = description or f"YS-Codebase module: {name}"

        # 1. Create manifest.json
        vfs.write_json(f"{target_src_uri}/manifest.json", {
            "name": name,
            "version": "0.1.0.0",
            "description": final_desc,
            "entry": "scripts/cli.py",
            "dependencies": {
                "core": ">=1.0.0"
            }
        })

        # 2. Create scripts/cli.py
        cli_content = f'''"""
CLI Entry point for module {name}.
"""
from typing import Any
import sys

from core.guard import guard_dispatch
from core.commands import CmdBags
from core import uri


def hello(cmd_bags: Any) -> int:
    guard_dispatch("{name}")
    print(f"[{name}] Hello from YSCB module {name}!")
    return 0
'''
        vfs.write_text(f"{target_src_uri}/scripts/cli.py", cli_content)

        # 3. Create <pkg_name>/__init__.py
        pkg_name = name.replace("-", "_")
        init_content = f'''"""
{name} package initialization.
"""
__version__ = "0.1.0.0"
'''
        vfs.write_text(f"{target_src_uri}/{pkg_name}/__init__.py", init_content)

        # 4. Create tests/__init__.py and tests/test_basic.py
        vfs.write_text(f"{target_src_uri}/tests/__init__.py", '"""\nTest package.\n"""\n')
        test_content = f'''"""
Basic test for {name}.
"""
import unittest
from dev.testing import YSCBTestCase
from core.commands import CmdBags
from scripts import cli


class TestBasic(YSCBTestCase):
    def test_sample(self):
        bags = CmdBags(raw_cmd="hello", command="hello", args=[], options={{}})
        ret = cli.hello(bags)
        self.assertEqual(ret, 0)
        self.mark_passed()


if __name__ == "__main__":
    unittest.main()
'''
        vfs.write_text(f"{target_src_uri}/tests/test_basic.py", test_content)

        # 5. Create .yscbignore
        ignore_content = '''# Development ignore list
tests/
*.tmp
*.bak
.pytest_cache/
'''
        vfs.write_text(f"{target_src_uri}/.yscbignore", ignore_content)

        # 6. Create contributes/_format.json, contributes/_manifest.md, and sample contributes/core.json
        format_content = {
            "_types": {},
            "sample_point": {
                "description": f"Contribution point provided by {name}",
                "format": {
                    "item_name": "str!",
                    "enabled": "bool? = true"
                }
            }
        }
        vfs.write_json(f"{target_src_uri}/contributes/_format.json", format_content)

        manifest_content = f"""# {name} Contributes Manifest

> 本清冊記錄 `{name}` 模組對外貢獻之擴充能力與協議。

## 1. 外部注入清冊 (Egress Contributions)
- `core.json`: 向微內核註冊之 CLI 指令。
"""
        vfs.write_text(f"{target_src_uri}/contributes/_manifest.md", manifest_content)

        core_contrib_content = {
            "commands": {
                "description": final_desc,
                "cmd": {
                    "hello": {
                        "description": f"Say hello from {name}",
                        "tier": "safe",
                        "server_compatible": True,
                        "usage": {
                            "pros": [f"執行 {name} 基礎打招呼指令"],
                            "cons": []
                        }
                    }
                }
            }
        }
        vfs.write_json(f"{target_src_uri}/contributes/core.json", core_contrib_content)

        return True, f"Successfully created module '{name}' at {target_src_uri}."
