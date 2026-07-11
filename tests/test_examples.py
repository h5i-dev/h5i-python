import ast
from pathlib import Path

import pytest


EXAMPLES = Path(__file__).parents[1] / "examples"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.py")), ids=lambda p: p.name)
def test_examples_are_valid_python(path: Path):
    ast.parse(path.read_text(), filename=str(path))


@pytest.mark.parametrize("name", ["arena_score.py", "ensemble_score.py"])
def test_resident_examples_do_not_preflight_live_sessions(name: str):
    tree = ast.parse((EXAMPLES / name).read_text())
    live_checks = [
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "preflight"
        and any(keyword.arg == "live" for keyword in call.keywords)
    ]

    assert not live_checks, (
        'launcher="resident" starts sessions lazily on the first turn; '
        "preflight(live=...) fails before that turn can start them"
    )
