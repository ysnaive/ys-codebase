"""
knowledge-db 解析器動態註冊表與調度中心 (ParserRegistry)
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

from ..schema import UnifiedSymbol
from .base import BaseParser
from .cpp_parser import CppParser
from .csharp_parser import CSharpParser
from .markdown_parser import MarkdownParser
from .python_parser import PythonParser

logger = logging.getLogger("knowledge-db.parsers.registry")


class ParserRegistry:
    """動態外掛解析器註冊中心"""

    def __init__(self, register_defaults: bool = True):
        self._parsers: List[Tuple[int, BaseParser]] = []
        if register_defaults:
            self.register_parser(PythonParser(), priority=100)
            self.register_parser(MarkdownParser(), priority=100)
            self.register_parser(CppParser(), priority=100)
            self.register_parser(CSharpParser(), priority=100)

    def register_parser(self, parser: BaseParser, priority: int = 100) -> None:
        """
        註冊自訂解析器實例。
        :param parser: BaseParser 子類實例
        :param priority: 優先級權重 (愈大愈優先匹配，預設 100)
        """
        self._parsers.append((priority, parser))
        # 依優先級降序排序
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
