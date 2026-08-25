"""数据库连接接口。"""

from abc import ABC, abstractmethod
from typing import Any


class DatabaseBase(ABC):
    """只定义数据库对象必须提供的连接能力。

    查询、分页和写入统一由 repository 层负责，避免数据库对象与 repository
    同时维护两套数据访问 API。
    """

    @abstractmethod
    def connect(self) -> Any:
        raise NotImplementedError
