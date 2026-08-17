# episode.py — per-episode Docker orchestration. Creates a private network,
# starts the (trusted) tool-server container with the episode's world DB
# bind-mounted, starts the (untrusted) language executor on the same
# network (skipped for the json_mcp surface, which has no executor at all),
# and exposes exec()/teardown() for the agent loop to call.

from __future__ import annotations

import shutil
import tempfile
import time
import uuid
from pathlib import Path

import docker
import requests

from config import (
    CONTAINER_READY_POLL_INTERVAL_S,
    CONTAINER_READY_REQUEST_TIMEOUT_S,
    CONTAINER_READY_TIMEOUT_S,
    EXEC_HTTP_TIMEOUT_S,
    EXECUTOR_IMAGES as _EXECUTOR_IMAGES,
    RETRY_DELAYS_S as _EXEC_RETRY_DELAYS_S,
    TOOL_SERVER_IMAGE as _TOOL_SERVER_IMAGE,
)


class Episode:
    def __init__(self, world_db: str | Path, surface: str, ready_timeout_s: float = CONTAINER_READY_TIMEOUT_S):
        if surface not in ("python", "js", "ts", "json_mcp"):
            raise ValueError(f"unknown surface: {surface}")
        self.surface = surface
        self.client = docker.from_env()
        self.episode_id = uuid.uuid4().hex[:8]
        self.tmp_dir = Path(tempfile.mkdtemp(prefix=f"episode-{self.episode_id}-"))
        self.executor = None

        self.network = self.client.networks.create(
            f"episode-{self.episode_id}", driver="bridge")

        self.db_path = self.tmp_dir / "world.sqlite"
        shutil.copyfile(world_db, self.db_path)

        #this is the fatapi / fastmcp server
        self.tool_server = self.client.containers.run(
            _TOOL_SERVER_IMAGE, detach=True,
            name=f"tools-{self.episode_id}",
            network=self.network.name,
            volumes={str(self.db_path): {"bind": "/data/world.sqlite", "mode": "rw"}},
            ports={"8000/tcp": None},   # published so the harness (on host) can reach it
        )
        self._tool_server_url = self._wait_ready(self.tool_server, 8000, ready_timeout_s)

        # if it is json/mcp no need for another docker , it is already there with the fastapi (fastmcp)
        if surface != "json_mcp":
            image = _EXECUTOR_IMAGES[surface]
            self.executor = self.client.containers.run(
                image,
                detach=True,
                name=f"exec-{self.episode_id}",
                network=self.network.name,
                environment={"TOOL_SERVER_URL": f"http://tools-{self.episode_id}:8000"}, # noqa
                ports={"8001/tcp": None},  # published so the harness can POST /exec
            )
            self._executor_url = self._wait_ready(self.executor, 8001, ready_timeout_s)

    def _wait_ready(self, container, internal_port: int, timeout_s: float) -> str:
        container.reload()
        host_port = container.ports[f"{internal_port}/tcp"][0]["HostPort"]
        url = f"http://localhost:{host_port}"
        deadline = time.monotonic() + timeout_s
        last_error = None
        while time.monotonic() < deadline:
            try:
                path = "/openapi.json" if internal_port == 8000 else "/health"
                requests.get(f"{url}{path}", timeout=CONTAINER_READY_REQUEST_TIMEOUT_S)
                return url
            except requests.RequestException as e:
                last_error = e
                time.sleep(CONTAINER_READY_POLL_INTERVAL_S)
        raise RuntimeError(f"{container.name} never became ready on port {internal_port}: {last_error}")

    def tool_server_url(self) -> str:
        return self._tool_server_url

    def exec(self, code: str, lang: str | None = None,
             max_tool_calls: int | None = None) -> dict:
        """max_tool_calls: cap on tool calls inside this ONE block (None =
        unlimited). Sent per request rather than set as a container env var so
        the executor images stay identical across the batching ablation's
        capped and uncapped arms — an image difference would be a confound."""
        if self.executor is None:
            raise RuntimeError(f"no executor container for surface={self.surface!r}")
        payload = {"code": code, "lang": lang or self.surface}
        # Omitted entirely when unlimited, so an uncapped run puts the exact
        # same request on the wire as before this flag existed.
        if max_tool_calls is not None:
            payload["max_tool_calls"] = max_tool_calls
        last_error = None
        for attempt, delay in enumerate((0.0, *_EXEC_RETRY_DELAYS_S)):
            if delay:
                time.sleep(delay)
            try:
                resp = requests.post(f"{self._executor_url}/exec", json=payload,
                                      timeout=EXEC_HTTP_TIMEOUT_S)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.ConnectionError as e:
                last_error = e  # container unreachable — worth a retry, see module comment
            except requests.exceptions.HTTPError:
                raise  # a real response from a live container — not a connectivity issue, don't retry
        raise last_error

    def teardown(self) -> None:
        for container in (self.executor, self.tool_server):
            if container is None:
                continue
            try:
                container.stop(timeout=3)
            except Exception:  # noqa: BLE001 — best-effort cleanup, never let one failure block the rest
                pass
            try:
                container.remove(force=True)
            except Exception:  # noqa: BLE001
                pass
        try:
            self.network.remove()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def __enter__(self) -> "Episode":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.teardown()
