import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock

import httpx
from unittest.mock import AsyncMock, patch

import httpx

from ollama_client import OllamaClient


class MemoryCache:
    def __init__(self):
        self.rows = {}
        self.writes = 0

    def llm_cache_key(self, task_type, inputs):
        return f"{task_type}:{inputs['prompt_sha256']}"

    def get_llm_cache(self, cache_key):
        return self.rows.get(cache_key)

    def upsert_llm_cache(self, *, cache_key, task_type, model, payload, metadata=None):
        self.writes += 1
        self.rows[cache_key] = {"payload": payload, "metadata": metadata or {}}


class OllamaClientPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_extraction_disables_thinking(self):
        client = OllamaClient(model="qwen3.5:latest")
        client._post_json = AsyncMock(return_value={"response": '{"notes":["Measured glucose"]}'})
        result = await client.generate_json("Extract notes", num_predict=256)
        payload = client._post_json.await_args.args[1]
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["format"], "json")
        self.assertEqual(payload["options"]["num_predict"], 256)
        self.assertEqual(result["notes"], ["Measured glucose"])

    async def test_plain_generation_preserves_model_thinking_default(self):
        client = OllamaClient()
        client._post_json = AsyncMock(return_value={"response": "answer"})
        await client.generate("Explain")
        self.assertNotIn("think", client._post_json.await_args.args[1])

    async def test_empty_structured_answer_is_an_explicit_failure(self):
        client = OllamaClient(model="qwen3.5:latest")
        client._post_json = AsyncMock(return_value={
            "response": "", "thinking": "internal content", "done_reason": "length",
        })
        with self.assertRaisesRegex(ValueError, "Structured extraction returned no answer") as error:
            await client.generate_json("Extract notes")
        self.assertNotIn("internal content", str(error.exception))

    async def test_generate_resolves_missing_model_to_same_family_latest_tag(self):
        client = OllamaClient(model="qwen2.5:7b")
        missing_request = httpx.Request("POST", "http://localhost:11434/api/generate")
        missing_response = httpx.Response(404, request=missing_request)
        client._post_json = AsyncMock(
            side_effect=[
                httpx.HTTPStatusError("missing", request=missing_request, response=missing_response),
                {"response": "grounded"},
            ]
        )
        tags_response = Mock()
        tags_response.raise_for_status.return_value = None
        tags_response.json.return_value = {
            "models": [{"name": "qwen3.5:latest"}, {"name": "qwen2.5:latest"}]
        }
        http_client = AsyncMock()
        http_client.get.return_value = tags_response
        client._get_client = AsyncMock(return_value=http_client)

        result = await client.generate("test", temperature=0.0)

        self.assertEqual(result, "grounded")
        self.assertEqual(client.model, "qwen2.5:latest")
        self.assertEqual(client._post_json.await_args_list[1].args[1]["model"], "qwen2.5:latest")

    async def test_generate_uses_pooled_client_keep_alive_and_records_metrics(self):
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "response": "ok",
                    "load_duration": 2_000_000,
                    "prompt_eval_count": 20,
                    "prompt_eval_duration": 10_000_000,
                    "eval_count": 10,
                    "eval_duration": 20_000_000,
                },
            )

        client = OllamaClient(base_url="http://ollama.test", model="test-model")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch.dict(os.environ, {"OLLAMA_KEEP_ALIVE": "-1"}):
            self.assertEqual(await client.generate("first"), "ok")
            self.assertEqual(await client.generate("second"), "ok")

        self.assertEqual(len(requests), 2)
        self.assertTrue(all(request.extensions.get("timeout") for request in requests))
        self.assertTrue(all(b'"keep_alive":-1' in request.content for request in requests))
        snapshot = client.metrics_snapshot()
        self.assertEqual(snapshot["requests"], 2)
        self.assertEqual(snapshot["recent"][-1]["output_tokens_per_second"], 500.0)
        await client.close()

    async def test_identical_cached_requests_are_coalesced(self):
        cache = MemoryCache()
        client = OllamaClient(model="test-model")
        generated = {"answer": "stable"}

        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(0.01)
            return generated

        client.generate_json = AsyncMock(side_effect=slow_generate)
        first, second = await asyncio.gather(
            client.generate_json_cached(cache=cache, task_type="scope", prompt="same prompt"),
            client.generate_json_cached(cache=cache, task_type="scope", prompt="same prompt"),
        )
        await asyncio.sleep(0)

        self.assertEqual(first, generated)
        self.assertEqual(second, generated)
        self.assertEqual(client.generate_json.await_count, 1)
        self.assertEqual(cache.writes, 1)
        self.assertEqual(client.metrics_snapshot()["cache_misses"], 2)

        cached = await client.generate_json_cached(cache=cache, task_type="scope", prompt="same prompt")
        self.assertEqual(cached, generated)
        self.assertEqual(client.generate_json.await_count, 1)
        self.assertEqual(client.metrics_snapshot()["cache_hits"], 1)

    async def test_generation_concurrency_is_bounded(self):
        active = peak = 0
        async def handler(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.01)
                return httpx.Response(200, json={"response": "ok"})
            finally:
                active -= 1
        with patch.dict(os.environ, {"OLLAMA_MAX_CONCURRENT_GENERATIONS": "2"}):
            client = OllamaClient()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await asyncio.gather(*(client.generate(str(i)) for i in range(8)))
        self.assertEqual(peak, 2)
        await client.close()

    async def test_shutdown_drains_shared_work_and_rejects_new_work(self):
        client = OllamaClient()
        started = asyncio.Event()
        stopped = asyncio.Event()
        async def generation(*args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        client.generate_json = generation
        waiter = asyncio.create_task(client.generate_json_cached(cache=MemoryCache(), task_type="test", prompt="pending"))
        await started.wait()
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        self.assertFalse(stopped.is_set())  # One waiter cannot cancel shared work.
        await client.close()
        self.assertTrue(stopped.is_set())
        self.assertFalse(client._inflight)
        with self.assertRaises(RuntimeError):
            await client._get_client()

    async def test_queue_limit_keeps_duplicate_coalescing(self):
        with patch.dict(os.environ, {"OLLAMA_MAX_INFLIGHT_REQUESTS": "1"}):
            client = OllamaClient()
        gate = asyncio.Event()
        client.generate_json = AsyncMock(side_effect=lambda *a, **kw: None)
        async def generation(*args, **kwargs):
            await gate.wait()
            return {"ok": True}
        client.generate_json = generation
        cache = MemoryCache()
        first = asyncio.create_task(client.generate_json_cached(cache=cache, task_type="test", prompt="first"))
        await asyncio.sleep(0)
        duplicate = asyncio.create_task(client.generate_json_cached(cache=cache, task_type="test", prompt="first"))
        await asyncio.sleep(0)
        with self.assertRaisesRegex(RuntimeError, "queue is full"):
            await client.generate_json_cached(cache=cache, task_type="test", prompt="second")
        gate.set()
        self.assertEqual(await first, await duplicate)
        self.assertEqual(cache.writes, 1)
        await client.close()


if __name__ == "__main__":
    unittest.main()
