"""Hexagonal layering rules: dependencies point inward only.

``entrypoints -> adapters -> application -> domain``. ``config`` is read by the
composition root only, so adapters and the core never see settings objects.
"""

from typing import TypedDict


class LayerRuleCase(TypedDict):
    id: str
    layer: str
    forbidden_internal: list[str]
    forbidden_external: list[str]


FRAMEWORKS = [
    "fastapi",
    "starlette",
    "sqlalchemy",
    "asyncpg",
    "faststream",
    "aio_pika",
    "httpx",
]

LAYER_RULE_CASES: list[LayerRuleCase] = [
    {
        "id": "domain-is-pure-python",
        "layer": "domain",
        "forbidden_internal": ["application", "adapters", "entrypoints", "config"],
        "forbidden_external": [*FRAMEWORKS, "pydantic", "pydantic_settings", "alembic"],
    },
    {
        "id": "application-depends-only-on-domain",
        "layer": "application",
        "forbidden_internal": ["adapters", "entrypoints", "config"],
        "forbidden_external": [*FRAMEWORKS, "pydantic", "pydantic_settings", "alembic"],
    },
    {
        "id": "adapters-never-reach-into-entrypoints-or-config",
        "layer": "adapters",
        "forbidden_internal": ["entrypoints", "config"],
        "forbidden_external": ["fastapi", "pydantic_settings"],
    },
]
