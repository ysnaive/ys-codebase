"""
knowledge-db 多語言解析器基礎抽象類別 (BaseParser)
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Union

from ..schema import SymbolCallSite, UnifiedSymbol


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

    def extract_call_sites(
        self,
        file_path: str,
        content: str,
        space: str,
        symbols: Optional[List[UnifiedSymbol]] = None,
    ) -> List[SymbolCallSite]:
        """
        提取檔案文字內容中的符號調用點清單 (預設回傳空清單，特定語言解析器覆寫)。
        :param file_path: 正規化相對檔案路徑
        :param content: 檔案內容
        :param space: 所屬空間名稱
        :param symbols: 可選之預解析 UnifiedSymbol 清單，傳入時重用避免二次 AST 解析
        :return: List[SymbolCallSite]
        """
        return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """
        提取檔案文字內容中的檔頭 import 映射表 (預設回傳空字典，特定語言解析器覆寫)。
        :param file_path: 正規化相對檔案路徑
        :param content: 檔案內容
        :return: Dict[local_alias, full_target_module_path]
        """
        return {}

