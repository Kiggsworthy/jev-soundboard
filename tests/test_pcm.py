import numpy as np

from jevboard.pcm import (ClipLanes, RoomMixer, SampleBuffer, float_to_stereo_s16, resample, rms,
                          stereo_s16_to_float, to_api)


def test_resample_halves_48k_to_24k():
    assert len(resample(np.ones(4800), 48000, 24000)) == 2400
    assert len(resample(np.ones(4410), 44100, 24000)) == 2400


def test_to_api_is_int16_mono():
    pcm = to_api(np.full((4800, 2), 0.5, dtype=np.float32), 48000, 24000)
    assert len(pcm) == 2400 * 2
    assert 16000 < rms(pcm) < 16500


def test_clip_lanes_overlap_and_finish():
    lanes = ClipLanes()
    lanes.add(np.full(30, 0.25, dtype=np.float32))
    lanes.add(np.full(10, 0.25, dtype=np.float32))
    block = lanes.mix(20)
    assert block[0] == 0.5 and block[15] == 0.25
    assert lanes.active()
    lanes.mix(20)
    assert not lanes.active()


def test_room_mixer_sums_speakers():
    room = RoomMixer(rate=1000, max_seconds=1)
    room.add("a", np.full(10, 0.1, dtype=np.float32))
    room.add("b", np.full(5, 0.2, dtype=np.float32))
    block = room.drain(10)
    assert np.allclose(block[:5], 0.3) and np.allclose(block[5:], 0.1)
    assert room.speakers() == 0


def test_room_mixer_caps_lag():
    room = RoomMixer(rate=100, max_seconds=0.5)
    room.add("a", np.arange(200, dtype=np.float32))
    assert len(room.drain(1000)[:50]) == 50
    room.add("a", np.arange(200, dtype=np.float32))
    assert room.drain(50)[0] == 150  # only the newest half second was kept


def test_sample_buffer_pads_and_caps():
    buffer = SampleBuffer(limit=5)
    buffer.push(np.arange(8, dtype=np.float32))
    assert list(buffer.take(7)) == [3, 4, 5, 6, 7, 0, 0]


def test_stereo_round_trip():
    mono = np.array([0.5, -0.5, 0.0], dtype=np.float32)
    back = stereo_s16_to_float(float_to_stereo_s16(mono))
    assert np.allclose(back, mono, atol=1e-3)
