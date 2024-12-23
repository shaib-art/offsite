"""Data model for a file system entity, used as a base for both file and folder entities."""
from dataclasses import dataclass

@dataclass
class FileSystemEntity:
    """
    Data model for a file system entity, used as a base for both file and folder entities.

    Attributes:
        name (str): The name of the file system entity.
        onsite_path (str): The onsite path of the file system entity.
    """
    name: str
    onsite_path: str

    def __str__(self):
        return f"{self.name} ({self.onsite_path})"
