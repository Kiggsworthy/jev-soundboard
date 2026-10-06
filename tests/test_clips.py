from jevboard.clips import BANNED, NAME, screen_text


def test_screen_catches_swearing_but_not_clean_lines():
    assert screen_text("oh what the fudge", BANNED) == []
    assert screen_text("well that was a total disaster", BANNED) == []
    assert screen_text("Holy SHIT", BANNED)
    assert screen_text("kys lol", BANNED)


def test_clip_names():
    assert NAME.match("bruh")
    assert NAME.match("sad_violin_2")
    assert not NAME.match("Bad Name")
    assert not NAME.match("../escape")
