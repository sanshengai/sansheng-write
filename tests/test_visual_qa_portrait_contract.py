from pathlib import Path

from scripts.visual_qa import _style_contracts


def test_declared_portrait_gets_a_source_scoped_cover_contract(tmp_path: Path):
    portrait = tmp_path / "portrait.jpg"
    portrait.write_bytes(b"museum-source-bytes")
    (tmp_path / "article-meta.yaml").write_text(
        'infographic_style: "claymation"\n'
        "cover_portrait:\n"
        '  file: "portrait.jpg"\n'
        '  source: "https://museum.example/object/1"\n'
        '  license: "Public domain"\n'
        '  credit: "Museum"\n',
        encoding="utf-8",
    )

    contracts, errors = _style_contracts(tmp_path)

    assert errors == []
    cover = contracts["cover"]
    assert cover["target_style"] == "montage-evidence+portrait-bleed"
    assert cover["style_contract"]["layout"] == "left-50-gap-6-right-portrait-bleed"
    required = cover["style_contract"]["required_visual_traits"]
    assert all("two or three smaller evidence badges" not in trait for trait in required)
    assert any("sole evidence subject" in trait for trait in required)
    layers = cover["authorized_source_layers"]
    assert len(layers) == 1
    assert layers[0]["type"] == "public-domain-historical-portrait"
    assert layers[0]["source_sha256"]


def test_incomplete_portrait_declaration_cannot_relax_cover_review(tmp_path: Path):
    (tmp_path / "article-meta.yaml").write_text(
        'infographic_style: "claymation"\n'
        "cover_portrait:\n"
        '  file: "missing.jpg"\n',
        encoding="utf-8",
    )

    contracts, errors = _style_contracts(tmp_path)

    assert contracts == {}
    assert any("cover_portrait 声明不完整" in error for error in errors)
