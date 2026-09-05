"""
knowledge-db 解析器動態註冊表與調度中心 (ParserRegistry / LanguageRegistry)
100% 透過 contributes.knowledge_db 語言宣告驅動，落實零特權架構與 Tree-sitter 通用 AST 解析。
"""

import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..schema import LanguageConfig, SymbolCallSite, UnifiedSymbol
from .base import BaseParser
from .treesitter import TreeSitterDriver

logger = logging.getLogger("knowledge-db.parsers.registry")


class PythonParser(TreeSitterDriver):
    """Python AST 語意解析器 (基於 TreeSitterDriver)"""

    def __init__(self, config: Optional[LanguageConfig] = None):
        if config is None:
            config = LanguageConfig(
                id="python",
                name="Python",
                extensions=(".py", ".pyi"),
                mode="tree_sitter",
                grammar="tree_sitter_python",
                query_file="assets/queries/python.scm",
            )
        super().__init__(config)


class MarkdownParser(TreeSitterDriver):
    """Markdown 標題、表格與區塊文檔語意解析器 (基於 TreeSitterDriver)"""

    def __init__(self, config: Optional[LanguageConfig] = None):
        if config is None:
            config = LanguageConfig(
                id="markdown",
                name="Markdown",
                extensions=(".md", ".markdown"),
                mode="tree_sitter",
                grammar="tree_sitter_markdown",
                query_file="assets/queries/markdown.scm",
            )
        super().__init__(config)


class CppParser(TreeSitterDriver):
    """C/C++ 語意解析器 (基於 TreeSitterDriver)"""

    def __init__(self, config: Optional[LanguageConfig] = None):
        if config is None:
            config = LanguageConfig(
                id="cpp",
                name="C++",
                extensions=(".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh", ".c", ".h"),
                mode="tree_sitter",
                grammar="tree_sitter_cpp",
                query_file="assets/queries/cpp.scm",
            )
        super().__init__(config)


class CSharpParser(TreeSitterDriver):
    """C# 語意解析器 (基於 TreeSitterDriver)"""

    def __init__(self, config: Optional[LanguageConfig] = None):
        if config is None:
            config = LanguageConfig(
                id="c_sharp",
                name="C#",
                extensions=(".cs",),
                mode="tree_sitter",
                grammar="tree_sitter_c_sharp",
                query_file="assets/queries/c_sharp.scm",
            )
        super().__init__(config)


class JsTsParser(TreeSitterDriver):
    """JavaScript / TypeScript 語意解析器 (基於 TreeSitterDriver)"""

    def __init__(self, config: Optional[LanguageConfig] = None):
        if config is None:
            config = LanguageConfig(
                id="typescript",
                name="TypeScript",
                extensions=(".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
                mode="tree_sitter",
                grammar="tree_sitter_typescript:language_typescript",
                query_file="assets/queries/typescript.scm",
            )
        super().__init__(config)


class ParserRegistry:
    """
    動態外掛解析器註冊中心 (LanguageRegistry)
    透過 contributes.knowledge_db.languages 自動動態加載並分發相應解析驅動。
    """

    def __init__(
        self,
        register_defaults: bool = True,
        contributes_data: Optional[Dict[str, Any]] = None,
    ):
        self._parsers: List[Tuple[int, BaseParser]] = []
        self._language_configs: Dict[str, LanguageConfig] = {}

        if register_defaults:
            self._load_from_contributes(contributes_data=contributes_data)

    def _load_from_contributes(self, contributes_data: Optional[Dict[str, Any]] = None) -> None:
        """讀取 contributes 中的 languages 配置並動態掛載解析器 (Zero-Privilege Dogfooding)"""
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
                if "id" not in raw_cfg:
                    raw_cfg["id"] = lang_id
                cfg = LanguageConfig.from_dict(raw_cfg)
                self._language_configs[cfg.id] = cfg

                if cfg.mode == "tree_sitter":
                    # 依語言類別物化特定類別實例以維持向後相容性
                    if cfg.id == "python":
                        parser = PythonParser(cfg)
                    elif cfg.id == "markdown":
                        parser = MarkdownParser(cfg)
                    elif cfg.id in ("cpp", "c"):
                        parser = CppParser(cfg)
                    elif cfg.id == "c_sharp":
                        parser = CSharpParser(cfg)
                    elif cfg.id in ("javascript", "typescript"):
                        parser = JsTsParser(cfg)
                    else:
                        parser = TreeSitterDriver(cfg)
                    self.register_parser(parser, priority=100)

                elif cfg.mode == "custom" and cfg.parser_entry:
                    try:
                        entry_str = cfg.parser_entry
                        if ":" in entry_str:
                            mod_name, cls_name = entry_str.split(":", 1)
                        else:
                            mod_name, cls_name = entry_str.rsplit(".", 1)
                        mod = importlib.import_module(mod_name)
                        parser_cls = getattr(mod, cls_name)
                        parser_inst = parser_cls()
                        self.register_parser(parser_inst, priority=100)
                    except Exception as e:
                        logger.warning(f"Failed to instantiate custom parser '{cfg.parser_entry}': {e}")
            except Exception as e:
                logger.warning(f"Error loading language config '{lang_id}': {e}")

    def register_parser(self, parser: BaseParser, priority: int = 100) -> None:
        """
        註冊自訂解析器實例。
        :param parser: BaseParser 子類實例
        :param priority: 優先級權重 (愈大愈優先匹配，預設 100)
        """
        self._parsers.append((priority, parser))
        self._parsers.sort(key=lambda x: x[0], reverse=True)

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


LanguageRegistry = ParserRegistry
