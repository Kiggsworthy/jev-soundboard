import asyncio

from jevboard.jev import Decision
from jevboard.sidekick import TRIGGER, AntiRepeat, CostMeter
from jevboard.config import Config


def run(coro):
    return asyncio.run(coro)


def test_fires_when_confident(make_sidekick):
    sidekick, transport, jev, _ = make_sidekick([Decision(0.9, "airhorn", 300)])
    run(sidekick.heard("he just won the whole thing"))
    assert len(transport.played) == 1
    assert sidekick.recent.played == ["airhorn"]
    assert jev.calls[0]["state"]["newest_line"] == "he just won the whole thing"


def test_trigger_levels(make_sidekick):
    for level, expected in (("chill", 0), ("normal", 0), ("trigger_happy", 1)):
        sidekick, transport, _, _ = make_sidekick([Decision(0.7, "airhorn")], trigger=level)
        run(sidekick.heard("ok"))
        assert len(transport.played) == expected, level
    assert TRIGGER["chill"] > TRIGGER["normal"] > TRIGGER["trigger_happy"]


def test_min_gap_between_clips(make_sidekick):
    sidekick, transport, _, clock = make_sidekick(
        [Decision(0.95, "airhorn"), Decision(0.95, "boing"), Decision(0.95, "bonk")], min_gap=4.0)
    run(sidekick.heard("one"))
    clock.now += 2
    run(sidekick.heard("two"))  # too soon
    clock.now += 3
    run(sidekick.heard("three"))
    assert len(transport.played) == 2
    assert sidekick.recent.played == ["airhorn", "bonk"]


def test_no_repeat_of_recent_clip(make_sidekick):
    sidekick, transport, jev, clock = make_sidekick([Decision(0.95, "airhorn"), Decision(0.95, "airhorn")])
    run(sidekick.heard("one"))
    clock.now += 10
    run(sidekick.heard("two"))
    assert len(transport.played) == 1
    assert "airhorn" in jev.calls[1]["blocked"]


def test_off_and_busy_audio(make_sidekick):
    sidekick, transport, jev, _ = make_sidekick([Decision(0.95, "airhorn")])
    sidekick.enabled = False
    run(sidekick.heard("one"))
    assert jev.calls == [] and transport.played == []
    sidekick.enabled = True
    transport.busy = True  # a clip is still playing
    run(sidekick.heard("two"))
    assert transport.played == []


def test_only_the_newest_slice_is_judged(make_sidekick):
    sidekick, transport, jev, _ = make_sidekick(delay=0.05)

    async def burst():
        tasks = [asyncio.create_task(sidekick.heard(f"line {i}")) for i in range(6)]
        await asyncio.gather(*tasks)

    run(burst())
    # The first slice is judged; the five that arrived meanwhile collapse into one more decision.
    assert len(jev.calls) == 2
    assert jev.calls[-1]["state"]["newest_line"] == "line 5"
    assert len(jev.calls[-1]["state"]["transcript"]) == 6


def test_window_drops_old_lines(make_sidekick):
    sidekick, _, _, clock = make_sidekick(window_seconds=10)
    sidekick.add("old")
    clock.now += 11
    sidekick.add("new")
    assert [text for _, text in sidekick.window] == ["new"]


def test_manual_fire_does_not_reset_the_gap(make_sidekick):
    sidekick, transport, _, _ = make_sidekick()
    assert sidekick.fire("tada", manual=True)
    assert sidekick.last_clip is None
    assert not sidekick.fire("no_such_clip")
    assert len(transport.played) == 1


def test_anti_repeat_never_blocks_more_than_half_the_board():
    recent = AntiRepeat(25)
    for name in ["a", "b", "c", "d", "e", "a"]:
        recent.add(name)
    assert recent.blocked(board_size=6) == ["a", "e", "d"]
    assert recent.blocked(board_size=100) == ["a", "e", "d", "c", "b"]
    assert recent.blocked(board_size=1) == []
    assert recent.allows("b", board_size=6)
    assert not recent.allows("a", board_size=6)


def test_cost_meter():
    config = Config(jev_price_per_mtok=0.042, transcribe_price_per_minute=0.003)
    meter = CostMeter()
    for _ in range(1000):
        meter.add_decision(Decision(0.1, None, 1000))
    meter.add_audio(3600)
    assert round(meter.jev_usd(config), 4) == 0.042
    assert round(meter.transcribe_usd(config), 4) == 0.18
    assert meter.decisions == 1000
