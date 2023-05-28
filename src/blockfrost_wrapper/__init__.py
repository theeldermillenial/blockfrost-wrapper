import logging
import os
import time
from threading import Lock

import blockfrost
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load the project information
load_dotenv()
PROJECT_ID = os.environ["PROJECT_ID"]
MAX_CALLS = int(os.environ["MAX_CALLS"])
call_lock = Lock()


class BlockfrostCallLimit(Exception):
    """Error when the Blockfrost call limit is reached."""


class BlockFrostWrapper:
    """A class to enforce stall calls to Blockfrost when a rate limit is hit."""

    last_call: float = time.time()
    num_limit_calls: float = 0.0
    max_limit_calls: int = 500
    total_calls = 0
    max_total_calls = MAX_CALLS
    backoff_time: int = 10
    _api = blockfrost.BlockFrostApi(PROJECT_ID)

    @classmethod
    def remaining_calls(cls) -> int:
        """Remaining calls before rate limit."""
        return cls.max_total_calls - cls.total_calls

    @classmethod
    def reset_total_calls(cls) -> None:
        """Reset the call count."""
        cls.total_calls = 0

    @classmethod
    def _limiter(cls):
        with call_lock:
            cls.num_limit_calls += 1
            cls.total_calls += 1
            if cls.total_calls >= cls.max_total_calls:
                raise BlockfrostCallLimit(
                    f"Made {cls.total_calls}, "
                    + f"only {cls.max_total_calls} are allowed.",
                )
            elif cls.num_limit_calls >= cls.max_limit_calls:
                logger.warning(
                    "At or near blockfrost rate limit. "
                    + f"Waiting {cls.backoff_time}s...",
                )
                time.sleep(cls.backoff_time)
                logger.info("Finished sleeping, resuming...")

        now = time.time()
        cls.num_limit_calls = max(0, cls.num_limit_calls - (now - cls.last_call) * 10)
        cls.last_call = now

    @classmethod
    def api(cls):
        """Blockfrost API with rate limits."""
        cls._limiter()
        return cls._api

    @classmethod
    def rate_limit(cls, func):
        """Wrap with rate limit.

        This can probably be removed. It might have utility in the future for
        customizing imposing rate limits on a function.

        """

        def wrapper(*args, **kwargs):
            cls._limiter()
            try:
                return func(*args, **kwargs)
            except blockfrost.ApiError:
                print(f"cls.num_limit_calls: {cls.num_limit_calls}")
                raise

        return wrapper
