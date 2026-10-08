"""Community slang dictionary (别称/黑话 → 正式名) for Apex legends & weapons.

The built-in dictionary lives in ``data/community_aliases.json``. Users can
override it from the app sidebar; the override is stored in
``workspace/community_aliases.override.json`` so the bundled file stays intact.
"""
from __future__ import annotations

import json
from pathlib import Path

from .paths import COMMUNITY_ALIASES_FILE

DATA_PATH = COMMUNITY_ALIASES_FILE
OVERRIDE_FILENAME = "community_aliases.override.json"


class AliasDictionary:
    def __init__(self, data: dict[str, Any]):
        self._data = data
        # canonical -> {"zh": str, "terms": {canonical, zh, *aliases}} for matching
        self._entries: list[dict[str, Any]] = []
        for group in ("legends", "weapons"):
            for canonical, info in (data.get(group) or {}).items():
                zh = str(info.get("zh") or "")
                aliases = [str(a) for a in info.get("aliases") or [] if str(a).strip()]
                terms = {canonical, zh, *aliases} - {""}
                self._entries.append({
                    "group": group, "canonical": canonical, "zh": zh,
                    "aliases": aliases, "terms": terms,
                    "terms_folded": {t.casefold() for t in terms},
                })

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def aliases_for_target(self, target: str) -> list[str]:
        """All known terms (canonical/zh/slang) for a change target.

        Matches when the target overlaps an entry's canonical or zh name in
        either direction (e.g. target '瓦尔基里' or 'Valkyrie' both hit, and
        '瓦尔基里喷射套件' also hits the Valkyrie entry).
        """
        folded = (target or "").strip().casefold()
        if not folded:
            return []
        matched: list[str] = []
        for entry in self._entries:
            keys = {entry["canonical"].casefold(), entry["zh"].casefold()} - {""}
            if any(folded in key or key in folded for key in keys):
                matched.extend(sorted(entry["terms"]))
        return matched

    def chinese_name(self, target: str) -> str:
        """Chinese display name for a target; the original when unknown.

        Community discussion is almost entirely in Chinese, so change targets
        are shown and matched under their Chinese names ('寻血猎犬', not
        'Bloodhound'). The English canonical name stays reachable as an alias.
        """
        folded = (target or "").strip().casefold()
        if not folded:
            return target or ""
        for entry in self._entries:
            keys = {entry["canonical"].casefold(), entry["zh"].casefold()} - {""}
            if any(folded in key or key in folded for key in keys):
                return entry["zh"] or entry["canonical"]
        return target or ""

    def prompt_table(self) -> str:
        """Compact one-line-per-entry table for prompt injection."""
        lines = []
        for entry in self._entries:
            names = "/".join(filter(None, [entry["zh"], entry["canonical"]]))
            slang = "、".join(entry["aliases"])
            if slang:
                lines.append(f"- {names}：{slang}")
        return "\n".join(lines)

    def as_payload(self) -> dict[str, list[str]]:
        """Formal name -> slang list, for the analysis request payload."""
        output: dict[str, list[str]] = {}
        for entry in self._entries:
            names = "/".join(filter(None, [entry["zh"], entry["canonical"]]))
            output[names] = entry["aliases"]
        return output


def load_aliases(workspace_dir: Path | None = None) -> AliasDictionary:
    """Load the dictionary, preferring the user's workspace override."""
    candidates = []
    if workspace_dir is not None:
        candidates.append(workspace_dir / OVERRIDE_FILENAME)
    candidates.append(DATA_PATH)
    for path in candidates:
        if path.exists():
            try:
                return AliasDictionary(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
    return AliasDictionary({})


def save_override(workspace_dir: Path, text: str) -> AliasDictionary:
    """Validate and persist a user-edited dictionary; returns the parsed dict."""
    data = json.loads(text)  # raises JSONDecodeError on bad input
    if not isinstance(data, dict) or not any(k in data for k in ("legends", "weapons")):
        raise ValueError("词典 JSON 至少需要包含 legends 或 weapons 其中一类。")
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / OVERRIDE_FILENAME).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return AliasDictionary(data)


def reset_override(workspace_dir: Path) -> None:
    (workspace_dir / OVERRIDE_FILENAME).unlink(missing_ok=True)


def default_text() -> str:
    return DATA_PATH.read_text(encoding="utf-8") if DATA_PATH.exists() else "{}"


def current_text(workspace_dir: Path) -> str:
    override = workspace_dir / OVERRIDE_FILENAME
    if override.exists():
        return override.read_text(encoding="utf-8")
    return default_text()
