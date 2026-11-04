"""
ParserRegistry for module:ast (`ast_engine.parsers.registry`).
Loads language configurations from `contributes.get("ast")` (or injected `contributes_data` / built-in defaults)
and dispatches `TreeSitterDriver` and custom domain parsers.
"""

import copy
import importlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..schema import LanguageConfig, SymbolCallSite, UnifiedSymbol
from .base import BaseParser
from .treesitter import TreeSitterDriver

logger = logging.getLogger("ast.parsers.registry")

DEFAULT_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "python": {
        "id": "python",
        "name": "Python",
        "extensions": [".py", ".pyi"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_python",
        "query_file": "assets/queries/python.scm",
    },
    "c": {
        "id": "c",
        "name": "C",
        "extensions": [".c", ".h"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_c",
        "query_file": "assets/queries/c.scm",
    },
    "cpp": {
        "id": "cpp",
        "name": "C++",
        "extensions": [".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_cpp",
        "query_file": "assets/queries/cpp.scm",
    },
    "javascript": {
        "id": "javascript",
        "name": "JavaScript",
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_javascript",
        "query_file": "assets/queries/javascript.scm",
    },
    "typescript": {
        "id": "typescript",
        "name": "TypeScript",
        "extensions": [".ts", ".tsx"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_typescript:language_typescript",
        "query_file": "assets/queries/typescript.scm",
    },
    "c_sharp": {
        "id": "c_sharp",
        "name": "C#",
        "extensions": [".cs"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_c_sharp",
        "query_file": "assets/queries/c_sharp.scm",
    },
    "markdown": {
        "id": "markdown",
        "name": "Markdown",
        "extensions": [".md", ".markdown"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_markdown",
        "query_file": "assets/queries/markdown.scm",
    },
    "spice": {
        "id": "spice",
        "name": "SPICE",
        "extensions": [".sp", ".cir", ".spice", ".net", ".cdl", ".netlist"],
        "mode": "custom",
        "parser_entry": "ast_engine.parsers.spice_parser:SpiceParser",
    },
    "html": {
        "id": "html",
        "name": "HTML",
        "extensions": [".html", ".htm"],
        "mode": "custom",
        "parser_entry": "ast_engine.parsers.html_parser:HtmlParser",
    },
    "css": {
        "id": "css",
        "name": "CSS",
        "extensions": [".css", ".scss", ".sass", ".less"],
        "mode": "custom",
        "parser_entry": "ast_engine.parsers.css_parser:CssParser",
    },
}


class ParserRegistry:
    """
    Dynamic parser registry and dispatcher for module:ast.
    Driven by `contributes.get("ast")` `languages` declarations with built-in default language mappings.
    """

    def __init__(
        self,
        register_defaults: bool = True,
        contributes_data: Optional[Dict[str, Any]] = None,
    ):
        self._parsers: List[Tuple[int, BaseParser]] = []
        self._language_configs: Dict[str, LanguageConfig] = {}
        self.load_errors: Dict[str, str] = {}

        if register_defaults:
            self._load_from_contributes(contributes_data=contributes_data)

    @staticmethod
    def _ensure_search_paths(provider: Optional[str] = None) -> None:
        """Ensure module root, `project://`, `yscb.host://`, and `module://<provider>` are in `sys.path`."""
        from core.platform import ensure_installed_modules_path

        ast_mod_root = str(Path(__file__).resolve().parents[2])
        candidates: List[str] = [ast_mod_root]
        try:
            from core import uri

            if provider and provider not in ("unknown", "project_override", "project"):
                try:
                    mod_res = uri.resolve(f"module://{provider}", interactive=False)
                    if mod_res and not str(mod_res).startswith("!undefined"):
                        candidates.append(mod_res)
                except Exception:
                    pass
        except Exception:
            pass

        cwd = os.getcwd()
        if cwd:
            candidates.append(cwd)

        valid_extras: List[str] = []
        for cand in candidates:
            if not cand or not os.path.isdir(cand):
                continue
            abs_p = os.path.abspath(cand)
            norm_p = abs_p.replace("\\", "/")
            if "/source/" in norm_p or norm_p.endswith("/source"):
                continue
            valid_extras.append(abs_p)

        prio = provider if (provider and provider not in ("unknown", "project_override", "project")) else "ast"
        ensure_installed_modules_path(
            priority_module=prio,
            include_host_roots=True,
            extra_paths=valid_extras,
        )

    @staticmethod
    def _bind_configured_extensions(parser_inst: BaseParser, extensions: Tuple[str, ...]) -> None:
        """Merge configured `extensions` onto the parser instance without mutating class-level sets."""
        norm_exts = {
            (str(e).strip().lower() if str(e).strip().startswith(".") else "." + str(e).strip().lower())
            for e in extensions
            if str(e).strip()
        }
        if not norm_exts:
            return
        existing = getattr(parser_inst, "SUPPORTED_EXTENSIONS", None)
        if isinstance(existing, (set, list, tuple, frozenset)):
            existing_norm = {
                (str(e).strip().lower() if str(e).strip().startswith(".") else "." + str(e).strip().lower())
                for e in existing
                if str(e).strip()
            }
            parser_inst.SUPPORTED_EXTENSIONS = existing_norm | norm_exts  # type: ignore[attr-defined]
        else:
            parser_inst.SUPPORTED_EXTENSIONS = norm_exts  # type: ignore[attr-defined]

    def _instantiate_custom_parser(self, entry_str: str, provider: Optional[str] = None) -> BaseParser:
        """Instantiate custom parser from `module.path:ClassName`, `file.py:ClassName`, or `uri://...:ClassName`."""
        self._ensure_search_paths(provider=provider)

        if "://" in entry_str:
            scheme_part, rest = entry_str.split("://", 1)
            if ":" in rest:
                uri_path_part, cls_name = rest.rsplit(":", 1)
                target_uri = f"{scheme_part}://{uri_path_part}"
            else:
                target_uri, cls_name = entry_str.rsplit(".", 1)
            from core import uri

            resolved_target = uri.resolve(target_uri, interactive=False)
            target_path = Path(resolved_target)
            if target_path.is_file() or target_path.suffix == ".py":
                mod_name = f"_yscb_custom_parser_{target_path.stem}_{abs(hash(str(target_path)))}"
                spec = importlib.util.spec_from_file_location(mod_name, str(target_path))
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot load spec from file '{target_path}'")
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                parser_cls = getattr(mod, cls_name)
                return parser_cls()
            parent_dir = str(target_path.parent if target_path.suffix else target_path)
            if os.path.isdir(parent_dir):
                from core.platform import ensure_installed_modules_path

                ensure_installed_modules_path(extra_paths=[parent_dir])
            mod_rel = target_path.name.replace("/", ".").replace("\\", ".")
            mod = importlib.import_module(mod_rel)
            parser_cls = getattr(mod, cls_name)
            return parser_cls()

        if ":" in entry_str:
            mod_name, cls_name = entry_str.rsplit(":", 1)
        else:
            mod_name, cls_name = entry_str.rsplit(".", 1)

        if mod_name.endswith(".py") or "/" in mod_name or "\\" in mod_name:
            cand_file = Path(mod_name)
            if not cand_file.is_absolute():
                for sp in list(sys.path):
                    probe = Path(sp) / mod_name
                    if probe.is_file():
                        cand_file = probe
                        break
            if cand_file.is_file():
                dyn_name = f"_yscb_custom_parser_{cand_file.stem}_{abs(hash(str(cand_file)))}"
                spec = importlib.util.spec_from_file_location(dyn_name, str(cand_file))
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot load spec from file '{cand_file}'")
                mod = importlib.util.module_from_spec(spec)
                sys.modules[dyn_name] = mod
                spec.loader.exec_module(mod)
                parser_cls = getattr(mod, cls_name)
                return parser_cls()

        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            importlib.invalidate_caches()
            self._ensure_search_paths(provider=provider)
            mod = importlib.import_module(mod_name)

        parser_cls = getattr(mod, cls_name)
        return parser_cls()

    def _load_from_contributes(self, contributes_data: Optional[Dict[str, Any]] = None) -> None:
        """Load `languages` from `contributes_data`, `contributes.get("ast")`, or built-in defaults."""
        self.load_errors.clear()
        languages_dict: Dict[str, Any] = copy.deepcopy(DEFAULT_LANGUAGES)

        overlay_langs: Dict[str, Any] = {}
        if contributes_data and isinstance(contributes_data, dict):
            raw_ov = contributes_data.get("languages", {})
            if isinstance(raw_ov, dict):
                overlay_langs = raw_ov
        else:
            try:
                from core import contributes

                data = contributes.get("ast")
                if isinstance(data, dict) and isinstance(data.get("languages"), dict):
                    overlay_langs = data["languages"]
            except Exception:
                pass

            if not overlay_langs:
                try:
                    mod_contrib = Path(__file__).resolve().parents[2] / "contributes" / "ast.json"
                    if mod_contrib.exists():
                        with open(mod_contrib, "r", encoding="utf-8", errors="replace") as f:
                            m_data = json.load(f)
                        if isinstance(m_data, dict) and isinstance(m_data.get("languages"), dict):
                            overlay_langs = m_data["languages"]
                except Exception as exc:
                    logger.warning(f"ParserRegistry: Failed to load contributes/ast.json: {exc}")

        for lang_id, lang_cfg in overlay_langs.items():
            if not isinstance(lang_cfg, dict):
                continue
            if lang_id in languages_dict and isinstance(languages_dict[lang_id], dict):
                merged = dict(languages_dict[lang_id])
                merged.update(lang_cfg)
                languages_dict[lang_id] = merged
            else:
                languages_dict[lang_id] = dict(lang_cfg)

        for lang_id, raw_cfg in languages_dict.items():
            if not isinstance(raw_cfg, dict):
                continue
            try:
                cfg_data = dict(raw_cfg)
                provider = str(cfg_data.get("__provider__") or cfg_data.get("_provider") or "")
                if "id" not in cfg_data:
                    cfg_data["id"] = lang_id
                cfg = LanguageConfig.from_dict(cfg_data)
                self._language_configs[cfg.id] = cfg

                if cfg.mode == "tree_sitter":
                    driver = TreeSitterDriver(cfg)
                    self._bind_configured_extensions(driver, cfg.extensions)
                    if driver._language is None or driver._parser is None:
                        err_msg = f"Failed to load tree-sitter grammar '{cfg.grammar}' or query '{cfg.query_file}'"
                        self.load_errors[cfg.id] = err_msg
                    self.register_parser(driver, priority=100)
                elif cfg.mode == "custom" and cfg.parser_entry:
                    try:
                        parser_inst = self._instantiate_custom_parser(cfg.parser_entry, provider=provider)
                        self._bind_configured_extensions(parser_inst, cfg.extensions)
                        self.register_parser(parser_inst, priority=100)
                    except Exception as exc:
                        err_msg = f"Failed to instantiate custom parser '{cfg.parser_entry}': {exc}"
                        self.load_errors[cfg.id] = err_msg
                        logger.warning(err_msg)
            except Exception as exc:
                err_msg = f"Error loading language config '{lang_id}': {exc}"
                self.load_errors[str(lang_id)] = err_msg
                logger.warning(err_msg)

    def register_parser(self, parser: BaseParser, priority: int = 100) -> None:
        """Register a parser instance with priority (higher value takes precedence)."""
        self._parsers.append((priority, parser))
        self._parsers.sort(key=lambda x: x[0], reverse=True)

    @property
    def language_configs(self) -> Dict[str, LanguageConfig]:
        return dict(self._language_configs)

    def get_supported_extensions(self) -> Set[str]:
        """Return the set of all configured file extensions (lowercase with leading dot)."""
        exts: Set[str] = set()
        for cfg in self._language_configs.values():
            for e in cfg.extensions:
                ext_clean = str(e).strip().lower()
                if not ext_clean.startswith("."):
                    ext_clean = "." + ext_clean
                exts.add(ext_clean)
        for _, parser in self._parsers:
            if hasattr(parser, "SUPPORTED_EXTENSIONS") and isinstance(parser.SUPPORTED_EXTENSIONS, (set, list, tuple)):
                for e in parser.SUPPORTED_EXTENSIONS:
                    ext_clean = str(e).strip().lower()
                    if not ext_clean.startswith("."):
                        ext_clean = "." + ext_clean
                    exts.add(ext_clean)
        return exts

    def get_parser(self, file_path: Union[str, Path]) -> Optional[BaseParser]:
        """Return the highest-priority parser that supports `file_path`, or None."""
        for _, parser in self._parsers:
            try:
                if parser.can_parse(file_path):
                    return parser
            except Exception as exc:
                logger.warning(f"Error checking can_parse for {parser}: {exc}")
        return None

    def parse_file(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """Parse `file_path` content and return extracted UnifiedSymbol list."""
        parser = self.get_parser(file_path)
        if parser is None:
            return []
        try:
            return parser.parse(file_path=file_path, content=content, space=space)
        except Exception as exc:
            logger.warning(f"Unexpected error during parse_file '{file_path}' in space '{space}': {exc}")
            return []

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str = "unified",
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        """Extract symbol call sites from `file_path`."""
        parser = self.get_parser(file_path)
        if parser is None:
            return []
        try:
            return parser.extract_call_sites(file_path=file_path, content=content, space=space, symbols=symbols)
        except TypeError:
            try:
                return parser.extract_call_sites(file_path=file_path, content=content, space=space)
            except Exception as exc:
                logger.debug(f"Error extracting call sites from '{file_path}': {exc}")
                return []
        except Exception as exc:
            logger.debug(f"Error extracting call sites from '{file_path}': {exc}")
            return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """Extract file-level import mappings from `file_path`."""
        parser = self.get_parser(file_path)
        if parser is None:
            return {}
        try:
            return parser.extract_imports(file_path=file_path, content=content)
        except Exception as exc:
            logger.debug(f"Error extracting imports from '{file_path}': {exc}")
            return {}
