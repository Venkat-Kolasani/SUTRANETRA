"""cypher_query rejects write keywords (courtesy regex, not RBAC)."""

import pytest

from src.agent.tools import reject_write_cypher


@pytest.mark.parametrize(
    "q",
    [
        "CREATE (n:X)",
        "  CREATE (n:X)",
        "\nMERGE (a:Alias)",
        "delete n",
        "SET n.x = 1",
        "DROP CONSTRAINT x",
        "  mixed MERGE (n)",
    ],
)
def test_cypher_query_rejects_writes(q: str):
    with pytest.raises(ValueError):
        reject_write_cypher(q)


def test_cypher_query_allows_match():
    reject_write_cypher("MATCH (a:Alias) RETURN a.name LIMIT 5")
    reject_write_cypher("  match (n) return n")
