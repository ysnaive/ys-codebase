"""
knowledge-db 多語言解析器基礎抽象類別 (BaseParser)
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union

from ..schema import UnifiedSymbol


class BaseParser(ABC):
    """多語言符號解析器抽象介面"""

    @abstractmethod
    def can_parse(self, file_path: Union[str, Path]) -> bool:
        """
        判斷此解析器是否支援解析該檔案。
        :param file_path: 檔案路徑或檔名
        :return: 若支援回傳 True，否則 False
        """

    @abstractmethod
    def parse(self, file_path: str, content: str, space: str) -> List[UnifiedSymbol]:
        """
        解析檔案文字內容並產出 UnifiedSymbol 符號清單。
        :param file_path: 相對於來源根目錄之正規化路徑 (forward slash)
        :param content: 檔案文字內容
        :param space: 所屬空間識別名稱
        :return: 提取之 UnifiedSymbol 清單
        """
