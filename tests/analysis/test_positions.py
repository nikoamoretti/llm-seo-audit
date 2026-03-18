from pathlib import Path

from src.analysis.positions import detect_position


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "responses"


def test_positions_detect_numbered_list_order():
    response = (FIXTURE_ROOT / "listicle_format.md").read_text()

    result = detect_position(response, ["Laveta Coffee"])

    assert result.position == 2
    assert result.total_items >= 3


def test_positions_fall_back_for_prose_mentions():
    response = (FIXTURE_ROOT / "prose_format.md").read_text()

    result = detect_position(response, ["Parker Law Group"])

    assert result.position == 1
    assert result.total_items == 1
