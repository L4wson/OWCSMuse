from owcsmuse.faceit.ratelimit import AdaptiveRateLimiter, RateLimitInfo, backoff_delay, parse_rate_limit_headers


def test_parse_ietf_style_headers_as_sent_by_faceit():
    info = parse_rate_limit_headers(
        {"ratelimit-limit": "20, 20;w=1", "ratelimit-remaining": "18", "ratelimit-reset": "0"}
    )
    assert info.limit == 20 and info.remaining == 18
    assert info.window_seconds == 1.0 and info.reset_seconds == 0.0
    assert info.retry_after is None and info.has_data


def test_parse_x_ratelimit_headers_with_epoch_reset():
    now = 1_700_000_000.0
    info = parse_rate_limit_headers(
        {"X-RateLimit-Limit": "100", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(now) + 7),
         "Retry-After": "3"},
        now=now,
    )
    assert info.limit == 100 and info.remaining == 0
    assert info.reset_seconds == 7.0 and info.retry_after == 3.0


def test_parse_missing_headers():
    info = parse_rate_limit_headers({"content-type": "application/json"})
    assert not info.has_data and info.window_seconds == 1.0


def test_backoff_is_exponential_with_full_jitter():
    assert backoff_delay(0, base=0.5, cap=60, rng=lambda: 1.0) == 0.5
    assert backoff_delay(3, base=0.5, cap=60, rng=lambda: 1.0) == 4.0
    assert backoff_delay(20, base=0.5, cap=60, rng=lambda: 1.0) == 60.0  # capped
    assert backoff_delay(3, base=0.5, cap=60, rng=lambda: 0.0) == 0.0     # jitter lower bound
    for attempt in range(8):
        d = backoff_delay(attempt)
        assert 0.0 <= d <= min(60.0, 0.5 * 2**attempt)


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(s)
        self.now += s


def test_limiter_paces_to_limit_over_window():
    t = FakeTime()
    lim = AdaptiveRateLimiter(headroom=2, default_per_second=10, clock=t.clock, sleep=t.sleep)
    lim.wait()  # first request: no wait
    lim.observe(RateLimitInfo(limit=20, remaining=19, reset_seconds=0, window_seconds=1.0), 200)
    assert lim.min_interval == 0.05
    slept = lim.wait()
    assert abs(slept - 0.05) < 1e-9


def test_limiter_pauses_when_remaining_hits_headroom():
    t = FakeTime()
    lim = AdaptiveRateLimiter(headroom=2, default_per_second=100, clock=t.clock, sleep=t.sleep)
    lim.wait()
    lim.observe(RateLimitInfo(limit=20, remaining=2, reset_seconds=0, window_seconds=1.0), 200)
    slept = lim.wait()
    assert slept >= 1.0  # waited out the window even though reset=0


def test_limiter_honours_retry_after_on_429():
    t = FakeTime()
    lim = AdaptiveRateLimiter(headroom=2, default_per_second=100, clock=t.clock, sleep=t.sleep)
    lim.wait()
    lim.observe(RateLimitInfo(limit=20, remaining=0, reset_seconds=1, window_seconds=1.0, retry_after=3.0), 429)
    slept = lim.wait()
    assert abs(slept - 3.0) < 1e-9


def test_limiter_no_headers_falls_back_to_default_rate():
    t = FakeTime()
    lim = AdaptiveRateLimiter(headroom=2, default_per_second=4, clock=t.clock, sleep=t.sleep)
    lim.wait()
    lim.observe(RateLimitInfo(), 200)
    assert abs(lim.wait() - 0.25) < 1e-9
