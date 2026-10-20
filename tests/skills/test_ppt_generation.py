"""PPT generation handles every image mode Pillow can open."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_loader import load  # noqa: E402

Image = pytest.importorskip("PIL.Image")
pytest.importorskip("pptx")

ppt = load("ppt-generation")


def _plan(tmp_path: Path) -> Path:
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"aspect_ratio": "16:9", "slides": []}), encoding="utf-8"
    )
    return plan


@pytest.mark.parametrize("mode", ["LA", "I;16"])
def test_generate_ppt_converts_non_rgb_slide_images(tmp_path, mode):
    image_path = tmp_path / f"slide-{mode.replace(';', '')}.png"
    Image.new(mode, (100, 50)).save(image_path)
    output = tmp_path / "deck.pptx"

    message = ppt.generate_ppt(str(_plan(tmp_path)), [str(image_path)], str(output))

    assert output.is_file()
    assert "Successfully generated" in message


def test_generate_ppt_creates_nested_output_dir(tmp_path):
    image_path = tmp_path / "slide.png"
    Image.new("RGB", (100, 50), "red").save(image_path)
    output = tmp_path / "nested" / "dir" / "deck.pptx"

    ppt.generate_ppt(str(_plan(tmp_path)), [str(image_path)], str(output))

    assert output.is_file()
