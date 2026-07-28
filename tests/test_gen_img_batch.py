import scripts.gen_img as gen_img
import pytest


def test_global_model_accepts_multiple_four_arg_jobs(monkeypatch):
    calls = []
    monkeypatch.setattr(gen_img, "gen", lambda *args: calls.append(args))
    gen_img._main([
        "-m", "gemini-image",
        "01.md", "01.png", "576", "1024",
        "02.md", "02.png", "1024", "576",
    ])
    assert calls == [
        ("01.md", "01.png", "gemini-image", 576, 1024),
        ("02.md", "02.png", "gemini-image", 1024, 576),
    ]


def test_per_job_model_accepts_multiple_five_arg_jobs(monkeypatch):
    calls = []
    monkeypatch.setattr(gen_img, "gen", lambda *args: calls.append(args))
    gen_img._main([
        "01.md", "01.png", "model-a", "576", "1024",
        "02.md", "02.png", "model-b", "1024", "576",
    ])
    assert calls == [
        ("01.md", "01.png", "model-a", 576, 1024),
        ("02.md", "02.png", "model-b", 1024, 576),
    ]


def test_batch_runs_sequentially_in_input_order(monkeypatch):
    order = []
    monkeypatch.setattr(gen_img, "gen", lambda prompt, *_: order.append(prompt))
    gen_img._main([
        "-m", "gemini-image",
        "01.md", "01.png", "576", "1024",
        "02.md", "02.png", "1024", "576",
        "03.md", "03.png", "1024", "576",
    ])
    assert order == ["01.md", "02.md", "03.md"]


def test_vertex_preflight_requires_the_full_publisher_route(monkeypatch):
    monkeypatch.setattr(gen_img.pc, "load_secret", lambda name, **_: "project-123" if name == "GOOGLE_VERTEX_PROJECT" else "AQ.demo")

    route = gen_img.validate_google_route("gemini-3-pro-image", "AQ.demo")

    assert route == (
        "https://aiplatform.googleapis.com/v1/projects/project-123/locations/global/"
        "publishers/google/models/gemini-3-pro-image:generateContent"
    )


def test_preflight_rejects_a_regressed_vertex_base_url(monkeypatch):
    monkeypatch.setattr(gen_img, "_endpoint", lambda *_: "https://aiplatform.googleapis.com/v1")

    with pytest.raises(SystemExit, match="publishers/google"):
        gen_img.validate_google_route("gemini-3-pro-image", "AQ.demo")


def test_preflight_cli_makes_no_generation_call(monkeypatch, capsys):
    monkeypatch.setattr(gen_img, "validate_google_route", lambda model: f"route-for-{model}")
    monkeypatch.setattr(gen_img, "gen", lambda *_: pytest.fail("must not generate"))

    gen_img._main(["--preflight", "-m", "gemini-3-pro-image"])

    assert "route-for-gemini-3-pro-image" in capsys.readouterr().out
