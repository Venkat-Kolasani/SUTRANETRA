"""networkx components and centrality on a synthetic scored graph."""

import networkx as nx

from src.graph.build import centralities, cluster_components, node_key


class _R(dict):
    def __getitem__(self, k):
        return dict.get(self, k)


def test_known_component_structure():
    g = nx.Graph()
    g.add_edge("silkroad1:A", "silkroad2:A", weight=0.9)
    g.add_edge("silkroad2:A", "thehub:A", weight=0.9)
    g.add_node("nucleus:loner")
    comps = {frozenset(c) for c in cluster_components(g)}
    assert frozenset({"silkroad1:A", "silkroad2:A", "thehub:A"}) in comps
    assert frozenset({"nucleus:loner"}) in comps
    assert node_key("silkroad1", "A") != node_key("silkroad2", "A")


def test_centrality_differs_in_a_path():
    g = nx.Graph()
    g.add_edge("m1:a", "m2:bridge", weight=0.9)
    g.add_edge("m2:bridge", "m3:c", weight=0.9)
    _deg, bet = centralities(g)
    assert bet["m2:bridge"] > bet["m1:a"]
    assert bet["m2:bridge"] > bet["m3:c"]
    assert len({round(v, 6) for v in bet.values()}) > 1
