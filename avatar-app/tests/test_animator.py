import random

from avatar.animator import Animator


def make(seed=1, bmin=3.0, bmax=6.0, ms=120):
    return Animator(random.Random(seed), bmin, bmax, ms)


def test_mouth_stays_closed_when_not_speaking():
    a = make()
    assert not any(a.tick(t / 100, False)[0] for t in range(500))


def test_mouth_flaps_about_five_times_a_second_while_speaking():
    a = make()
    mouth = [a.tick(t * 0.02, True)[0] for t in range(100)]          # 2 seconds, sampled every 20 ms
    toggles = sum(1 for x, y in zip(mouth, mouth[1:]) if x != y)
    assert 16 <= toggles <= 28                                        # roughly 5 flaps (open+close) per second


def test_mouth_closes_when_speech_stops():
    a = make()
    for t in range(50):
        a.tick(t * 0.02, True)
    assert a.tick(1.2, False)[0] is False


def test_blinks_last_blink_ms_and_come_every_min_to_max_seconds():
    a = make()
    dt, starts, runs, prev, run_start = 0.01, [], [], False, 0.0
    for i in range(6000):                                             # 60 seconds
        t = i * dt
        blinking = a.tick(t, False)[1]
        if blinking and not prev:
            starts.append(t)
            run_start = t
        if prev and not blinking:
            runs.append(t - run_start)
        prev = blinking
    assert len(starts) >= 9
    assert all(0.105 <= r <= 0.14 for r in runs)
    gaps = [b - a_ for a_, b in zip(starts, starts[1:])]
    assert all(2.95 <= g <= 6.05 for g in gaps)
