from scripts import profile_config


def test_signature_clay_contract_cannot_be_overridden_by_private_profile(monkeypatch):
    monkeypatch.setattr(
        profile_config,
        "brand",
        lambda: {
            "visual": {
                "default_profile": "warm-light-clay",
                "profiles": {
                    "warm-light-clay": {
                        "background": "#000000",
                        "accent": "#003300",
                        "thresholds": {"mean_luma_min": 1},
                    }
                },
            }
        },
    )

    recipe = profile_config.visual_profile("warm-light-clay")

    assert recipe["contract_owner"] == "sansheng-write"
    assert recipe["contract_revision"] == "warm-light-clay/2"
    assert recipe["background"] == "#F7F2E9"
    assert recipe["accent"] == "#79AA95"
    assert recipe["thresholds"]["mean_luma_min"] == 192

