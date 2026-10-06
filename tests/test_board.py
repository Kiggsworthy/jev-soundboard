import json

import numpy as np

from jevboard.board import Soundboard, load_index
from jevboard.effects import DESCRIPTIONS, EFFECTS


def write(tmp_path, index, files=()):
    for name in files:
        (tmp_path / name).write_bytes(b"\0" * 10)
    (tmp_path / "index.json").write_text(json.dumps(index))


def test_loads_valid_entries(tmp_path):
    write(tmp_path, {"bruh": {"file": "bruh.mp3", "desc": "a friend says something cringe"}}, ["bruh.mp3"])
    clips = load_index(tmp_path)
    assert clips["bruh"].desc == "a friend says something cringe"
    assert clips["bruh"].file == tmp_path / "bruh.mp3"


def test_skips_missing_files_and_bad_entries(tmp_path):
    write(tmp_path, {"gone": {"file": "gone.mp3"}, "bad": "nope", "nofile": {"desc": "x"},
                     "ok": {"file": "ok.wav"}}, ["ok.wav"])
    clips = load_index(tmp_path)
    assert list(clips) == ["ok"]
    assert clips["ok"].desc == "ok"  # falls back to the name


def test_bad_or_missing_index(tmp_path):
    assert load_index(tmp_path) == {}
    (tmp_path / "index.json").write_text("{not json")
    assert load_index(tmp_path) == {}
    (tmp_path / "index.json").write_text("[1, 2]")
    assert load_index(tmp_path) == {}


def test_board_has_built_ins_with_zero_clips(tmp_path):
    board = Soundboard(tmp_path)
    assert set(board.names()) == set(DESCRIPTIONS)
    assert board.samples("airhorn") is EFFECTS["airhorn"]
    assert board.samples("nope") is None


def test_effects_are_sane():
    assert len(EFFECTS) >= 15
    for name, samples in EFFECTS.items():
        assert samples.dtype == np.float32, name
        assert 0.1 < len(samples) / 48000 < 4, name
        assert np.isfinite(samples).all(), name
        assert np.abs(samples).max() <= 0.9 + 1e-6, name
        assert DESCRIPTIONS[name], name
