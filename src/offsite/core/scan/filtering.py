"""Folder-based include/exclude rule parsing and matching for scanner traversal."""

from __future__ import annotations

from pathlib import Path


class FolderFilter:
    """Evaluate include/exclude folder rules for deterministic scan decisions."""

    def __init__(self, include_folders: list[Path] | None = None, exclude_folders: list[Path] | None = None) -> None:
        """Build a filter where the most specific rule wins and exclude wins ties."""
        self._includes = _normalize_folder_rules(include_folders or [])
        self._excludes = _normalize_folder_rules(exclude_folders or [])

    def should_include(self, path_rel: str) -> bool:
        """Return True if the path should be kept in scan output."""
        include_depth = _best_match_depth(path_rel, self._includes)
        exclude_depth = _best_match_depth(path_rel, self._excludes)

        if not self._includes:
            return exclude_depth is None

        if include_depth is None:
            return False

        if exclude_depth is None:
            return True

        if include_depth > exclude_depth:
            return True

        return False

    def should_descend(self, path_rel: str) -> bool:
        """Return True if traversal should continue into a directory path."""
        if not self._includes:
            return _best_match_depth(path_rel, self._excludes) is None

        if _is_ancestor_of_any_include(path_rel, self._includes):
            return True

        return self.should_include(path_rel)


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


def _best_match_depth(path_rel: str, rules: list[str]) -> int | None:
    normalized_path = _normalize_rel_path(path_rel)
    matched_depths = [rule.count("/") + 1 for rule in rules if _path_matches_rule(normalized_path, rule)]
    if not matched_depths:
        return None
    return max(matched_depths)


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
