"""
YS-Codebase VFS 抽象基底介面定義。
100% Python 標準庫，定義標準虛擬檔案系統原語契約與型態規範。
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Union, IO, Generator


class VFSBackend(ABC):
    """
    虛擬檔案系統後端抽象基類 (VFS Backend Abstract Base Class)。
    定義檔案與目錄之讀寫、查詢、建立、搬移、刪除與原子寫入介面。
    """

    @abstractmethod
    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """
        讀取指定路徑之純文字內容。

        :param path: 目標規範路徑
        :param encoding: 文字編碼格式 (預設 utf-8)
        :return: 檔案文字字串
        """
        ...

    @abstractmethod
    def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        atomic: bool = True,
    ) -> None:
        """
        寫入純文字內容至指定路徑。

        :param path: 目標規範路徑
        :param content: 寫入之文字內容
        :param encoding: 文字編碼格式 (預設 utf-8)
        :param atomic: 是否啟用原子寫入防護 (預設 True)
        """
        ...

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """
        讀取指定路徑之二進位位元組串。

        :param path: 目標規範路徑
        :return: 檔案二進位位元組串
        """
        ...

    @abstractmethod
    def write_bytes(
        self,
        path: str,
        data: bytes,
        atomic: bool = True,
    ) -> None:
        """
        寫入二進位位元組串至指定路徑。

        :param path: 目標規範路徑
        :param data: 寫入之二進位資料
        :param atomic: 是否啟用原子寫入防護 (預設 True)
        """
        ...

    @abstractmethod
    def read_json(self, path: str, encoding: str = "utf-8") -> Any:
        """
        讀取指定路徑之 JSON 檔案並反序列化為 Python 物件。

        :param path: 目標規範路徑
        :param encoding: 文字編碼格式 (預設 utf-8)
        :return: 解析後之 Python 資料結構 (Dict, List 等)
        """
        ...

    @abstractmethod
    def write_json(
        self,
        path: str,
        data: Any,
        indent: int = 2,
        encoding: str = "utf-8",
        atomic: bool = True,
    ) -> None:
        """
        序列化 Python 物件並以 JSON 格式寫入至指定路徑。

        :param path: 目標規範路徑
        :param data: 待序列化之 Python 資料結構
        :param indent: 縮排空格數 (預設 2)
        :param encoding: 文字編碼格式 (預設 utf-8)
        :param atomic: 是否啟用原子寫入防護 (預設 True)
        """
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """
        檢查目標路徑是否存在。

        :param path: 目標規範路徑
        :return: 是否存在
        """
        ...

    @abstractmethod
    def is_file(self, path: str) -> bool:
        """
        檢查目標路徑是否存在且為常規檔案。

        :param path: 目標規範路徑
        :return: 是否為常規檔案
        """
        ...

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """
        檢查目標路徑是否存在且為目錄。

        :param path: 目標規範路徑
        :return: 是否為目錄
        """
        ...

    @abstractmethod
    def listdir(self, path: str) -> List[str]:
        """
        列舉指定目錄下的子項目名稱清單。

        :param path: 目標目錄規範路徑
        :return: 子檔案與目錄名稱清單 (排序)
        """
        ...

    @abstractmethod
    def makedirs(self, path: str, exist_ok: bool = True) -> None:
        """
        遞迴建立目錄樹。

        :param path: 目標目錄規範路徑
        :param exist_ok: 若目錄已存在是否忽略錯誤 (預設 True)
        """
        ...

    @abstractmethod
    def remove(self, path: str, missing_ok: bool = True) -> None:
        """
        刪除指定檔案或目錄。若目標為目錄且非空，遞迴清除其內容。

        :param path: 目標規範路徑
        :param missing_ok: 若路徑不存在是否忽略錯誤 (預設 True)
        """
        ...

    @abstractmethod
    def rmtree(self, path: str, ignore_errors: bool = False) -> None:
        """
        遞迴刪除指定目錄樹。

        :param path: 目標目錄規範路徑
        :param ignore_errors: 是否忽略過程中的錯誤 (預設 False)
        """
        ...

    @abstractmethod
    def copy(self, src: str, dst: str) -> None:
        """
        複製檔案或目錄至目標路徑。若為目錄則遞迴複製。

        :param src: 來源路徑
        :param dst: 目的路徑
        """
        ...

    @abstractmethod
    def move(self, src: str, dst: str) -> None:
        """
        移動檔案或目錄至目標路徑。

        :param src: 來源路徑
        :param dst: 目的路徑
        """
        ...

    @abstractmethod
    @contextmanager
    def atomic_write(
        self,
        path: str,
        mode: str = "w",
        encoding: Optional[str] = "utf-8",
    ) -> Generator[IO, None, None]:
        """
        同目錄同分區原子寫入上下文管理器。
        在目標路徑同級目錄下建立暫存檔，寫入並 flush/sync 完成後，以 atomic replace 覆蓋。
        若過程中拋出異常，確保在退出時清除暫存檔且目標檔不受污染。

        :param path: 目標檔案規範路徑
        :param mode: 開啟模式 ('w' 或 'wb')
        :param encoding: 文字編碼 (若為二進位模式則為 None)
        :return: 可寫入之檔案物件 Generator
        """
        ...

    @abstractmethod
    def assert_safe_path(self, path: str, root: Optional[str] = None) -> str:
        """
        安全邊界防逃逸檢核。防禦路徑穿越 (Path Traversal / '..') 或越界符號連結。

        :param path: 待檢核路徑
        :param root: 授權邊界根目錄 (若為 None 則使用預設授權邊界或不限制)
        :return: 規範化後之安全絕對路徑
        :raises PermissionError: 當檢測到路徑穿越逃逸時拋出
        """
        ...
