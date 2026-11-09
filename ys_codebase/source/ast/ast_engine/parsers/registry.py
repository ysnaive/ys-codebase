"""
ParserRegistry for module:ast (`ast_engine.parsers.registry`).
Loads language configurations from `contributes.get("ast")` (or injected `contributes_data` / built-in defaults)
and dispatches `TreeSitterDriver` and custom domain parsers.
"""

import copy
import dataclasses
import importlib
import json
import os
from pathlib import Path
import sys
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Union

from core.context import get_virtual_cwd
from core.loader import load_module_from_path
from core.log import log_debug, log_warn

from ..schema import (
    FileSymbolGraph,
    LanguageConfig,
    ProvenanceStep,
    RelationEdge,
    SymbolCallSite,
    SymbolNode,
    UnifiedSymbol,
)
from .base import BaseParser, EdgeRefiner, ModulePathResolver, SymbolProcessor, compute_content_hash
from .treesitter import TreeSitterDriver

DEFAULT_LANGUAGES: Mapping[str, Dict[str, Any]] = MappingProxyType({
    "python": {
        "id": "python",
        "name": "Python",
        "extensions": [".py", ".pyi"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_python",
        "query_file": "assets/queries/python.scm",
        "receiver_aliases": {"self_aliases": ["self", "cls"], "super_aliases": ["super"]},
    },
    "c": {
        "id": "c",
        "name": "C",
        "extensions": [".c", ".h"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_c",
        "query_file": "assets/queries/c.scm",
        "symbol_folding": {"header_extensions": [".h"], "impl_extensions": [".c"]},
    },
    "cpp": {
        "id": "cpp",
        "name": "C++",
        "extensions": [".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_cpp",
        "query_file": "assets/queries/cpp.scm",
        "receiver_aliases": {"self_aliases": ["this", "self"], "super_aliases": ["__super", "base"]},
        "symbol_folding": {
            "header_extensions": [".h", ".hpp", ".hxx", ".hh"],
            "impl_extensions": [".cpp", ".cxx", ".cc"],
        },
    },
    "javascript": {
        "id": "javascript",
        "name": "JavaScript",
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_javascript",
        "query_file": "assets/queries/javascript.scm",
        "receiver_aliases": {"self_aliases": ["this", "self"], "super_aliases": ["super", "base"]},
    },
    "typescript": {
        "id": "typescript",
        "name": "TypeScript",
        "extensions": [".ts", ".tsx"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_typescript:language_typescript",
        "query_file": "assets/queries/typescript.scm",
        "receiver_aliases": {"self_aliases": ["this", "self"], "super_aliases": ["super", "base"]},
        "symbol_folding": {"header_extensions": [".d.ts"], "impl_extensions": [".ts", ".tsx"]},
    },
    "c_sharp": {
        "id": "c_sharp",
        "name": "C#",
        "extensions": [".cs"],
        "mode": "tree_sitter",
        "grammar": "tree_sitter_c_sharp",
        "query_file": "assets/queries/c_sharp.scm",
        "receiver_aliases": {"self_aliases": ["this", "self"], "super_aliases": ["base"]},
        "symbol_folding": {"partial_modifier": "partial"},
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
})


class ParserRegistry:
    """
    Dynamic parser registry and dispatcher for module:ast.
    Driven by `contributes.get("ast")` `languages` declarations with built-in default language mappings.
    """

    def __init__(
        self,
        register_defaults: bool = True,
        contributes_data: Optional[Dict[str, Any]] = None,
        space_manager: Optional[Any] = None,
    ):
        self._parsers: List[Tuple[int, BaseParser]] = []
        self._language_configs: Dict[str, LanguageConfig] = {}
        self._module_resolvers: Dict[str, ModulePathResolver] = {}
        self._edge_refiners: Dict[str, Tuple[EdgeRefiner, ...]] = {}
        self._space_manager: Optional[Any] = space_manager
        self.load_errors: Dict[str, str] = {}

        if register_defaults or contributes_data is not None:
            self._load_from_contributes(contributes_data=contributes_data, include_defaults=register_defaults)

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

        cwd = str(get_virtual_cwd())
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
                mod_name = f"_yscb_mod_custom_parser.{target_path.stem}_{abs(hash(str(target_path)))}"
                mod = load_module_from_path(mod_name, target_path)
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
                dyn_name = f"_yscb_mod_custom_parser.{cand_file.stem}_{abs(hash(str(cand_file)))}"
                mod = load_module_from_path(dyn_name, cand_file)
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

    def _load_from_contributes(
        self,
        contributes_data: Optional[Dict[str, Any]] = None,
        include_defaults: bool = True,
    ) -> None:
        """Load `languages` from `contributes_data`, `contributes.get("ast")`, or built-in defaults."""
        self.load_errors.clear()
        languages_dict: Dict[str, Any] = copy.deepcopy(dict(DEFAULT_LANGUAGES)) if include_defaults else {}

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
                    log_warn(f"ParserRegistry: Failed to load contributes/ast.json: {exc}", stream="stderr")

        for lang_id, lang_cfg in overlay_langs.items():
            if not isinstance(lang_cfg, dict):
                continue
            if lang_id in languages_dict and isinstance(languages_dict[lang_id], dict):
                merged = dict(languages_dict[lang_id])
                for list_key in ("query_files", "spaces", "processors", "edge_refiners", "extensions"):
                    if list_key in merged and list_key in lang_cfg:
                        base_list = list(merged[list_key]) if isinstance(merged[list_key], (list, tuple)) else []
                        add_list = list(lang_cfg[list_key]) if isinstance(lang_cfg[list_key], (list, tuple)) else []
                        for elem in add_list:
                            if elem not in base_list:
                                base_list.append(elem)
                        merged[list_key] = base_list
                for dict_key in ("receiver_aliases", "symbol_folding"):
                    if dict_key in merged and dict_key in lang_cfg and isinstance(merged[dict_key], dict) and isinstance(lang_cfg[dict_key], dict):
                        sub_merged = dict(merged[dict_key])
                        sub_merged.update(lang_cfg[dict_key])
                        merged[dict_key] = sub_merged
                for k, v in lang_cfg.items():
                    if k not in ("query_files", "spaces", "processors", "edge_refiners", "extensions", "receiver_aliases", "symbol_folding") or k not in merged:
                        merged[k] = v
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

                if cfg.module_resolver:
                    try:
                        res_obj = self._instantiate_custom_parser(cfg.module_resolver, provider=provider)
                        if isinstance(res_obj, ModulePathResolver) or hasattr(res_obj, "resolve_import"):
                            self._module_resolvers[cfg.id] = res_obj  # type: ignore[assignment]
                        else:
                            err_msg = f"Module resolver '{cfg.module_resolver}' does not implement ModulePathResolver"
                            self.load_errors[f"{cfg.id}:{cfg.module_resolver}"] = err_msg
                            log_warn(err_msg, stream="stderr")
                    except Exception as exc:
                        err_msg = f"Failed to instantiate module_resolver '{cfg.module_resolver}': {exc}"
                        self.load_errors[f"{cfg.id}:{cfg.module_resolver}"] = err_msg
                        log_warn(err_msg, stream="stderr")

                refiner_instances: List[EdgeRefiner] = []
                for ref_entry in cfg.edge_refiners:
                    try:
                        ref_obj = self._instantiate_custom_parser(ref_entry, provider=provider)
                        if isinstance(ref_obj, EdgeRefiner) or hasattr(ref_obj, "refine_workspace_edges"):
                            refiner_instances.append(ref_obj)  # type: ignore[arg-type]
                        else:
                            err_msg = f"Edge refiner '{ref_entry}' does not implement EdgeRefiner"
                            self.load_errors[f"{cfg.id}:{ref_entry}"] = err_msg
                            log_warn(err_msg, stream="stderr")
                    except Exception as exc:
                        err_msg = f"Failed to instantiate edge_refiner '{ref_entry}': {exc}"
                        self.load_errors[f"{cfg.id}:{ref_entry}"] = err_msg
                        log_warn(err_msg, stream="stderr")
                if refiner_instances:
                    self._edge_refiners[cfg.id] = tuple(refiner_instances)

                proc_instances: List[SymbolProcessor] = []
                for proc_entry in cfg.processors:
                    try:
                        proc_obj = self._instantiate_custom_parser(proc_entry, provider=provider)
                        if isinstance(proc_obj, SymbolProcessor) or hasattr(proc_obj, "refine_file_graph"):
                            proc_instances.append(proc_obj)  # type: ignore[arg-type]
                        else:
                            err_msg = f"Processor '{proc_entry}' does not implement SymbolProcessor"
                            self.load_errors[f"{cfg.id}:{proc_entry}"] = err_msg
                            log_warn(err_msg, stream="stderr")
                    except Exception as exc:
                        err_msg = f"Failed to instantiate processor '{proc_entry}': {exc}"
                        self.load_errors[f"{cfg.id}:{proc_entry}"] = err_msg
                        log_warn(err_msg, stream="stderr")

                if cfg.mode == "tree_sitter":
                    driver = TreeSitterDriver(cfg, processors=tuple(proc_instances))
                    self._bind_configured_extensions(driver, cfg.extensions)
                    driver.SPACES = cfg.spaces
                    if driver._language is None or driver._parser is None:
                        err_msg = f"Failed to load tree-sitter grammar '{cfg.grammar}' or query '{cfg.query_file}'"
                        self.load_errors[cfg.id] = err_msg
                        fallback_parser: Optional[BaseParser] = None
                        if cfg.id == "python":
                            from .python_ast import PythonASTParser

                            fallback_parser = PythonASTParser()
                        elif cfg.id == "markdown":
                            from .markdown import MarkdownParser

                            fallback_parser = MarkdownParser()
                        if fallback_parser is not None:
                            self._bind_configured_extensions(fallback_parser, cfg.extensions)
                            fallback_parser.SPACES = cfg.spaces
                            if proc_instances:
                                fallback_parser._processors = tuple(proc_instances)  # type: ignore[attr-defined]
                            self.register_parser(fallback_parser, priority=100)
                            continue
                    self.register_parser(driver, priority=100)
                elif cfg.mode == "custom" and cfg.parser_entry:
                    try:
                        parser_inst = self._instantiate_custom_parser(cfg.parser_entry, provider=provider)
                        self._bind_configured_extensions(parser_inst, cfg.extensions)
                        parser_inst.SPACES = cfg.spaces
                        if proc_instances:
                            parser_inst._processors = tuple(proc_instances)  # type: ignore[attr-defined]
                        self.register_parser(parser_inst, priority=100)
                    except Exception as exc:
                        err_msg = f"Failed to instantiate custom parser '{cfg.parser_entry}': {exc}"
                        self.load_errors[cfg.id] = err_msg
                        log_warn(err_msg, stream="stderr")
            except Exception as exc:
                err_msg = f"Error loading language config '{lang_id}': {exc}"
                self.load_errors[str(lang_id)] = err_msg
                log_warn(err_msg, stream="stderr")

    def register_parser(self, parser: BaseParser, priority: int = 100) -> None:
        """Register a parser instance with priority (higher value takes precedence)."""
        self._parsers.append((priority, parser))
        self._parsers.sort(key=lambda x: x[0], reverse=True)

    @property
    def language_configs(self) -> Dict[str, LanguageConfig]:
        return dict(self._language_configs)

    @property
    def module_resolvers(self) -> Dict[str, ModulePathResolver]:
        return dict(self._module_resolvers)

    @property
    def edge_refiners(self) -> Dict[str, Tuple[EdgeRefiner, ...]]:
        return dict(self._edge_refiners)

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

    def _matches_configured_spaces(self, parser: BaseParser, file_path: Union[str, Path]) -> bool:
        """
        Check if `file_path` satisfies `parser.SPACES` via `space_manager.match_path`.
        When `parser.SPACES` is empty (default), returns True immediately without I/O.
        """
        spaces = getattr(parser, "SPACES", ())
        if not spaces:
            return True
        try:
            reg = self._space_manager
            if reg is None:
                from core.space import get_default_registry

                reg = get_default_registry()
            res = reg.match_path(file_path, list(spaces))
            return bool(res.matched)
        except Exception as exc:
            log_debug(f"Space match check failed for '{file_path}' against {spaces}: {exc}")
            return False

    def get_parser(self, file_path: Union[str, Path]) -> Optional[BaseParser]:
        """Return the highest-priority parser that supports `file_path` and its `spaces` scope, or None."""
        for _, parser in self._parsers:
            try:
                if parser.can_parse(file_path) and self._matches_configured_spaces(parser, file_path):
                    return parser
            except Exception as exc:
                log_warn(f"Error checking can_parse for {parser}: {exc}", stream="stderr")
        return None

    def get_applicable_parsers(self, file_path: Union[str, Path]) -> List[BaseParser]:
        """Return all registered parsers that match `file_path` extension and `spaces` scope."""
        matched: List[BaseParser] = []
        for _, parser in self._parsers:
            try:
                if parser.can_parse(file_path) and self._matches_configured_spaces(parser, file_path):
                    matched.append(parser)
            except Exception as exc:
                log_warn(f"Error checking can_parse for {parser}: {exc}", stream="stderr")
        return matched

    @staticmethod
    def _match_base_extract_cache(
        parser: BaseParser,
        file_path: str,
        content: str,
        space: Optional[str] = None,
    ) -> Optional[Tuple[Any, ...]]:
        cached = getattr(parser, "_last_base_extract_cache", None)
        if cached is None:
            return None
        norm_p = str(file_path).replace("\\", "/")
        if (
            cached[0] == norm_p
            and cached[1] == len(content)
            and (cached[2] == id(content) or cached[3] == content)
            and (space is None or cached[4] == space)
        ):
            return cached
        return None

    def parse_file(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """Parse `file_path` content and return extracted UnifiedSymbol list."""
        parser = self.get_parser(file_path)
        if parser is None:
            return []
        hit = self._match_base_extract_cache(parser, file_path, content, space=space)
        if hit is not None:
            return [dataclasses.replace(s, metadata=dict(s.metadata)) for s in hit[5]]
        try:
            return parser.parse(file_path=file_path, content=content, space=space)
        except Exception as exc:
            log_warn(f"Unexpected error during parse_file '{file_path}' in space '{space}': {exc}", stream="stderr")
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
        if symbols is None:
            hit = self._match_base_extract_cache(parser, file_path, content, space=space)
            if hit is not None:
                return list(hit[6])
        try:
            return parser.extract_call_sites(file_path=file_path, content=content, space=space, symbols=symbols)
        except TypeError:
            try:
                return parser.extract_call_sites(file_path=file_path, content=content, space=space)
            except Exception as exc:
                log_debug(f"Error extracting call sites from '{file_path}': {exc}")
                return []
        except Exception as exc:
            log_debug(f"Error extracting call sites from '{file_path}': {exc}")
            return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """Extract file-level import mappings from `file_path`."""
        parser = self.get_parser(file_path)
        if parser is None:
            return {}
        hit = self._match_base_extract_cache(parser, file_path, content, space=None)
        if hit is not None:
            return dict(hit[7])
        try:
            return parser.extract_imports(file_path=file_path, content=content)
        except Exception as exc:
            log_debug(f"Error extracting imports from '{file_path}': {exc}")
            return {}

    @staticmethod
    def _merge_symbol_nodes_commutative(
        node_a: SymbolNode,
        node_b: SymbolNode,
        id_remap: Optional[Dict[str, str]] = None,
    ) -> SymbolNode:
        """Commutatively merge two `SymbolNode` instances sharing the same `@name` physical span or ID."""
        merged_span = node_a.span.union(node_b.span)
        merged_kinds = frozenset(node_a.kinds | node_b.kinds)
        merged_parts = dict(node_a.parts)
        for slot, sp_val in node_b.parts.items():
            merged_parts[slot] = merged_parts[slot].union(sp_val) if slot in merged_parts else sp_val

        merged_facets = dict(node_a.facets)
        for fk, fv in node_b.facets.items():
            if fk not in merged_facets or not merged_facets[fk]:
                merged_facets[fk] = fv
            elif isinstance(merged_facets[fk], Mapping) and isinstance(fv, Mapping):
                combined_map = dict(merged_facets[fk])
                for mk, mv in fv.items():
                    if mk not in combined_map or str(mv) > str(combined_map[mk]):
                        combined_map[mk] = mv
                merged_facets[fk] = combined_map
            elif isinstance(merged_facets[fk], (set, frozenset, list, tuple)) and isinstance(fv, (set, frozenset, list, tuple)):
                merged_facets[fk] = tuple(sorted({str(x) for x in (*merged_facets[fk], *fv)}))
            elif str(fv) > str(merged_facets[fk]):
                merged_facets[fk] = fv

        child_by_key: Dict[Tuple[int, int, str], SymbolNode] = {}
        for ch in (*node_a.children, *node_b.children):
            nsp = ch.parts.get("name", ch.span)
            ckey = (nsp.start_byte, nsp.end_byte, ch.name)
            if ckey in child_by_key:
                child_by_key[ckey] = ParserRegistry._merge_symbol_nodes_commutative(
                    child_by_key[ckey],
                    ch,
                    id_remap=id_remap,
                )
            else:
                child_by_key[ckey] = ch
        merged_children = tuple(
            sorted(child_by_key.values(), key=lambda c: (c.span.start_byte, -c.span.end_byte, c.name))
        )
        merged_prov = tuple(sorted(set(node_a.provenance) | set(node_b.provenance), key=lambda p: p.sort_key()))
        chosen_id = max((node_a.id, node_b.id), key=lambda s: (len(s), s))
        if id_remap is not None:
            if node_a.id != chosen_id:
                id_remap[node_a.id] = chosen_id
            if node_b.id != chosen_id:
                id_remap[node_b.id] = chosen_id
        chosen_scope = max((node_a.scope_path, node_b.scope_path), key=lambda sp: (len(sp), sp))
        chosen_name = max((node_a.name, node_b.name), key=lambda s: (len(s), s))
        chosen_lang = max(
            (node_a.language, node_b.language),
            key=lambda s: (0 if s in ("", "unknown") else 1, len(s), s),
        )
        return SymbolNode(
            id=chosen_id,
            name=chosen_name,
            scope_path=chosen_scope,
            kinds=merged_kinds,
            language=chosen_lang,
            span=merged_span,
            parts=merged_parts,
            facets=merged_facets,
            children=merged_children,
            provenance=merged_prov,
        )

    def extract_file_graph(
        self,
        file_path: str,
        content: str,
        *,
        space: str = "unified",
    ) -> FileSymbolGraph:
        """
        Extract and commutatively merge `FileSymbolGraph` across all applicable parsers
        matching `file_path` extension and `core.space` scope.
        """
        norm_path = str(file_path).replace("\\", "/")
        content_bytes = (content or "").encode("utf-8", errors="replace")
        c_hash = compute_content_hash(content_bytes)
        applicable = self.get_applicable_parsers(file_path)
        if not applicable:
            return FileSymbolGraph(
                file_path=norm_path,
                content_hash=c_hash,
                language="unknown",
            )

        graphs: List[FileSymbolGraph] = []
        for parser in applicable:
            try:
                g = parser.extract_file_graph(file_path=norm_path, content=content, space=space)
                for proc in getattr(parser, "_processors", ()):
                    if not isinstance(parser, TreeSitterDriver):
                        g = proc.refine_file_graph(g, content_bytes)
                graphs.append(g)
            except Exception as exc:
                log_warn(f"Unexpected error during extract_file_graph '{file_path}': {exc}", stream="stderr")

        if not graphs:
            return FileSymbolGraph(
                file_path=norm_path,
                content_hash=c_hash,
                language="unknown",
            )
        if len(graphs) == 1:
            return graphs[0]

        id_remap: Dict[str, str] = {}
        root_by_key: Dict[Tuple[int, int, str], SymbolNode] = {}
        for g in graphs:
            for rnode in g.root_nodes:
                nsp = rnode.parts.get("name", rnode.span)
                rkey = (nsp.start_byte, nsp.end_byte, rnode.name)
                if rkey in root_by_key:
                    root_by_key[rkey] = self._merge_symbol_nodes_commutative(
                        root_by_key[rkey],
                        rnode,
                        id_remap=id_remap,
                    )
                else:
                    root_by_key[rkey] = rnode

        def _resolve_remapped_id(raw_id: str) -> str:
            curr = raw_id
            visited: Set[str] = set()
            while curr in id_remap and curr not in visited:
                visited.add(curr)
                curr = id_remap[curr]
            return curr

        merged_roots = tuple(
            sorted(root_by_key.values(), key=lambda r: (r.span.start_byte, -r.span.end_byte, r.name))
        )

        edge_by_key: Dict[Tuple[str, str, str, int, int], RelationEdge] = {}
        for g in graphs:
            for ed in g.outgoing_edges:
                remapped_src = _resolve_remapped_id(ed.source_id)
                remapped_targets = tuple(_resolve_remapped_id(tid) for tid in ed.resolved_target_ids)
                ekey = (
                    remapped_src,
                    ed.target_expr,
                    ed.edge_kind,
                    ed.span.start_byte,
                    ed.span.end_byte,
                )
                if ekey in edge_by_key:
                    prev_ed = edge_by_key[ekey]
                    comb_prov = tuple(
                        sorted(set(prev_ed.provenance) | set(ed.provenance), key=lambda p: p.sort_key())
                    )
                    comb_targets = tuple(sorted(set(prev_ed.resolved_target_ids) | set(remapped_targets)))
                    edge_by_key[ekey] = RelationEdge(
                        source_id=remapped_src,
                        target_expr=ed.target_expr,
                        edge_kind=ed.edge_kind,
                        span=prev_ed.span.union(ed.span),
                        resolution_status=prev_ed.resolution_status if prev_ed.resolution_status != "unresolved" else ed.resolution_status,
                        resolved_target_ids=comb_targets,
                        provenance=comb_prov,
                    )
                else:
                    edge_by_key[ekey] = RelationEdge(
                        source_id=remapped_src,
                        target_expr=ed.target_expr,
                        edge_kind=ed.edge_kind,
                        span=ed.span,
                        resolution_status=ed.resolution_status,
                        resolved_target_ids=remapped_targets,
                        provenance=ed.provenance,
                    )

        merged_edges = tuple(
            sorted(
                edge_by_key.values(),
                key=lambda e: (e.span.start_byte, e.edge_kind, e.source_id, e.target_expr),
            )
        )
        primary_lang = next((g.language for g in graphs if g.language and g.language != "unknown"), graphs[0].language)
        return FileSymbolGraph(
            file_path=norm_path,
            content_hash=c_hash,
            language=primary_lang,
            root_nodes=merged_roots,
            outgoing_edges=merged_edges,
        )

    def extract_all_file_artifacts(
        self,
        file_path: str,
        content: str,
        *,
        space: str = "unified",
    ) -> Tuple[FileSymbolGraph, List[UnifiedSymbol], List[SymbolCallSite], Dict[str, str]]:
        """
        Single-pass file extraction returning `(file_graph, symbols, call_sites, imports)`
        without re-reading or re-running parser CST traversal.
        """
        fg = self.extract_file_graph(file_path=file_path, content=content, space=space)
        symbols = self.parse_file(file_path=file_path, content=content, space=space)
        call_sites = self.extract_call_sites(file_path=file_path, content=content, space=space, symbols=symbols)
        imports = self.extract_imports(file_path=file_path, content=content)
        return fg, symbols, call_sites, imports
