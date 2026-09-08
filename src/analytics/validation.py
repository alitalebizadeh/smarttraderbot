from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class DataSplit:
    training: tuple[T, ...]
    validation: tuple[T, ...]
    testing: tuple[T, ...]


def chronological_split(items: Sequence[T]) -> DataSplit[T]:
    """Split ordered observations into 60% train, 20% validation, 20% test."""
    if len(items) < 5:
        raise ValueError("at least five ordered observations are required")
    train_end = int(len(items) * 0.6)
    validation_end = int(len(items) * 0.8)
    return DataSplit(tuple(items[:train_end]), tuple(items[train_end:validation_end]), tuple(items[validation_end:]))
