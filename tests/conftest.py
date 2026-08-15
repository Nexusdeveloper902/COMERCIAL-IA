"""Test shared fixtures and path setup."""
import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

TAXONOMY_DIR = Path(__file__).resolve().parent.parent / "data" / "taxonomy"


@pytest.fixture(scope="session")
def taxonomy_dir():
    return TAXONOMY_DIR


@pytest.fixture(scope="session")
def taxonomy(taxonomy_dir):
    from commercial_ai.taxonomy import TaxonomyLoader
    return TaxonomyLoader(taxonomy_dir)
