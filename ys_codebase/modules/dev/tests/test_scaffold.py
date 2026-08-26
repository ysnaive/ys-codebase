"""
Official test suite for dev.scaffold.Scaffolder.
"""
import os
from dev.testing import YSCBTestCase
from dev.scaffold import Scaffolder
from core import uri

class TestDevScaffolder(YSCBTestCase):
    def setUp(self):
        super().setUp()
        self.scaffolder = Scaffolder()

    def test_create_module_creates_all_templates(self):
        """Verify create_module produces manifest, cli.py, __init__.py, .yscbignore."""
        mod_name = "test_mod_scaffold_x"
        ok, msg = self.scaffolder.create_module(mod_name, desc="Unit test module")
        self.assertTrue(ok, f"Scaffold failed: {msg}")
        
        src_uri = f"module.source://{mod_name}"
        self.assertTrue(uri.exists(f"{src_uri}/manifest.json"))
        self.assertTrue(uri.exists(f"{src_uri}/scripts/cli.py"))
        self.assertTrue(uri.exists(f"{src_uri}/{mod_name}/__init__.py"))
        self.assertTrue(uri.exists(f"{src_uri}/.yscbignore"))
        
        # Cleanup created source
        uri.rmtree(src_uri)
        self.mark_passed()

    def test_create_duplicate_module_rejected(self):
        """Verify scaffolding over existing module fails."""
        mod_name = "test_mod_dup"
        self.scaffolder.create_module(mod_name)
        
        # Second attempt must fail
        ok2, msg2 = self.scaffolder.create_module(mod_name)
        self.assertFalse(ok2)
        self.assertIn("already exists", msg2)
        
        uri.rmtree(f"module.source://{mod_name}")
        self.mark_passed()
