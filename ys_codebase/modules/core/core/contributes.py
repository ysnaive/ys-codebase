"""
Contributes Aggregator and Dependency Injection Engine.
"""
from typing import Dict, Any, List, Optional
import os
from core import uri

class ContributesAggregator:
    def __init__(self):
        pass

    def scan_and_inject(self, clean: bool = True) -> None:
        if not uri.exists("module.root://"):
            return
        
        installed_modules = uri.listdir("module.root://")
        for mod in installed_modules:
            manifest_uri = f"module.root://{mod}/manifest.json"
            if not uri.exists(manifest_uri):
                continue
            
            # Read format if exists
            fmt_uri = f"module.root://{mod}/contributes.format.md"
            
            # Scan contributed files targeting this module
            for donor in installed_modules:
                donor_contrib = f"module.root://{donor}/contributes.{mod}.json"
                if uri.exists(donor_contrib):
                    try:
                        contrib_data = uri.read_json(donor_contrib)
                        self._apply_module_contribution(mod, donor, contrib_data)
                    except Exception as e:
                        print(f"[core:contributes] Warning: failed to apply contribution from {donor} to {mod}: {e}")

    def _apply_module_contribution(self, target_module: str, donor_module: str, contrib_data: Dict[str, Any]) -> None:
        target_cfg_uri = f"config.root://{target_module}/contributes.{donor_module}.json"
        uri.write_json(target_cfg_uri, contrib_data)
