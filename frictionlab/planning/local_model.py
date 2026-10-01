"""Owned local llama.cpp process shared by independent, credential-free model adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import threading
import time
from copy import deepcopy

import httpx
import psutil
from pydantic import ValidationError
from smolagents.models import (
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
    Model,
)

from frictionlab.browser.broker import free_port
from frictionlab.browser.state import redact
from frictionlab.configuration import CONFIG_DIRECTORY, ROOT, read_json
from frictionlab.planning.choices import INSTRUCTION, PROTOCOL, available_choices, expand_choice
from frictionlab.planning.contracts import PlannerStopped


class LocalModelRuntime:
    def __init__(self, directory=None):
        self.resources = read_json(CONFIG_DIRECTORY / "resource-manifest.json")
        self.runtime_key = "runtime" if os.name == "nt" else "runtime_linux"
        self.settings = read_json(CONFIG_DIRECTORY / "models.json")["planner"]
        self.directory = directory or ROOT / "artifacts" / "phase3" / "model"
        self.process = None
        self.log = None
        self.client = None
        self.endpoint = None
        self.lock = threading.Lock()
        self.peak_rss_bytes = 0
        self.startup_seconds = 0
        self.stop_monitor = threading.Event()
        self.monitor = None
        self.memory_exceeded = False
        self.cleanup_errors = []
        self.verified_model_sha256 = None

    def check_resources(self):
        runtime = (
            ROOT / self.resources[self.runtime_key]["local_path"].replace("\\", "/")
        ).resolve()
        weights = (ROOT / self.resources["model"]["local_path"].replace("\\", "/")).resolve()
        if not runtime.is_relative_to((ROOT / ".runtime").resolve()) or not weights.is_relative_to(
            (ROOT / "models").resolve()
        ):
            raise PlannerStopped(
                "model_setup", "Local model resource paths escape their project directories."
            )
        if not runtime.is_file() or not weights.is_file():
            raise PlannerStopped(
                "model_setup", "Pinned local runtime or model is missing; run resource setup first."
            )
        with weights.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != self.resources["model"]["sha256"]:
            raise PlannerStopped(
                "model_setup", "Local model checksum does not match the pinned resource manifest."
            )
        self.verified_model_sha256 = digest
        return runtime, weights

    def sample_memory(self):
        while not self.stop_monitor.wait(0.2):
            try:
                usage = psutil.Process(self.process.pid).memory_info().rss
                self.peak_rss_bytes = max(self.peak_rss_bytes, usage)
                if usage > self.settings["memory_budget_gib"] * 1024**3:
                    self.memory_exceeded = True
                    self.process.terminate()
                    return
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return

    async def __aenter__(self):
        started = time.monotonic()
        try:
            runtime, weights = await asyncio.to_thread(self.check_resources)
            self.directory.mkdir(parents=True, exist_ok=True)
            self.log = (self.directory / "llama-server.log").open("w", encoding="utf-8")
            self.endpoint = f"http://127.0.0.1:{free_port()}"
            port = self.endpoint.rsplit(":", 1)[1]
            self.process = await asyncio.to_thread(
                subprocess.Popen,
                [
                    str(runtime),
                    "-m",
                    str(weights),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    port,
                    "-c",
                    str(self.settings["context_tokens"]),
                    "-t",
                    str(min(os.cpu_count() or 2, 8)),
                    "-ngl",
                    "0",
                    "--parallel",
                    "1",
                    "--alias",
                    "frictionlab-local",
                    "--cache-ram",
                    "512",
                    "--no-agent",
                    "--no-ui",
                    "--no-ui-mcp-proxy",
                ],
                env=launch_environment(runtime.parent),
                stdout=self.log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.monitor = threading.Thread(target=self.sample_memory, daemon=True)
            self.monitor.start()
            self.client = httpx.Client(
                base_url=self.endpoint, trust_env=False, follow_redirects=False
            )
            deadline = time.monotonic() + self.settings["startup_timeout_seconds"]
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                while time.monotonic() < deadline:
                    if self.process.poll() is not None:
                        raise PlannerStopped(
                            "model_startup", "Owned local model process exited during startup."
                        )
                    try:
                        response = await client.get(self.endpoint + "/health", timeout=2)
                        if response.status_code == 200:
                            self.startup_seconds = time.monotonic() - started
                            return self
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.25)
            raise PlannerStopped("model_startup", "Local model startup deadline exceeded.")
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        self.stop_monitor.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait, 10)
        if self.monitor:
            await asyncio.to_thread(self.monitor.join, 2)
        if self.client:
            self.client.close()
        if self.log:
            self.log.close()
        self.client = self.log = None

    def post(self, path, payload, timeout):
        if self.memory_exceeded:
            raise PlannerStopped(
                "model_memory_limit", "Owned model exceeded its sampled memory ceiling."
            )
        if self.client is None or self.process is None or self.process.poll() is not None:
            raise PlannerStopped("model_unavailable", "Owned local model is unavailable.")
        response = self.client.post(path, json=payload, timeout=timeout)
        response.raise_for_status()
        if len(response.content) > 256_000:
            raise PlannerStopped(
                "invalid_model_output", "Model response exceeds its payload ceiling."
            )
        return response.json()


class LocalPlannerModel(Model):
    """smolagents adapter; replace this interface without changing broker or persona memory."""

    planning_protocol = PROTOCOL

    def __init__(self, runtime, memory, limits, seed, writer):
        super().__init__(model_id="frictionlab-local")
        self.runtime = runtime
        self.memory = memory
        self.limits = limits
        self.seed = seed
        self.writer = writer
        self.records = []
        self.last_fault = None
        self.stopped = threading.Event()
        self.deadline = time.monotonic() + limits.max_runtime_seconds

    def generate(self, messages, **kwargs):
        record = {
            "attempt": len(self.records) + 1,
            "seed": self.seed,
            "observation_id": self.memory.state["observation_id"],
            "status": "pending",
            "inference_seconds": 0,
        }
        started = time.monotonic()
        try:
            if self.stopped.is_set():
                raise PlannerStopped("cancelled", "Planner session was stopped.")
            if len(self.records) >= self.limits.max_steps:
                raise PlannerStopped("step_limit", "Planner decision ceiling reached.")
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise PlannerStopped("runtime_limit", "Planner runtime ceiling reached.")
            if not self.runtime.lock.acquire(
                timeout=min(remaining, self.limits.request_timeout_seconds)
            ):
                raise PlannerStopped(
                    "model_queue_timeout", "Local inference queue deadline exceeded."
                )
            try:
                state = deepcopy(self.memory.state)
                choices = available_choices(state)
                state.pop("observation_id", None)
                state["action_choices"] = list(choices)
                system = next(
                    (message.content for message in messages if message.role == MessageRole.SYSTEM),
                    "Select a permitted action for the observed user goal.",
                )
                payload_messages = [
                    {"role": "system", "content": system + "\n" + INSTRUCTION},
                    {"role": "user", "content": json.dumps(state, separators=(",", ":"))},
                ]
                timeout = min(
                    self.limits.request_timeout_seconds, max(0.1, self.deadline - time.monotonic())
                )
                formatted = self.runtime.post(
                    "/apply-template",
                    {
                        "messages": payload_messages,
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                    timeout,
                )["prompt"]
                tokens = self.runtime.post(
                    "/tokenize", {"content": formatted, "add_special": True}, timeout
                )["tokens"]
                record["input_tokens"] = len(tokens)
                if len(tokens) > self.limits.max_input_tokens:
                    raise PlannerStopped(
                        "context_limit", "Formatted planner input exceeds its token ceiling."
                    )
                body = self.runtime.post(
                    "/v1/chat/completions",
                    {
                        "model": self.model_id,
                        "messages": payload_messages,
                        "seed": self.seed,
                        "temperature": 0,
                        "max_tokens": min(64, self.limits.max_output_tokens),
                        "chat_template_kwargs": {"enable_thinking": False},
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "browser_decision",
                                "strict": True,
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "choice": {"type": "string", "enum": list(choices)},
                                    },
                                    "required": ["choice"],
                                },
                            },
                        },
                    },
                    timeout,
                )
            finally:
                self.runtime.lock.release()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or len(content) > 4096:
                raise PlannerStopped(
                    "invalid_model_output", "Model decision must be a bounded JSON string."
                )
            record["raw_output"] = redact(content)
            record["usage"] = {
                key: value
                for key, value in body.get("usage", {}).items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
            if body["choices"][0].get("finish_reason") == "length":
                raise PlannerStopped(
                    "invalid_model_output", "Model output reached its token ceiling."
                )
            decision = expand_choice(json.loads(content), choices)
            if self.stopped.is_set() or time.monotonic() >= self.deadline:
                raise PlannerStopped(
                    "runtime_limit", "Planner stopped before dispatching the generated action."
                )
            record["status"] = "valid"
            record["decision"] = decision.model_dump(mode="json")
            name = "final_answer" if decision.action.kind == "finish" else "browser_action"
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content=decision.rationale,
                tool_calls=[
                    ChatMessageToolCall(
                        id=str(decision.action.id),
                        type="function",
                        function=ChatMessageToolCallFunction(
                            name=name, arguments={"action": decision.action.model_dump(mode="json")}
                        ),
                    )
                ],
            )
        except PlannerStopped as exc:
            self.last_fault = exc
            record.update(status="failed", category=exc.category, reason=str(exc))
            raise
        except httpx.TimeoutException as exc:
            self.last_fault = PlannerStopped(
                "model_timeout", "Local model request timed out; no behavioral penalty applied."
            )
            record.update(
                status="failed", category=self.last_fault.category, reason=str(self.last_fault)
            )
            raise self.last_fault from exc
        except (
            httpx.HTTPError,
            ValidationError,
            ValueError,
            KeyError,
            TypeError,
            IndexError,
        ) as exc:
            category = (
                "model_memory_limit"
                if getattr(self.runtime, "memory_exceeded", False)
                else "model_provider_error"
                if isinstance(exc, httpx.HTTPError)
                else "invalid_model_output"
            )
            self.last_fault = PlannerStopped(
                category,
                f"Planner response rejected ({type(exc).__name__}); no UX diagnosis inferred.",
            )
            record.update(status="failed", category=category, reason=str(self.last_fault))
            raise self.last_fault from exc
        finally:
            record["inference_seconds"] = round(time.monotonic() - started, 6)
            self.records.append(record)
            self.writer.json("planner-decisions.json", self.records)


def launch_environment(runtime_directory=None):
    """Native runtime must not inherit keys, agent tools, proxies, or override settings."""
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    if os.name != "nt" and runtime_directory is not None:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            [str(runtime_directory), str(runtime_directory.parent / "lib")]
        )
    return environment
