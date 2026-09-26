"""Loopback-only development server with a psycopg-compatible event loop."""

import asyncio
import logging

import uvicorn


def loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(
        "risk_platform.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        proxy_headers=False,
        server_header=False,
        access_log=False,
        timeout_keep_alive=5,
        loop="risk_platform.runtime:loop_factory",
    )
