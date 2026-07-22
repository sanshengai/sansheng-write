import scripts.gen_img as gen_img


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
