"""Loopback-only development server with a psycopg-compatible event loop."""

import asyncio

import uvicorn


def loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()


def serve() -> None:
    uvicorn.run(
        "risk_platform.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        loop="risk_platform.runtime:loop_factory",
    )
