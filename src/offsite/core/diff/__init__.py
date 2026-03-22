"""Diff generation and deletion safety logic."""

from offsite.core.diff.deleted import is_deletion_candidate
from offsite.core.diff.differ import DiffEntry, Differ

__all__ = ["DiffEntry", "Differ", "is_deletion_candidate"]