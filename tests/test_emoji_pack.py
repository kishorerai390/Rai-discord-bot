from pathlib import Path

import pytest

from music_bot.emoji_pack import eligible_images, emoji_name, image_data_uri


def test_emoji_name_normalizes_pack_filenames():
    assert emoji_name("3D Butterfly!!.PNG") == "3d_butterfly"
    assert emoji_name("x.gif") == "x_emoji"
    assert len(emoji_name("a" * 80 + ".webp")) <= 32


def test_image_data_uri_encodes_supported_image():
    uri = image_data_uri("shine.webp", b"image-bytes")
    assert uri.startswith("data:image/webp;base64,")
    assert "aW1hZ2UtYnl0ZXM=" in uri


@pytest.mark.parametrize("filename", ["nope.svg", "readme.txt", "emoji.lottie"])
def test_image_data_uri_rejects_unsupported_formats(filename):
    with pytest.raises(ValueError, match="Unsupported"):
        image_data_uri(filename, b"bytes")


def test_image_data_uri_rejects_empty_and_oversized_images():
    with pytest.raises(ValueError, match="empty"):
        image_data_uri("a.png", b"")
    with pytest.raises(ValueError, match="256 KiB"):
        image_data_uri("a.png", b"x" * (256 * 1024))


def test_eligible_images_filters_and_sorts(tmp_path: Path):
    for name in ("z.webp", "a.PNG", "notes.txt", ".hidden.png"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in eligible_images(tmp_path.iterdir())] == ["a.PNG", "z.webp"]
