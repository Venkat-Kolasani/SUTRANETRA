"""S_embed is topic proximity; S_char is style — they must be able to diverge."""

from src.stylometry.char_ngram import fit_char_tfidf, pairwise_s_char
from src.stylometry.embed import embed_posts, load_model, mean_pool, s_embed
import numpy as np

# Same product talk, opposite writing habits (the first-draft failure mode).
CASUAL = (
    "lol the cannabis / bud nugs r fire, 5 grams shipping 2day asap wtf "
    "vendor order cheap yo xoxo hahaha??!! umm yeah dude "
) * 8
FORMAL = (
    "The cannabis bud offered by this vendor is five grams. Shipping of the "
    "order proceeds after payment. Product quality remains consistent. "
) * 8


def test_topic_pair_high_embed_low_char():
    vec = fit_char_tfidf([CASUAL, FORMAL], min_df=1, max_features=8000)[1]
    style = float(pairwise_s_char(vec, np.array([0]), np.array([1]))[0])
    model = load_model()
    topic = s_embed(
        mean_pool(embed_posts(model, [CASUAL])),
        mean_pool(embed_posts(model, [FORMAL])),
    )
    assert topic > 0.45, topic
    assert topic > style + 0.15, (topic, style)
