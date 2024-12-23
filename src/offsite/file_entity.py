"""Dataclass for a file entity."""
from dataclasses import dataclass
from datetime import datetime

from .file_system_entity import FileSystemEntity
from .offsite_location import OffsiteLocation


@dataclass
class FileEntity(FileSystemEntity):
    """
    Dataclass for a file entity.

    Attributes:
        name (str): The name of the file entity.
        onsite_path (str): The onsite path of the file entity.
        offsite_location (OffsiteLocation): The offsite path of the file entity.
        size (int): The size of the file entity.
        modified_at (datetime): The last modified date of the file entity.
        hash (str): The hash of the file entity.
    """
    offsite_location: OffsiteLocation
    size: int
    modified_at: datetime
    hash: str

    def __str__(self):
        return f"{self.name} ({self.onsite_path} -> {self.offsite_location})[{self.size} bytes, {self.modified_at}, {self.hash}]"
