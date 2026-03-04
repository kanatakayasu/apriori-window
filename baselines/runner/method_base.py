from __future__ import annotations

from abc import ABC, abstractmethod

from .types import MethodInput, MethodResult


class ComparativeMethod(ABC):
    """Abstract interface for all comparative methods."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def run(self, method_input: MethodInput) -> MethodResult:
        raise NotImplementedError
