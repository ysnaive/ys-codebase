"""
knowledge-db 解析器動態註冊表與調度中心 (ParserRegistry)
100% 透過 contributes.knowledge_db 語言宣告驅動，落實零特權架構與 Tree-sitter 通用 AST 解析。
"""

import importlib
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..schema import LanguageConfig, SymbolCallSite, UnifiedSymbol
from .base import BaseParser
from .treesitter import TreeSitterDriver

logger = logging.getLogger("knowledge-db.parsers.registry")


class ParserRegistry:
    """
    動態外掛解析器註冊中心
    透過 contributes.knowledge_db.languages 自動動態加載並分發相應解析驅動。
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
        """確保 project://、yscb.host:// 與語言提供者 module://<provider> 位於 sys.path 中。"""
        candidates: List[str] = []
        try:
            from core import uri
            for uri_key in ("project://", "yscb.host://"):
                try:
                    res = uri.resolve(uri_key, interactive=False)
                    if res and not str(res).startswith("!undefined"):
                        candidates.append(res)
                except Exception:
                    pass
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

        for cand in candidates:
            if not cand or not os.path.isdir(cand):
                continue
            abs_p = os.path.abspath(cand)
            norm_p = abs_p.replace("\\", "/")
            if "/source/" in norm_p or norm_p.endswith("/source"):
                continue
            if abs_p not in sys.path:
                sys.path.insert(0, abs_p)

    @staticmethod
    def _bind_configured_extensions(parser_inst: BaseParser, extensions: Tuple[str, ...]) -> None:
        """將 LanguageConfig 宣告之副檔名動態合併至解析器實例（不污染類別共享集合）。"""
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
        """支援 module.path:ClassName、檔案路徑:ClassName 與語意 URI (project://.../file.py:ClassName) 實例化。"""
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
            if os.path.isdir(parent_dir) and parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
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
        """讀取 contributes 中的 languages 配置並動態掛載解析器 (Zero-Privilege Dogfooding)"""
        self.load_errors.clear()
        languages_dict: Dict[str, Any] = {}

        # 1. 優先使用傳入之自訂 contributes 資料 (測試或隔離環境)
        if contributes_data and isinstance(contributes_data, dict):
            languages_dict = contributes_data.get("languages", {})

        # 2. 嘗試透過 core SDK 讀取聚合的 contributes
        if not languages_dict:
            try:
                from core import contributes

                data = contributes.get("knowledge-db")
                if isinstance(data, dict):
                    languages_dict = data.get("languages", {})
            except Exception:
                pass

        # 3. 模組內建宣告之安全降級載入 (讀取自身 contributes/knowledge-db.json)
        if not languages_dict:
            try:
                mod_contrib = (
                    Path(__file__).resolve().parent.parent.parent / "contributes" / "knowledge-db.json"
                )
                if mod_contrib.exists():
                    with open(mod_contrib, "r", encoding="utf-8", errors="replace") as f:
                        m_data = json.load(f)
                    if isinstance(m_data, dict):
                        languages_dict = m_data.get("languages", {})
            except Exception as e:
                logger.warning(f"ParserRegistry: Failed to load contributes/knowledge-db.json: {e}")

        # 4. 註冊所有宣告之語言
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
                    if driver._language is None or driver._parser is None:
                        err_msg = f"Failed to load tree-sitter grammar '{cfg.grammar}' or query '{cfg.query_file}'"
                        self.load_errors[cfg.id] = err_msg
                    self.register_parser(driver, priority=100)
                elif cfg.mode == "custom" and cfg.parser_entry:
                    try:
                        parser_inst = self._instantiate_custom_parser(cfg.parser_entry, provider=provider)
                        self._bind_configured_extensions(parser_inst, cfg.extensions)
                        self.register_parser(parser_inst, priority=100)
                    except Exception as e:
                        err_msg = f"Failed to instantiate custom parser '{cfg.parser_entry}': {e}"
                        self.load_errors[cfg.id] = err_msg
                        logger.warning(err_msg)
            except Exception as e:
                err_msg = f"Error loading language config '{lang_id}': {e}"
                self.load_errors[str(lang_id)] = err_msg
                logger.warning(err_msg)

    def register_parser(self, parser: BaseParser, priority: int = 100) -> None:
        """
        註冊自訂解析器實例。
        :param parser: BaseParser 子類實例
        :param priority: 優先級權重 (愈大愈優先匹配，預設 100)
        """
        self._parsers.append((priority, parser))
        self._parsers.sort(key=lambda x: x[0], reverse=True)

    def get_supported_extensions(self) -> Set[str]:
        """動態彙整當前註冊的所有語言所宣告之副檔名集合 (全小寫，含前導點號)。"""
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
        """
        依副檔名/特徵尋找相符且優先級最高之解析器。
        若無匹配解析器回傳 None (EC-02)。
        """
        for _, parser in self._parsers:
            try:
                if parser.can_parse(file_path):
                    return parser
            except Exception as e:
                logger.warning(f"Error checking can_parse for {parser}: {e}")
        return None

    def parse_file(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """
        調度相符解析器執行符號提取；若無匹配解析器回傳空清單 []。
        """
        parser = self.get_parser(file_path)
        if parser is None:
            logger.debug(f"No parser available for '{file_path}', skipping.")
            return []

        try:
            return parser.parse(file_path=file_path, content=content, space=space)
        except Exception as e:
            logger.warning(f"Unexpected error during parse_file '{file_path}' in space '{space}': {e}")
            return []

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str = "unified",
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        """
        調度相符解析器提取符號調用點；若無匹配解析器回傳空清單 []。
        支援傳入預解析之 symbols 實例，避免 TreeSitterDriver 內部重複執行 parse()。
        """
        parser = self.get_parser(file_path)
        if parser is None:
            return []
        try:
            return parser.extract_call_sites(file_path=file_path, content=content, space=space, symbols=symbols)
        except TypeError:
            try:
                return parser.extract_call_sites(file_path=file_path, content=content, space=space)
            except Exception as e:
                logger.debug(f"Error extracting call sites from '{file_path}': {e}")
                return []
        except Exception as e:
            logger.debug(f"Error extracting call sites from '{file_path}': {e}")
            return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """
        調度相符解析器提取檔頭 Import 映射表；若無匹配解析器回傳空字典 {}。
        """
        parser = self.get_parser(file_path)
        if parser is None:
            return {}
        try:
            return parser.extract_imports(file_path=file_path, content=content)
        except Exception as e:
            logger.debug(f"Error extracting imports from '{file_path}': {e}")
            return {}
