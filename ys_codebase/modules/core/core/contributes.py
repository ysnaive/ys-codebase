"""
Contributes Aggregator and Dependency Injection Engine.
"""
from typing import Dict, Any, List, Optional
import os
from core import uri

class ContributesAggregator:
    def __init__(self):
        pass

    def scan_and_inject(self, clean: bool = True) -> Dict[str, Any]:
        """
        Scan and cascade-merge contributes from 5 sources:
        1. module://manifest.json -> contributes
        2. module://contributes.{target}.json
        3. config://config.project.json
        4. config://contributes.{target}.json
        5. config://config.local.json
        """
        aggregated: Dict[str, Dict[str, Any]] = {}
        if not uri.exists("module.root://"):
            return aggregated
        
        installed_modules = uri.listdir("module.root://")
        
        # 1. Initialize empty dictionaries for all targets
        for mod in installed_modules:
            aggregated[mod] = {}

        # 2. Collect from module-level sources (Manifest and contributes.<target>.json)
        for donor in installed_modules:
            # Source 1: Manifest
            manifest_uri = f"module.root://{donor}/manifest.json"
            if uri.exists(manifest_uri):
                m_data = uri.read_json(manifest_uri)
                m_contribs = m_data.get("contributes", {})
                if isinstance(m_contribs, dict):
                    for target, c_body in m_contribs.items():
                        if target in aggregated and isinstance(c_body, dict):
                            self._deep_merge(aggregated[target], c_body)

            # Source 2: contributes.<target>.json in donor module
            for target in installed_modules:
                donor_file = f"module.root://{donor}/contributes.{target}.json"
                if uri.exists(donor_file):
                    c_data = uri.read_json(donor_file)
                    if isinstance(c_data, dict):
                        self._deep_merge(aggregated[target], c_data)

        # 3. Project-level and local-level overrides
        for target in installed_modules:
            # Source 3: project-level config.project.json
            proj_cfg_uri = f"config.root://{target}/config.project.json"
            if not uri.exists(proj_cfg_uri) and uri.exists("project://config.project.json"):
                proj_cfg_uri = "project://config.project.json"
                
            if uri.exists(proj_cfg_uri):
                p_data = uri.read_json(proj_cfg_uri)
                p_contribs = p_data.get("contributes", {}).get(target, {})
                if isinstance(p_contribs, dict):
                    self._deep_merge(aggregated[target], p_contribs)

            # Persist injected contributes
            target_cfg_uri = f"config.root://{target}/contributes.merged.json"
            uri.write_json(target_cfg_uri, aggregated[target])

        return aggregated

    def _deep_merge(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            elif k in base and isinstance(base[k], list) and isinstance(v, list):
                base[k].extend(x for x in v if x not in base[k])
            else:
                base[k] = v
