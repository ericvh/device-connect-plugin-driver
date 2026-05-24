"""In-memory loopback messaging bus for integration tests."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Optional

from device_connect_edge.messaging.base import MessagingClient, Subscription
from device_connect_edge.messaging.exceptions import NotConnectedError, RequestTimeoutError


class _LoopbackSubscription(Subscription):
    def __init__(self, broker: LoopbackBroker, subject: str, callback: Callable[..., Awaitable[None]]) -> None:
        self._broker = broker
        self._subject = subject
        self._callback = callback

    async def unsubscribe(self) -> None:
        self._broker._unsubscribe(self._subject, self._callback)


class LoopbackBroker:
    """Process-local pub/sub + request/reply broker shared by multiple clients."""

    def __init__(self) -> None:
        self._subs: list[tuple[str, Callable[..., Awaitable[None]]]] = []

    def _unsubscribe(self, subject: str, callback: Callable[..., Awaitable[None]]) -> None:
        self._subs = [(s, cb) for s, cb in self._subs if not (s == subject and cb is callback)]

    async def deliver(self, subject: str, data: bytes, reply_subject: str | None = None) -> None:
        for pattern, callback in list(self._subs):
            if not _subject_matches(pattern, subject):
                continue
            try:
                await callback(data, reply_subject)
            except TypeError:
                await callback(data, reply_subject, None)

    async def subscribe(
        self,
        subject: str,
        callback: Callable[..., Awaitable[None]],
    ) -> _LoopbackSubscription:
        self._subs.append((subject, callback))
        return _LoopbackSubscription(self, subject, callback)

    async def request(self, subject: str, data: bytes, timeout: float = 5.0) -> bytes:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bytes] = loop.create_future()
        reply_subject = f"_reply.{id(fut)}"

        async def on_reply(payload: bytes, reply: str | None = None, *_args: Any) -> None:
            if not fut.done():
                fut.set_result(payload)

        sub = await self.subscribe(reply_subject, on_reply)
        try:
            await self.deliver(subject, data, reply_subject)
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise RequestTimeoutError(f"loopback request timed out on {subject}") from exc
        finally:
            await sub.unsubscribe()


def _subject_matches(pattern: str, subject: str) -> bool:
    if pattern == subject:
        return True
    regex = pattern.replace(".", r"\.").replace("*", "[^.]+").replace(">", ".*")
    return re.fullmatch(regex, subject) is not None


class LoopbackMessagingClient(MessagingClient):
    """MessagingClient backed by a shared LoopbackBroker."""

    def __init__(self, broker: LoopbackBroker) -> None:
        self._broker = broker
        self._connected = False
        self._closed = False

    async def connect(self, servers: list[str], credentials: dict | None = None, **kwargs: Any) -> None:
        self._connected = True

    async def publish(self, subject: str, data: bytes) -> None:
        if not self._connected:
            raise NotConnectedError("loopback client not connected")
        await self._broker.deliver(subject, data, None)

    async def subscribe(
        self,
        subject: str,
        callback: Callable[[bytes, Optional[str]], Awaitable[None]],
        queue: str | None = None,
        subscribe_only: bool = False,
    ) -> Subscription:
        if not self._connected:
            raise NotConnectedError("loopback client not connected")

        async def wrapped(data: bytes, reply: str | None = None, *_args: Any) -> None:
            await callback(data, reply)

        return await self._broker.subscribe(subject, wrapped)

    async def request(self, subject: str, data: bytes, timeout: float = 5.0) -> bytes:
        if not self._connected:
            raise NotConnectedError("loopback client not connected")
        return await self._broker.request(subject, data, timeout=timeout)

    async def close(self) -> None:
        self._closed = True
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and not self._closed

    @property
    def is_closed(self) -> bool:
        return self._closed


def install_loopback_backend(broker: LoopbackBroker | None = None) -> LoopbackBroker:
    """Register the loopback backend and return the shared broker instance."""
    from device_connect_edge.messaging import register_backend

    shared = broker or LoopbackBroker()
    register_backend("loopback", lambda: LoopbackMessagingClient(shared))
    return shared
