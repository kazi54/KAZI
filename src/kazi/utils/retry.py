"""
Retry — Configurable retry with exponential backoff.

Domain-agnostic. Used by agents, destination adapters, and LLM clients
to handle transient failures gracefully.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from dataclasses import dataclass
from typing import Callable, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd
    retryable_exceptions: tuple = (Exception,)  # Which exceptions to retry


def calculate_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> float:
    """Calculate delay for a given retry attempt with exponential backoff."""
    delay = min(base_delay * (exponential_base ** attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random() * 0.5)
    return delay


async def retry_async(
    func: Callable,
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs,
):
    """
    Execute an async function with retry logic.

    Usage:
        result = await retry_async(
            my_async_func,
            arg1, arg2,
            config=RetryConfig(max_retries=3),
        )
    """
    config = config or RetryConfig()
    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e
            if attempt < config.max_retries:
                delay = calculate_delay(
                    attempt,
                    config.base_delay,
                    config.max_delay,
                    config.exponential_base,
                    config.jitter,
                )
                logger.warning(
                    f"Retry {attempt + 1}/{config.max_retries} for {func.__name__}: "
                    f"{type(e).__name__}: {e} — waiting {delay:.1f}s"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"All {config.max_retries} retries exhausted for {func.__name__}: "
                    f"{type(e).__name__}: {e}"
                )

    raise last_exception


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = (Exception,),
):
    """
    Decorator for adding retry logic to async functions.

    Usage:
        @with_retry(max_retries=3, retryable_exceptions=(TimeoutError, ConnectionError))
        async def call_api():
            ...
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        retryable_exceptions=retryable_exceptions,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(func, *args, config=config, **kwargs)
        return wrapper

    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern for protecting against cascading failures.

    States:
      - CLOSED: Normal operation, requests pass through
      - OPEN: Failing, requests are rejected immediately
      - HALF_OPEN: Testing, one request allowed through

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

        async with breaker:
            result = await call_external_service()
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        name: str = "default",
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        async with self._lock:
            if self.state == self.OPEN:
                # Check if recovery timeout has elapsed
                if self._last_failure_time:
                    elapsed = asyncio.get_event_loop().time() - self._last_failure_time
                    if elapsed >= self.recovery_timeout:
                        self.state = self.HALF_OPEN
                        logger.info(f"CircuitBreaker [{self.name}]: OPEN → HALF_OPEN")
                    else:
                        raise CircuitBreakerOpenError(
                            f"Circuit breaker [{self.name}] is OPEN. "
                            f"Recovery in {self.recovery_timeout - elapsed:.0f}s"
                        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            if exc_type is None:
                # Success
                if self.state == self.HALF_OPEN:
                    self.state = self.CLOSED
                    self.failure_count = 0
                    logger.info(f"CircuitBreaker [{self.name}]: HALF_OPEN → CLOSED")
                elif self.state == self.CLOSED:
                    self.failure_count = 0
            else:
                # Failure
                self.failure_count += 1
                self._last_failure_time = asyncio.get_event_loop().time()

                if self.failure_count >= self.failure_threshold:
                    self.state = self.OPEN
                    logger.warning(
                        f"CircuitBreaker [{self.name}]: → OPEN "
                        f"(failures: {self.failure_count})"
                    )

        return False  # Don't suppress the exception


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker is open and rejecting requests."""
    pass
