from abc import ABC, abstractmethod
from typing import Any


class Model(ABC):
    @abstractmethod
    async def complete_stream(self, messages: list[Any]) -> Any:
        pass
