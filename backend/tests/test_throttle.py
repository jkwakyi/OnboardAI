"""The attempt limiter counts, forgets and forgets bounded (ON-37).

Time is injected, so none of these sleep and none of them are flaky. The
window is the whole behaviour: a limiter that never forgets locks people
out permanently, and one that forgets too early is decoration.
"""

import threading

import pytest

from app.api.throttle import AttemptLimiter, TooManyAttempts


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def limiter(clock) -> AttemptLimiter:
    return AttemptLimiter(limit=3, window_seconds=60, clock=clock)


def fail(limiter: AttemptLimiter, key: str, times: int) -> None:
    for _ in range(times):
        limiter.record_failure(key)


# --- counting ----------------------------------------------------------


def test_a_key_with_no_failures_passes(limiter):
    limiter.check("someone")


def test_failures_below_the_limit_still_pass(limiter):
    fail(limiter, "someone", 2)

    limiter.check("someone")


def test_the_limit_itself_is_refused(limiter):
    """Three allowed failures means the fourth attempt does not happen."""
    fail(limiter, "someone", 3)

    with pytest.raises(TooManyAttempts):
        limiter.check("someone")


def test_keys_are_counted_separately(limiter):
    fail(limiter, "someone", 3)

    limiter.check("somebody else")


# --- the window --------------------------------------------------------


def test_failures_fall_out_of_the_window(limiter, clock):
    fail(limiter, "someone", 3)
    clock.advance(61)

    limiter.check("someone")


def test_a_failure_still_inside_the_window_counts(limiter, clock):
    fail(limiter, "someone", 2)
    clock.advance(59)
    fail(limiter, "someone", 1)

    with pytest.raises(TooManyAttempts):
        limiter.check("someone")


def test_the_window_slides_rather_than_resetting(limiter, clock):
    """Three failures spread over the window still fill it.

    A fixed window that cleared every sixty seconds would let somebody
    make three guesses at 0:59 and three more at 1:01.
    """
    for _ in range(3):
        limiter.record_failure("someone")
        clock.advance(20)

    # At 60 seconds the first failure has just left the window and the
    # other two have not, so there is room for exactly one more.
    limiter.check("someone")
    fail(limiter, "someone", 1)
    with pytest.raises(TooManyAttempts):
        limiter.check("someone")


def test_it_says_how_long_to_wait(limiter, clock):
    fail(limiter, "someone", 3)
    clock.advance(20)

    with pytest.raises(TooManyAttempts) as refused:
        limiter.check("someone")

    # 40 seconds of the window left, rounded up.
    assert 40 <= refused.value.retry_after_seconds <= 41


def test_the_wait_is_never_zero(limiter, clock):
    """A Retry-After of 0 invites a retry that is still refused."""
    fail(limiter, "someone", 3)
    clock.advance(59.999)

    with pytest.raises(TooManyAttempts) as refused:
        limiter.check("someone")

    assert refused.value.retry_after_seconds >= 1


# --- forgetting --------------------------------------------------------


def test_success_clears_the_key(limiter):
    fail(limiter, "someone", 3)

    limiter.clear("someone")

    limiter.check("someone")


def test_clearing_a_key_nobody_has_failed_on_is_harmless(limiter):
    limiter.clear("someone")


def test_reset_forgets_everything(limiter):
    fail(limiter, "a", 3)
    fail(limiter, "b", 3)

    limiter.reset()

    limiter.check("a")
    limiter.check("b")
    assert limiter.tracked_keys == 0


def test_an_expired_key_stops_being_tracked(limiter, clock):
    """Otherwise every address ever tried stays in memory for good."""
    fail(limiter, "someone", 1)
    assert limiter.tracked_keys == 1

    clock.advance(61)
    limiter.check("someone")

    assert limiter.tracked_keys == 0


def test_the_number_of_keys_is_bounded(clock):
    """The limiter must not become the way to exhaust the server's memory.

    An attacker who varies the address on every request would otherwise
    make this dictionary grow for as long as they kept going.
    """
    limiter = AttemptLimiter(limit=3, window_seconds=60, max_keys=10, clock=clock)

    for index in range(1000):
        limiter.record_failure(f"address-{index}")

    assert limiter.tracked_keys == 10


def test_the_key_dropped_is_the_least_recently_failed(clock):
    limiter = AttemptLimiter(limit=3, window_seconds=60, max_keys=2, clock=clock)

    fail(limiter, "old", 3)
    fail(limiter, "recent", 3)
    # Touching "old" again should save it and cost "recent" instead.
    fail(limiter, "old", 1)
    fail(limiter, "newest", 3)

    with pytest.raises(TooManyAttempts):
        limiter.check("old")
    limiter.check("recent")


# --- the obvious misconfigurations -------------------------------------


@pytest.mark.parametrize("limit", [0, -1])
def test_a_limit_below_one_is_refused(limit):
    with pytest.raises(ValueError):
        AttemptLimiter(limit=limit, window_seconds=60)


@pytest.mark.parametrize("window", [0, -60])
def test_a_window_that_is_not_positive_is_refused(window):
    with pytest.raises(ValueError):
        AttemptLimiter(limit=3, window_seconds=window)


# --- concurrency -------------------------------------------------------


def test_no_failure_is_lost_when_several_arrive_at_once():
    """Sync endpoints run in a threadpool, so two requests really can be
    inside the limiter at once.

    Eight threads record a hundred failures each against one key, with the
    limit set to exactly eight hundred. If a single update were lost the
    count would fall short and the key would still be allowed through.
    """
    limiter = AttemptLimiter(limit=800, window_seconds=60)
    start = threading.Barrier(8)

    def hammer():
        start.wait()
        for _ in range(100):
            limiter.record_failure("someone")

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with pytest.raises(TooManyAttempts):
        limiter.check("someone")
