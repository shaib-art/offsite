"""Dataclass for a folder entity."""
from dataclasses import dataclass

from .file_entity import FileEntity
from .file_system_entity import FileSystemEntity


@dataclass
class FolderEntity(FileSystemEntity):
    """
    Dataclass for a folder entity.

    Attributes:
        name (str): The name of the folder entity.
        onsite_path (str): The onsite path of the folder entity.
        files (list[FileEntity]): The offsite path of the folder entity.
    """
    files: list[FileEntity]
    folders: list['FolderEntity']

    def __str__(self):
        return f"{self.name} ({self.onsite_path}, files: {len(self.files)}, folders: {len(self.folders)})"
