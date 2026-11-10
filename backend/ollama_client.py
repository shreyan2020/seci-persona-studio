import asyncio
from collections import deque
from datetime import datetime, timezone
import hashlib
import inspect
import json
import logging
import math
import os
import time
import httpx
from typing import Optional, Dict, Any, List, Callable
from models import Objective, EvidenceItem

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen3.5:latest")
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        self._inflight: Dict[str, asyncio.Task] = {}
        self._inflight_lock = asyncio.Lock()
        self._closed = False
        self._max_inflight = max(1, int(os.getenv("OLLAMA_MAX_INFLIGHT_REQUESTS", "64")))
        self._generation_slots = asyncio.Semaphore(max(1, int(os.getenv("OLLAMA_MAX_CONCURRENT_GENERATIONS", "2"))))
        self._metrics = deque(maxlen=max(100, int(os.getenv("OLLAMA_METRICS_BUFFER_SIZE", "1000"))))

    async def start(self, *, preload: bool = False) -> None:
        await self._get_client()
        if preload:
            try:
                await self.generate("", temperature=0.0, top_p=1.0)
            except Exception as exc:
                logger.warning("Ollama preload failed; the first request will retry normally: %s", exc)

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._inflight.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._inflight.clear()
        async with self._client_lock:
            client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._closed:
            raise RuntimeError("Ollama client is closed")
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                max_connections = max(1, int(os.getenv("OLLAMA_HTTP_MAX_CONNECTIONS", "20")))
                self._client = httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=max_connections,
                        max_keepalive_connections=max_connections,
                        keepalive_expiry=60.0,
                    )
                )
            return self._client

    def _clear_inflight(self, cache_key: str, task: asyncio.Task) -> None:
        # Same event loop: no await or extra cleanup task is needed.
        if self._inflight.get(cache_key) is task:
            self._inflight.pop(cache_key, None)
        if not task.cancelled():
            task.exception()  # Observe failures even if every waiter disconnected.

    def _keep_alive(self) -> Any:
        value = os.getenv("OLLAMA_KEEP_ALIVE", "-1").strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return value

    def _timeout(self, timeout_seconds: Optional[float] = None) -> httpx.Timeout:
        raw = timeout_seconds if timeout_seconds is not None else os.getenv("OLLAMA_TIMEOUT_SECONDS", "90")
        try:
            total = max(5.0, float(raw))
        except (TypeError, ValueError):
            total = 90.0
        return httpx.Timeout(total, connect=min(10.0, total))

    def _record_metric(
        self,
        *,
        operation: str,
        payload: Dict[str, Any],
        elapsed_ms: float,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        cache_status: Optional[str] = None,
    ) -> None:
        result = result or {}
        prompt_tokens = int(result.get("prompt_eval_count") or 0)
        output_tokens = int(result.get("eval_count") or 0)
        prompt_ms = float(result.get("prompt_eval_duration") or 0) / 1_000_000
        eval_ms = float(result.get("eval_duration") or 0) / 1_000_000
        metric = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "model": payload.get("model") or self.model,
            "elapsed_ms": round(elapsed_ms, 3),
            "load_ms": round(float(result.get("load_duration") or 0) / 1_000_000, 3),
            "prompt_eval_ms": round(prompt_ms, 3),
            "eval_ms": round(eval_ms, 3),
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "prompt_tokens_per_second": round(prompt_tokens * 1000 / prompt_ms, 3) if prompt_ms else None,
            "output_tokens_per_second": round(output_tokens * 1000 / eval_ms, 3) if eval_ms else None,
            "cache_status": cache_status,
            "error": error,
        }
        self._metrics.append(metric)
        logger.info("llm_inference_metric %s", json.dumps(metric, separators=(",", ":")))

    def metrics_snapshot(self) -> Dict[str, Any]:
        rows = list(self._metrics)
        completed = [row for row in rows if not row.get("error")]
        cache_hits = sum(row.get("cache_status") == "hit" for row in rows)
        cache_misses = sum(row.get("cache_status") == "miss" for row in rows)

        def percentile(values: List[float], fraction: float) -> Optional[float]:
            if not values:
                return None
            ordered = sorted(values)
            index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
            return round(ordered[index], 3)

        durations = [float(row["elapsed_ms"]) for row in completed if row.get("cache_status") is None]
        return {
            "model": self.model,
            "samples": len(rows),
            "requests": len(durations),
            "errors": sum(bool(row.get("error")) for row in rows),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": round(cache_hits / (cache_hits + cache_misses), 4) if cache_hits + cache_misses else None,
            "latency_ms": {
                "p50": percentile(durations, 0.50),
                "p95": percentile(durations, 0.95),
            },
            "recent": rows[-25:],
        }

    async def _post_json(
        self,
        path: str,
        payload: Dict[str, Any],
        *,
        operation: str,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            async with self._generation_slots:
                client = await self._get_client()
                response = await client.post(
                    f"{self.base_url}{path}",
                    json=payload,
                    timeout=self._timeout(timeout_seconds),
                )
            response.raise_for_status()
            result = response.json()
            self._record_metric(
                operation=operation,
                payload=payload,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                result=result,
            )
            return result
        except Exception as exc:
            self._record_metric(
                operation=operation,
                payload=payload,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    async def _resolve_installed_model(self, requested_model: str) -> Optional[str]:
        """Resolve a missing Ollama tag to an installed tag from the same model family."""
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/api/tags",
            timeout=self._timeout(15),
        )
        response.raise_for_status()
        installed = sorted(
            str(item.get("name") or item.get("model") or "").strip()
            for item in response.json().get("models", [])
        )
        installed = [name for name in installed if name]
        family = requested_model.split(":", 1)[0].removesuffix("-instruct")
        preferred = [
            requested_model.removesuffix("-instruct"),
            f"{family}:latest",
        ]
        for candidate in preferred:
            if candidate in installed:
                return candidate
        family_matches = [name for name in installed if name.split(":", 1)[0] == family]
        return family_matches[0] if family_matches else None
    
    async def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        format_json: bool = False,
        num_predict: Optional[int] = None,
        num_ctx: Optional[int] = None,
    ) -> str:
        """Generate text from Ollama model."""
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p
            }
        }
        requested_context = num_ctx or os.getenv("OLLAMA_NUM_CTX")
        if requested_context is not None:
            payload["options"]["num_ctx"] = max(2048, min(int(requested_context), 131072))
        if num_predict is not None:
            payload["options"]["num_predict"] = max(1, int(num_predict))
        keep_alive = self._keep_alive()
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        if format_json:
            payload["format"] = "json"
            # Structured extraction needs the final JSON within its token/time budget.
            # Qwen3.5 can otherwise loop in thinking before producing any answer.
            payload["think"] = False
        
        try:
            result = await self._post_json(
                "/api/generate", payload, operation="generate", timeout_seconds=timeout_seconds
            )
        except httpx.HTTPStatusError as exc:
            active_model = model or self.model
            if exc.response.status_code != 404:
                raise
            fallback_model = await self._resolve_installed_model(active_model)
            if not fallback_model or fallback_model == active_model:
                raise
            logger.warning(
                "Ollama model %s is not installed; using equivalent installed tag %s",
                active_model,
                fallback_model,
            )
            payload["model"] = fallback_model
            result = await self._post_json(
                "/api/generate", payload, operation="generate_fallback", timeout_seconds=timeout_seconds
            )
            if model is None:
                self.model = fallback_model
        answer = result.get("response", "")
        if format_json and (not isinstance(answer, str) or not answer.strip()):
            raise ValueError(
                f"Structured extraction returned no answer from {payload['model']} "
                f"(done_reason={result.get('done_reason', 'unknown')}). "
                "No notes were extracted; retry after checking the model runtime."
            )
        return answer
    
    async def generate_json(
        self,
        prompt: str,
        max_retries: int = 1,
        temperature: float = 0.7,
        top_p: float = 0.9,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        num_predict: Optional[int] = None,
        num_ctx: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate and parse JSON from Ollama with retry logic."""
        initial_prompt = f"{prompt}\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no code blocks, no explanation."
        response_text = ""
        
        for attempt in range(max_retries + 1):
            if attempt == 0:
                response_text = await self.generate(
                    initial_prompt,
                    temperature=temperature,
                    top_p=top_p,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    format_json=True,
                    num_predict=num_predict,
                    **({"num_ctx": num_ctx} if num_ctx is not None else {}),
                )
            else:
                retry_prompt = f"{initial_prompt}\n\nYour previous output was invalid JSON. Please fix it and return ONLY valid JSON.\n\nPrevious invalid output:\n{response_text}"
                response_text = await self.generate(
                    retry_prompt,
                    temperature=temperature,
                    top_p=top_p,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    format_json=True,
                    num_predict=num_predict,
                    **({"num_ctx": num_ctx} if num_ctx is not None else {}),
                )
            
            try:
                return self._extract_json(response_text)
            except json.JSONDecodeError as e:
                print(f"DEBUG: JSON parse error on attempt {attempt + 1}: {e}")
                print(f"DEBUG: Response text: {response_text[:500]}...")
                if attempt == max_retries:
                    raise ValueError(f"Failed to parse JSON after {max_retries + 1} attempts. Last error: {e}. Response: {response_text[:200]}") from e
                continue
        
        raise ValueError("Unexpected error in JSON generation")

    async def generate_json_cached(
        self,
        *,
        cache: Any,
        task_type: str,
        prompt: str,
        cache_version: int = 1,
        cache_inputs: Optional[Dict[str, Any]] = None,
        max_retries: int = 1,
        temperature: float = 0.2,
        top_p: float = 0.9,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        num_predict: Optional[int] = None,
        num_ctx: Optional[int] = None,
    ) -> Dict[str, Any]:
        active_model = model or self.model
        key_inputs = {
            "version": cache_version,
            "structured_generation_contract": 2,
            "think": False,
            "model": active_model,
            "model_revision": os.getenv("OLLAMA_MODEL_REVISION", ""),
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": num_predict,
            "num_ctx": num_ctx or os.getenv("OLLAMA_NUM_CTX"),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "inputs": cache_inputs or {},
        }
        cache_key = cache.llm_cache_key(task_type, key_inputs)
        cached = cache.get_llm_cache(cache_key)
        if cached is not None:
            self._record_metric(
                operation=task_type,
                payload={"model": active_model},
                elapsed_ms=0.0,
                cache_status="hit",
            )
            return cached.get("payload") or {}

        self._record_metric(
            operation=task_type,
            payload={"model": active_model},
            elapsed_ms=0.0,
            cache_status="miss",
        )
        async with self._inflight_lock:
            if self._closed:
                raise RuntimeError("Ollama client is closed")
            task = self._inflight.get(cache_key)
            if task is None:
                if len(self._inflight) >= self._max_inflight:
                    raise RuntimeError("Model request queue is full; retry after current requests finish")
                async def generate_and_store() -> Dict[str, Any]:
                    payload = await self.generate_json(
                        prompt,
                        max_retries=max_retries,
                        temperature=temperature,
                        top_p=top_p,
                        model=model,
                        timeout_seconds=timeout_seconds,
                        num_predict=num_predict,
                        **({"num_ctx": num_ctx} if num_ctx is not None else {}),
                    )
                    cache.upsert_llm_cache(
                        cache_key=cache_key,
                        task_type=task_type,
                        model=active_model,
                        payload=payload,
                        metadata={
                            "cache_version": cache_version,
                            "model_revision": os.getenv("OLLAMA_MODEL_REVISION", ""),
                        },
                    )
                    return payload

                task = asyncio.create_task(generate_and_store())
                self._inflight[cache_key] = task
                task.add_done_callback(
                    lambda completed, key=cache_key: self._clear_inflight(key, completed)
                )
        return await asyncio.shield(task)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        top_p: float = 0.9,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
            },
        }
        if tools:
            payload["tools"] = tools

        keep_alive = self._keep_alive()
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        return await self._post_json(
            "/api/chat", payload, operation="chat", timeout_seconds=timeout_seconds
        )

    async def run_tool_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        tool_handlers: Dict[str, Callable[..., Any]],
        model: Optional[str] = None,
        max_rounds: int = 4,
        temperature: float = 0.2,
        top_p: float = 0.9,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": user_prompt.strip()})

        for _ in range(max_rounds):
            response = await self.chat(
                messages=messages,
                tools=tools,
                temperature=temperature,
                top_p=top_p,
                model=model,
            )
            message = response.get("message") or {}
            assistant_message = {
                "role": "assistant",
                "content": message.get("content") or "",
            }
            if message.get("thinking"):
                assistant_message["thinking"] = message.get("thinking")
            if message.get("tool_calls"):
                assistant_message["tool_calls"] = message.get("tool_calls")
            messages.append(assistant_message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                break

            for call in tool_calls:
                function = call.get("function") or {}
                name = str(function.get("name") or "").strip()
                raw_arguments = function.get("arguments") or {}
                if isinstance(raw_arguments, str):
                    try:
                        raw_arguments = json.loads(raw_arguments)
                    except json.JSONDecodeError:
                        raw_arguments = {}
                handler = tool_handlers.get(name)
                if not handler:
                    result: Any = {"error": f"unknown_tool:{name}"}
                else:
                    try:
                        if inspect.iscoroutinefunction(handler):
                            result = await handler(**raw_arguments)
                        else:
                            result = handler(**raw_arguments)
                    except Exception as exc:
                        result = {"error": str(exc)}
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(result),
                    }
                )

        return messages

    def collect_tool_messages(self, messages: List[Dict[str, Any]]) -> str:
        chunks: List[str] = []
        for message in messages:
            if message.get("role") != "tool":
                continue
            name = str(message.get("tool_name") or "tool").strip()
            content = str(message.get("content") or "").strip()
            if not content:
                continue
            chunks.append(f"Tool {name} result:\n{content}")
        return "\n\n".join(chunks)

    async def ollama_generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        json_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        schema_hint = ""
        if json_schema is not None:
            schema_hint = f"\nJSON Schema hint:\n{json.dumps(json_schema)}"
        full_prompt = (
            f"{prompt}{schema_hint}\n\n"
            "Return ONLY valid JSON. No prose."
        )
        text = await self.generate(full_prompt, temperature=temperature)
        return self._extract_json(text)

    def _extract_json(self, response_text: str) -> Dict[str, Any]:
        json_part = response_text.strip()
        if "```json" in json_part:
            json_part = json_part.split("```json")[1].split("```")[0].strip()
        elif "```" in json_part:
            json_part = json_part.split("```")[1].split("```")[0].strip()

        if not json_part.startswith(("{", "[")):
            start_idx = min(
                (json_part.find("{") if json_part.find("{") != -1 else len(json_part)),
                (json_part.find("[") if json_part.find("[") != -1 else len(json_part)),
            )
            if start_idx < len(json_part):
                json_part = json_part[start_idx:]

        if json_part.startswith("{"):
            brace_count = 0
            for i, char in enumerate(json_part):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_part = json_part[: i + 1]
                        break

        parsed = json.loads(json_part)
        if not isinstance(parsed, dict):
            raise json.JSONDecodeError("Expected JSON object", json_part, 0)
        return parsed
    
    def get_objectives_prompt(self, query: str, context: Optional[str] = None, k: int = 5) -> str:
        """Generate the prompt for objective generation."""
        context_part = f"Context: {context}\n\n" if context else ""
        
        return f"""You are an expert at interpreting underspecified user queries.
{context_part}User query: "{query}"

Task:
Generate {k} distinct objectives that could represent different interpretations of what 'best' means.
For each objective, provide:
- id: obj_1..obj_{k}
- title: 2-5 words
- subtitle: what's user is trying to achieve
- definition: 2-4 lines describing the goal
- signals: 4-10 indicative keywords
- facet_questions: 2-4 clarifying questions
- exemplar_answer: 5-10 lines

Also provide 2-4 global questions broadly useful across objectives.

Return ONLY valid JSON with this structure:
{{
    "objectives": [
        {{
            "id": "obj_1",
            "title": "title here",
            "subtitle": "subtitle here",
            "definition": "definition here",
            "signals": ["signal1", "signal2"],
            "facet_questions": ["question1", "question2"],
            "exemplar_answer": "answer here"
        }}
    ],
    "global_questions": ["question1", "question2"]
}}

Return ONLY valid JSON. No markdown, no code blocks."""
    
    def get_augment_prompt(self, query: str, objective_id: str, objective_definition: str, context_blob: str) -> str:
        """Generate the prompt for evidence augmentation."""
        return f"""You are an expert at incorporating external evidence to improve answers based on specific objectives.

Query: "{query}"
Selected objective: {objective_id}
Objective definition: "{objective_definition}"

User context/evidence: "{context_blob}"

Your task:
1. Extract 3-7 evidence bullet points from the context that are most relevant to this objective
2. Rewrite or enhance an answer to incorporate this evidence
3. Return your response as valid JSON

Structure:
{{
    "evidence_items": [
        {{
            "id": "ev_1",
            "type": "note",
            "title": "short descriptive title",
            "snippet": "relevant excerpt from context",
            "source_ref": "user_context",
            "score": 1.0
        }}
    ],
    "augmented_answer": "updated answer using the evidence (or null if no context provided)"
}}

Return ONLY valid JSON. No markdown, no code blocks."""
    
    def get_finalize_prompt(self, query: str, objective: Objective, answers: Dict[str, str], 
                          evidence_items: Optional[List[EvidenceItem]] = None) -> str:
        """Generate the prompt for final answer synthesis."""
        evidence_text = ""
        if evidence_items:
            evidence_snippets = [item.snippet for item in evidence_items]
            evidence_text = "\nEvidence to incorporate:\n" + "\n".join(f"- {snippet}" for snippet in evidence_snippets)
        
        facet_answers_text = "\n".join(f"- {question}: {answer}" for question, answer in answers.items())
        
        return f"""You are an expert at synthesizing comprehensive answers based on clarified objectives and user preferences.

Query: "{query}"
Selected objective: {objective.title} ({objective.subtitle})
Objective definition: "{objective.definition}"

User's answers to facet questions:
{facet_answers_text}{evidence_text}

Generate a final answer that:
1. Is consistent with the selected objective
2. Incorporates the user's specific answers to facet questions
3. Uses the evidence if provided
4. Clearly states any assumptions made
5. Suggests relevant follow-up questions

Return your response as valid JSON:
{{
    "final_answer": "comprehensive answer addressing the query",
    "assumptions": ["assumption1", "assumption2"],
    "next_questions": ["followup1", "followup2"]
}}

Return ONLY valid JSON. No markdown, no code blocks."""

    def get_agentic_plan_prompt(
        self,
        query: str,
        objective: Objective,
        persona_summary: str,
        facet_answers: Dict[str, str],
        context_blob: Optional[str] = None,
    ) -> str:
        facet_block = "\n".join(f"- {k}: {v}" for k, v in facet_answers.items()) if facet_answers else "- none"
        context_block = context_blob.strip() if context_blob else "none"

        return f"""You are an elite planning agent. Build an actionable, evidence-aware execution plan.

User query: "{query}"
Selected objective cluster:
- id: {objective.id}
- title: {objective.title}
- subtitle: {objective.subtitle}
- definition: {objective.definition}
- signals: {", ".join(objective.signals)}

Persona summary:
{persona_summary}

Facet answers:
{facet_block}

Additional context:
{context_block}

Planning requirements:
1) Produce a concrete multi-step plan (5-9 steps) that serves the selected objective.
2) Explain WHY each step was chosen and how it maps to objective + persona.
3) Include examples or factual anchors per step.
4) Include dependencies, expected outcomes, and confidence (0..1) for each step.
5) Include risks + mitigations and measurable success criteria.
6) Keep text concise but specific.

Return ONLY valid JSON using this exact shape:
{{
  "plan": {{
    "plan_title": "string",
    "strategy_summary": "string",
    "success_criteria": ["string"],
    "assumptions": ["string"],
    "risks": [{{"risk": "string", "mitigation": "string"}}],
    "steps": [
      {{
        "id": "step_1",
        "title": "string",
        "description": "string",
        "why_this_step": "string",
        "objective_link": "string",
        "persona_link": "string",
        "evidence_facts": ["string"],
        "examples": ["string"],
        "dependencies": ["step_1"],
        "source_refs": ["S1 or citation/source id"],
        "gap_refs": ["gap id or gap theme"],
        "judgment_refs": ["judgment id or stance"],
        "validation_refs": ["validation id, target, method, or tool result"],
        "expected_outcome": "string",
        "confidence": 0.75
      }}
    ]
  }}
}}

Return ONLY valid JSON. No markdown, no code blocks."""

    def get_project_persona_generation_prompt(self, project: Dict[str, Any]) -> str:
        return f"""You are designing a product-specific biotech project team.

Project brief:
- name: {project.get("name")}
- end_product: {project.get("end_product")}
- target_host: {project.get("target_host")}
- project_goal: {project.get("project_goal")}
- raw_material_focus: {project.get("raw_material_focus") or "none"}
- notes: {project.get("notes") or "none"}

Task:
Generate 4 to 6 distinct personas tailored to THIS product program. They should collectively cover the full workflow,
including raw materials or sourcing, strain/pathway design, upstream process, downstream recovery, and economics or program gating.
Make the personas product-specific when the brief suggests a specialized concern. For example, if the product implies precursor,
toxicity, extraction, purification, or formulation issues, reflect that in the persona names and focus areas.
Include one persona that is explicitly strong at literature, benchmark, or evidence synthesis so the team can answer questions
about successful strategies, examples, latest improvement options, and open technical challenges.

Allowed workflow_stage values:
- feedstock
- strain_engineering
- upstream_process
- downstream_processing
- economics
- regulatory_quality
- analytics

Enum rules:
- domain_expertise values must be one of: novice, intermediate, expert, unknown
- time_sensitivity, risk_tolerance, citation_need, verbosity must be one of: low, medium, high, unknown
- compliance_posture must be one of: flexible, moderate, strict, unknown
- output_format must be one of: steps, table, narrative, mixed, unknown
- decision_style must be one of: exploratory, confirmatory, production, unknown
- default_reliance must be one of: low, medium, high, unknown

Return ONLY valid JSON with this exact structure:
{{
  "personas": [
    {{
      "name": "string",
      "workflow_stage": "feedstock",
      "focus_area": "string",
      "starter_questions": ["string", "string"],
      "role": "string",
      "domain_expertise": {{"biotech": "expert", "stats": "intermediate", "coding": "unknown"}},
      "goals": ["string", "string", "string"],
      "constraints": {{"time_sensitivity": "medium", "compliance_posture": "moderate", "risk_tolerance": "medium"}},
      "preferences": {{"output_format": "mixed", "citation_need": "medium", "verbosity": "medium"}},
      "decision_style": "production",
      "trust_profile": {{"default_reliance": "medium", "verification_habits": ["string", "string"]}},
      "taboo_or_redlines": ["string"],
      "workflow_focus": ["string", "string", "string"]
    }}
  ]
}}

Requirements:
1) Every persona must have a concrete name, not a generic label like Persona 1.
2) Keep the team tightly tied to the product brief.
3) Use short, operational focus areas and starter questions.
4) Ensure the set of personas covers the full workflow without near-duplicates.
5) At least one persona should use workflow_stage="analytics" and focus on literature or benchmark reasoning.

Return ONLY valid JSON. No markdown, no code blocks."""

    def get_project_plan_prompt(
        self,
        project: Dict[str, Any],
        persona_summary: str,
        focus_question: Optional[str] = None,
        notes: Optional[str] = None,
        clarifying_answers: Optional[Dict[str, str]] = None,
        reasoning_notes: Optional[str] = None,
        work_template_summary: Optional[str] = None,
    ) -> str:
        focus = focus_question.strip() if focus_question else "Build the highest-leverage next-step workflow for this program."
        note_block = notes.strip() if notes else "none"
        answer_block = (
            "\n".join(f"- {question}: {answer}" for question, answer in (clarifying_answers or {}).items() if str(answer or "").strip())
            or "none"
        )
        reasoning_block = reasoning_notes.strip() if reasoning_notes else "none"
        work_template_block = work_template_summary.strip() if work_template_summary else "none"

        return f"""You are an elite biotech collaboration agent. Build an editable, concrete working draft.

Project:
- name: {project.get("name")}
- end_product: {project.get("end_product")}
- target_host: {project.get("target_host")}
- project_goal: {project.get("project_goal")}
- raw_material_focus: {project.get("raw_material_focus") or "none"}
- notes: {project.get("notes") or "none"}

Selected planning focus:
{focus}

Persona summary:
{persona_summary}

Clarifying answers:
{answer_block}

Current user reasoning or synthesis:
{reasoning_block}

Structured research work template:
{work_template_block}

Project context and constraints:
{note_block}

Planning requirements:
1) Let the working question determine scope. Do NOT force the full biotech workflow if the question is narrower.
2) Use the persona as a collaborator lens, not a reason to inject unrelated sections.
3) Only include raw materials, sourcing, or cost analysis if the question explicitly asks for it, the project context highlights it, or it is a true blocking dependency.
4) If the working question is about literature, benchmarks, examples, latest improvement options, or open questions, produce an evidence-synthesis draft:
   - scope the search/problem framing
   - identify comparison axes
   - extract successful strategies and benchmark examples
   - map bottlenecks, open questions, and future improvement options
   - convert those findings into next experiments or decisions
5) If the working question is about an experiment plan, focus on hypotheses, interventions, measurements, controls, and decision gates.
6) If the working question is about process or scale-up, focus on operating variables, DOE structure, and transition criteria.
7) Make each step actionable for a biotech program team, not generic advice.
8) Include factual anchors, examples, dependencies, expected outcomes, and confidence (0..1).
9) Include risks, mitigations, and measurable success criteria.
10) Surface assumptions explicitly, especially where data is missing.
11) If a structured research work template is provided, preserve its logic:
   - keep the known vs unknown split visible
   - honor explicit exclusions or boundary conditions from the user
   - translate validation tracks into decision-useful experiments or analyses
   - carry promising proposal seeds forward instead of restarting from zero
12) When the template references analog compounds, neighboring conditions, or transferable examples, state the generalization assumptions explicitly.
13) Make traceability explicit. For every step, include the paper/source refs, gap refs, user judgment refs, and validation refs that justify the step. If a ref is unavailable, leave that array empty rather than inventing a source.

Return ONLY valid JSON using this exact shape:
{{
  "plan": {{
    "plan_title": "string",
    "strategy_summary": "string",
    "success_criteria": ["string"],
    "assumptions": ["string"],
    "risks": [{{"risk": "string", "mitigation": "string"}}],
    "steps": [
      {{
        "id": "step_1",
        "title": "string",
        "description": "string",
        "why_this_step": "string",
        "objective_link": "string",
        "persona_link": "string",
        "evidence_facts": ["string"],
        "examples": ["string"],
        "dependencies": ["step_1"],
        "source_refs": ["S1 or citation/source id"],
        "gap_refs": ["gap id or gap theme"],
        "judgment_refs": ["judgment id or stance"],
        "validation_refs": ["validation id, target, method, or tool result"],
        "expected_outcome": "string",
        "confidence": 0.75
      }}
    ]
  }}
}}

Return ONLY valid JSON. No markdown, no code blocks."""

    def get_persona_refactor_prompt(
        self,
        current_persona_json: Dict[str, Any],
        current_summary: str,
        interaction_events: List[Dict[str, Any]],
    ) -> str:
        compact_events = json.dumps(interaction_events[:200])
        return f"""You are a persona-learning agent.

Task: infer how the user actually behaves from interaction telemetry and explicit feedback,
then output an updated persona JSON following the exact schema below.

Current persona summary:
{current_summary}

Current persona JSON:
{json.dumps(current_persona_json)}

Interaction events (clicks, searches, objective choices, answers, feedback):
{compact_events}

Rules:
1) Prefer explicit feedback over implicit behavior.
2) Update only fields supported by event evidence.
3) Keep unknown when weak evidence.
4) Maintain consistency and provenance-friendly claims.

Return ONLY valid JSON in this shape:
{{
  "persona": {{
    "persona_id": "string",
    "scope_id": "string",
    "role": "string|unknown",
    "domain_expertise": {{"biotech": "novice|intermediate|expert|unknown", "stats": "novice|intermediate|expert|unknown", "coding": "novice|intermediate|expert|unknown"}},
    "goals": ["string"],
    "constraints": {{"time_sensitivity": "low|medium|high|unknown", "compliance_posture": "strict|moderate|flexible|unknown", "risk_tolerance": "low|medium|high|unknown"}},
    "preferences": {{"output_format": "steps|table|narrative|mixed|unknown", "citation_need": "low|medium|high|unknown", "verbosity": "low|medium|high|unknown"}},
    "decision_style": "exploratory|confirmatory|production|unknown",
    "trust_profile": {{"default_reliance": "low|medium|high|unknown", "verification_habits": ["string"]}},
    "taboo_or_redlines": ["string"],
    "key_quotes": [{{"quote": "string", "interview_id": 0}}],
    "evidence": {{"support": [{{"claim": "string", "interview_id": 0, "span_hint": "event"}}]}}
  }},
  "learning_summary": "string"
}}

Return JSON only."""

# Global Ollama client
ollama = OllamaClient()
