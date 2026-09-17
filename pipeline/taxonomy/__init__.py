"""Curated taxonomies: roles, regions and companies.

The YAML files in this directory are the single source of truth for what the pipeline
collects. Import from this package rather than from its modules.
"""

from pipeline.taxonomy.companies import BOARD_TYPES, Company, load_companies
from pipeline.taxonomy.regions import (
    OTHER_REGION,
    AdzunaMarket,
    Country,
    adzuna_markets,
    get_country,
    jsearch_countries,
    load_countries,
    load_regions,
    region_for_country,
    resolve_country,
)
from pipeline.taxonomy.roles import (
    Role,
    get_role,
    is_relevant_title,
    load_roles,
    match_role,
    normalize_title,
)

__all__ = [
    "BOARD_TYPES",
    "OTHER_REGION",
    "AdzunaMarket",
    "Company",
    "Country",
    "Role",
    "adzuna_markets",
    "get_country",
    "get_role",
    "is_relevant_title",
    "jsearch_countries",
    "load_companies",
    "load_countries",
    "load_regions",
    "load_roles",
    "match_role",
    "normalize_title",
    "region_for_country",
    "resolve_country",
]
