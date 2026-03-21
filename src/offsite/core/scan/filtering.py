"""Folder-based include/exclude rule parsing and matching for scanner traversal."""

from __future__ import annotations

from pathlib import Path


class FolderFilter:
    """Evaluate include/exclude folder rules for deterministic scan decisions."""

    def __init__(self, include_folders: list[Path] | None = None, exclude_folders: list[Path] | None = None) -> None:
        """Build a filter where exclude rules take precedence over include rules."""
        self._includes = _normalize_folder_rules(include_folders or [])
        self._excludes = _normalize_folder_rules(exclude_folders or [])

    def should_include(self, path_rel: str) -> bool:
        """Return True if the path should be kept in scan output."""
        if _matches_any_rule(path_rel, self._excludes):
            return False

        if not self._includes:
            return True

        return _matches_any_rule(path_rel, self._includes)

    def should_descend(self, path_rel: str) -> bool:
        """Return True if traversal should continue into a directory path."""
        if _matches_any_rule(path_rel, self._excludes):
            return False

        if not self._includes:
            return True

        if _matches_any_rule(path_rel, self._includes):
            return True

        return _is_ancestor_of_any_include(path_rel, self._includes)


def _normalize_folder_rules(rules: list[Path]) -> list[str]:
    normalized: list[str] = []
    for rule in rules:
        value = rule.as_posix().strip("/")
        if not value or value == ".":
            continue
        normalized.append(value)
    return normalized


def _matches_any_rule(path_rel: str, rules: list[str]) -> bool:
    normalized_path = _normalize_rel_path(path_rel)
    return any(_path_matches_rule(normalized_path, rule) for rule in rules)


def _is_ancestor_of_any_include(path_rel: str, include_rules: list[str]) -> bool:
    normalized_path = _normalize_rel_path(path_rel)
    if normalized_path == ".":
        return True

    prefix = f"{normalized_path}/"
    return any(rule.startswith(prefix) for rule in include_rules)


def _path_matches_rule(path_rel: str, rule: str) -> bool:
    return path_rel == rule or path_rel.startswith(f"{rule}/")


def _normalize_rel_path(path_rel: str) -> str:
    if path_rel in {"", "."}:
        return "."
    return path_rel.strip("/")
