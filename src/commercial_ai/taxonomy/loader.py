"""Taxonomy loader: reads JSON files under a taxonomy dir and exposes lookups.

Used by the normalizer (synonym resolution) and the validator (membership checks).
Scrapers may NOT invent category names: every category must exist in the taxonomy.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


class TaxonomyLoader:
    def __init__(self, taxonomy_dir: str | Path):
        self.dir = Path(taxonomy_dir)
        if not self.dir.exists():
            raise FileNotFoundError(f"taxonomy dir not found: {self.dir}")
        self._cache: dict[str, dict[str, Any]] = {}

    def _load(self, name: str) -> dict[str, Any]:
        if name not in self._cache:
            p = self.dir / f"{name}.json"
            if not p.exists():
                raise FileNotFoundError(f"taxonomy file not found: {p}")
            self._cache[name] = json.loads(p.read_text(encoding="utf-8"))
        return self._cache[name]

    # -- categories --------------------------------------------------------
    @property
    def categories(self) -> list[str]:
        return list(self._load("categories")["categories"])

    def is_valid_category(self, category: str) -> bool:
        return category in self.categories

    # -- subcategories -----------------------------------------------------
    def subcategories(self, category: str) -> list[str]:
        subs = self._load("subcategories")["subcategories"]
        return list(subs.get(category, []))

    def is_valid_subcategory(self, category: str, subcategory: str | None) -> bool:
        if not subcategory:
            return True  # subcategory optional
        return subcategory in self.subcategories(category)

    # -- use cases ---------------------------------------------------------
    @property
    def use_cases(self) -> list[str]:
        return list(self._load("use_cases")["use_cases"])

    def is_valid_use_case(self, uc: str) -> bool:
        return uc in self.use_cases

    # -- features ----------------------------------------------------------
    @property
    def features(self) -> list[str]:
        return list(self._load("features")["features"])

    def is_valid_feature(self, f: str) -> bool:
        return f in self.features

    # -- connectivity ------------------------------------------------------
    @property
    def connectivity_types(self) -> list[str]:
        return list(self._load("connectivity_types")["connectivity_types"])

    @property
    def connectivity_aliases(self) -> dict[str, str]:
        return dict(self._load("connectivity_types").get("aliases", {}))

    def resolve_connectivity(self, raw: str) -> str | None:
        k = raw.strip().lower()
        if k in self.connectivity_types:
            return k
        return self.connectivity_aliases.get(k)

    # -- units -------------------------------------------------------------
    @property
    def units(self) -> dict[str, str]:
        return dict(self._load("units")["units"])

    def resolve_unit(self, raw: str) -> str | None:
        return self.units.get(raw.strip().lower())

    # -- spec names --------------------------------------------------------
    def spec_fields(self, category: str) -> dict[str, list[str]]:
        sn = self._load("spec_names")["spec_names"]
        return dict(sn.get(category, {}))

    @lru_cache(maxsize=4096)  # type: ignore[misc]
    def resolve_spec_field(self, category: str, raw_name: str) -> str | None:
        """Map a raw spec name to a canonical field, or None if unknown.

        Unknown specs are NOT errors: the normalizer preserves them in
        ``specifications_extra``.
        """
        if not raw_name:
            return None
        key = raw_name.strip().lower()
        for canonical, synonyms in self.spec_fields(category).items():
            for syn in synonyms:
                if key == syn.strip().lower():
                    return canonical
        return None

    # -- currencies (convenience, also in config) --------------------------
    @property
    def allowed_currencies(self) -> list[str]:
        # Not a taxonomy file; currencies live in config. Kept here for the
        # validator's convenience; default set below.
        return ["COP", "USD", "EUR"]
