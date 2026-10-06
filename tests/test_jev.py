from jevboard.jev import MAX_CHOICES, build_questions, build_state, parse_answers

ALLOWED = ["airhorn", "sad_trombone", "bruh"]


def result(react, clip, tokens=420):
    return {"answers": {"react_now": {"type": "noul", "noul": react},
                        "clip": {"type": "choice", "choice": clip, "confidence": 0.8}},
            "usage": {"input_tokens": tokens, "output_tokens": 20}}


def test_parses_a_normal_answer():
    decision = parse_answers(result(0.91, "bruh"), ALLOWED)
    assert decision.react == 0.91
    assert decision.clip == "bruh"
    assert decision.input_tokens == 420


def test_none_means_no_clip():
    assert parse_answers(result(0.95, "none"), ALLOWED).clip is None


def test_unknown_clip_is_rejected():
    assert parse_answers(result(0.95, "something_else"), ALLOWED).clip is None


def test_react_is_clamped_and_sanitized():
    assert parse_answers(result(1.7, "bruh"), ALLOWED).react == 1.0
    assert parse_answers(result(-3, "bruh"), ALLOWED).react == 0.0
    assert parse_answers(result(float("nan"), "bruh"), ALLOWED).react == 0.0
    assert parse_answers(result("not a number", "bruh"), ALLOWED).react == 0.0


def test_garbage_responses():
    assert parse_answers(None, ALLOWED) is None
    assert parse_answers({"error": "nope"}, ALLOWED) is None
    partial = parse_answers({"answers": {"react_now": {"noul": 0.8}}}, ALLOWED)
    assert partial.react == 0.8 and partial.clip is None and partial.input_tokens == 0


def test_questions_leave_out_blocked_clips_and_offer_none():
    menu = {"airhorn": "a win", "sad_trombone": "a fail", "bruh": "something cringe"}
    questions = build_questions(menu, blocked=["airhorn"])
    options = questions["clip"]["criteria"]
    assert "airhorn" not in options
    assert {"sad_trombone", "bruh", "none"} <= set(options)
    assert questions["react_now"]["type"] == "noul"
    assert questions["clip"]["type"] == "choice"


def test_choice_respects_api_option_limit():
    menu = {f"clip_{i}": "x" for i in range(400)}
    assert len(build_questions(menu)["clip"]["criteria"]) == MAX_CHOICES


def test_state_has_the_newest_line():
    state = build_state("a call", "be nice", ["one", "two"], 12.4, ["bruh"])
    assert state["newest_line"] == "two"
    assert state["seconds_since_last_clip"] == 12
    assert build_state("a call", "v", [], None, [])["seconds_since_last_clip"] is None
