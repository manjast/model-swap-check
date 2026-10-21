"""Intent scope and slices from `config/intent-groups.yaml` (spec §2.2, §2.4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUPS_PATH = REPO_ROOT / "config" / "intent-groups.yaml"
OUT_OF_SCOPE = "out_of_scope"


def catalog_order(ids: list[str]) -> list[str]:
    """Catalog order used everywhere (spec §3.1); `out_of_scope` is appended by callers."""
    return sorted(ids, key=lambda s: (s.casefold(), s))


@dataclass(frozen=True)
class IntentGroups:
    in_scope_groups: dict[str, list[str]]
    out_of_scope: list[str]

    @property
    def slices(self) -> list[str]:
        """Slice names in file order, `out_of_scope` last."""
        return [*self.in_scope_groups, OUT_OF_SCOPE]

    @property
    def in_scope(self) -> list[str]:
        """The in-scope intents in catalog order."""
        return catalog_order([i for group in self.in_scope_groups.values() for i in group])

    def slice_of(self, intent: str) -> str:
        for name, intents in self.in_scope_groups.items():
            if intent in intents:
                return name
        if intent in self.out_of_scope:
            return OUT_OF_SCOPE
        raise KeyError(f"intent not in config/intent-groups.yaml: {intent!r}")


def load_groups(path: Path = GROUPS_PATH) -> IntentGroups:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    groups = {str(k): [str(i) for i in v] for k, v in raw["in_scope_groups"].items()}
    return IntentGroups(groups, [str(i) for i in raw["out_of_scope"]])
