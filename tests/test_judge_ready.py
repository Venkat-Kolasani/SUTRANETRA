from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_judge_ui_uses_professional_copy_and_groq_default():
    html = (ROOT / "src/api/static/index.html").read_text(encoding="utf-8").lower()
    assert "templates and structured views always work" not in html
    assert "neo4j / llm are optional" not in html
    with (ROOT / "config.yaml").open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    llm = cfg["profiles"]["dev"]["llm"]
    assert llm["enabled"] is True
    assert llm["provider"] == "groq"

