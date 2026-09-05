"""
knowledge-db 多語言調用拓撲協議 (LanguageTopologyProtocol)
定義跨語言 AST 調用點與檔頭匯入提取標準抽象協議與註冊中心
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional

from .schema import SymbolCallSite

logger = logging.getLogger("knowledge-db.protocol")


class LanguageTopologyProtocol(ABC):
    """跨語言調用拓撲與匯入提取協議介面"""

    @abstractmethod
    def extract_call_sites(self, file_path: str, content: str, space: str) -> List[SymbolCallSite]:
        """
        自原始檔與 AST 中萃取調用點清單 (SymbolCallSite)
        必須填入 caller_member_name、context_prefix 與行號
        """
        pass

    @abstractmethod
    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        """
        自原始檔提取匯入別名與完整目標對照表 (e.g. {'np': 'numpy', 'bar': 'foo.bar'})
        """
        pass


class TreeSitterTopologyAdapter(LanguageTopologyProtocol):
    """
    包裝 TreeSitterDriver 之通用多語言拓撲適配器
    支援 Python, TypeScript, JavaScript, C++, C, C#, Markdown 等
    """

    def __init__(self, driver: Any):
        self.driver = driver

    def extract_call_sites(self, file_path: str, content: str, space: str) -> List[SymbolCallSite]:
        if hasattr(self.driver, "extract_call_sites"):
            return self.driver.extract_call_sites(file_path=file_path, content=content, space=space)
        return []

    def extract_imports(self, file_path: str, content: str) -> Dict[str, str]:
        if hasattr(self.driver, "extract_imports"):
            return self.driver.extract_imports(file_path=file_path, content=content)
        return {}


class TopologyProtocolRegistry:
    """語言調用拓撲協議註冊中心"""

    _adapters: Dict[str, LanguageTopologyProtocol] = {}

    @classmethod
    def register(cls, language: str, adapter: LanguageTopologyProtocol) -> None:
        """註冊特定語言之調用拓撲適配器"""
        cls._adapters[language.lower()] = adapter
        logger.debug(f"Registered topology adapter for language: {language}")

    @classmethod
    def get(cls, language: str) -> Optional[LanguageTopologyProtocol]:
        """取得指定語言之適配器"""
        return cls._adapters.get(language.lower())

    @classmethod
    def has(cls, language: str) -> bool:
        return language.lower() in cls._adapters

    @classmethod
    def clear(cls) -> None:
        cls._adapters.clear()
