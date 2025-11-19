import json
import screen_overrides


def test_load_overrides_handles_legacy_structure(tmp_path):
    overrides_path = tmp_path / "screen_overrides.json"
    overrides_path.write_text(json.dumps({"screens": {"travel": {"font_scale": 1.5}}}))

    loaded = screen_overrides.load_overrides(str(overrides_path))
    assert "travel" in loaded
    assert loaded["travel"]["defaults"]["font_scale"] == 1.5
    assert loaded["travel"]["profiles"] == {}


def test_resolve_overrides_for_profile_merges_defaults():
    overrides = {
        "travel": {
            "defaults": {"font_scale": 1.1},
            "profiles": {
                "hyperpixel4": {"image_scale": 0.95},
            },
        },
        "date": {
            "profiles": {"hyperpixel4_square": {"font_scale": 1.05}},
        },
    }

    resolved = screen_overrides.resolve_overrides_for_profile(
        "hyperpixel4", overrides=overrides
    )
    assert set(resolved) == {"travel"}
    assert resolved["travel"].font_scale == 1.1
    assert resolved["travel"].image_scale == 0.95

    square = screen_overrides.resolve_override_for_screen(
        "date", "hyperpixel4_square", overrides=overrides
    )
    assert square is not None
    assert square.font_scale == 1.05
    assert square.image_scale is None


def test_resolve_override_for_screen_missing_entry():
    overrides = {}
    assert (
        screen_overrides.resolve_override_for_screen(
            "unknown", "hyperpixel4", overrides=overrides
        )
        is None
    )
