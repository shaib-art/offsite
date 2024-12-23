"""Dataclass for an offsite location."""
from dataclasses import dataclass


@dataclass
class OffsiteLocation:
    """
    Dataclass for an offsite location.

    Attributes:
        label (str): The name of the offsite location.
        path (str): The path of the offsite location.
    """
    label: str
    path: str

    def __str__(self):
        return f"{self.label}::{self.path}"
