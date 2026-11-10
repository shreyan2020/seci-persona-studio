# Runtime performance and resource ownership

## Implemented mechanisms

| Area | Mechanism | Bound / lifecycle |
|---|---|---|
| PDF verification | Group passages by SHA-256 in a dictionary; stream hashes; parse each matching original once; retain normalized text only for requested pages | Existing 8-finding / 20-passage limits; request-local data, no persistent PDF objects |
| Annotation | `try/finally` owns the PDF document; streaming source hash | Closes on success, model failure, and cancellation |
| Perspectives | Structured concurrency with `asyncio.TaskGroup`; merge results in role order, then run reviewer | Three children; parent cancellation cancels and joins children |
| Model HTTP generation | Shared semaphore | `OLLAMA_MAX_CONCURRENT_GENERATIONS=2` per client/process; semaphore released on failure/cancellation |
| Cached model work | Existing identical-request coalescing plus admission cap | `OLLAMA_MAX_INFLIGHT_REQUESTS=64` distinct cached tasks; duplicates join existing work even at capacity |
| Model cleanup | Synchronous completion callback removes task and observes failures; shutdown cancels and joins shared tasks before closing HTTP pool | No extra fire-and-forget cleanup tasks; closed clients cannot reopen connections |
| Application shutdown | Cancel and await execution tasks before closing model client | Prevents execution tasks outliving dependencies |
| UI polling | One pending request per polling effect; ignore obsolete responses; abort fetch on cleanup | Execution and report polling stop on navigation, run changes or unmount |

Normal Python/JavaScript garbage collection remains enabled. Explicit ownership releases file handles, requests and task references promptly; periodic forced collection is not introduced. Persisted project data, original PDFs and database caches are not deleted by this change.

## Benchmark

Run `python benchmark_pdf_verification.py` from `backend`.

The fixture contains one 41-page synthetic PDF and 20 distinct passages. The baseline reproduces the previous per-passage reopen/reference-scan strategy. Both paths must return the same ordered page/quote pairs. Seven repeated runs follow a correctness warm-up.

Observed local medians: previous 68.903 ms; optimized 4.050 ms; 17.01x improvement. This is a synthetic verification benchmark, not an end-to-end platform or real-model speed claim. Streaming hashing also avoids loading an entire PDF into a separate Python bytes object; native-library peak memory was not benchmarked.

## Configuration and limits

- Structured JSON generation explicitly sends `think: false`; ordinary text and tool-chat requests retain their existing thinking behavior. On local Ollama 0.34.2 with `qwen3.5:latest`, a small extraction using the previous request failed with `prediction aborted, token repeat limit reached`; the same prompt with thinking disabled returned valid JSON. A subsequent call through the actual structured PDF-note helper produced notes from a controlled excerpt. These probes establish runtime compatibility, not paper-level scientific accuracy. Empty structured answers now raise an explicit extraction error, and the JSON cache contract distinguishes the new generation mode.

- Limits are per application process, not a distributed limit across backend replicas and report workers. Docker Compose passes both settings to backend and worker.
- The cached-work admission cap does not cap all incoming HTTP handlers or uncached requests. Deployment-level admission control still matters under sustained overload.
- `OLLAMA_NUM_PARALLEL` controls model-server execution separately. Its current Compose default is 1. Concurrent application requests can therefore queue inside Ollama; model throughput improvements require hardware measurements before raising that setting.
- Existing `OLLAMA_KEEP_ALIVE=-1` deliberately keeps model weights resident for latency. Use a finite deployment setting such as `5m` if reclaiming idle model memory is preferred. This pass does not change existing deployments' residency policy.
- PDF parsing remains synchronous. A process-worker trial failed in the Windows integration environment and is not included; unsafe concurrent PDF parsing in threads is not used. Very large archives still require streaming every original's bytes to verify hashes. There is no persistent hash index that might skip detecting changed source bytes.
- Annotation still keeps its document open while awaiting extraction calls, but now always closes it on exit. Further process isolation and limits for concurrent annotation requests need workload measurements.
- Persisted board histories and database caches retain their existing lifecycle. Disk retention needs a separate policy that preserves source provenance and user decisions.

## Validation

Backend tests cover one PDF open for multiple passages, original source checks, annotation cleanup on model failure, role overlap/order, reviewer dependency, cancellation joining all roles, generation concurrency, coalescing at queue capacity and shutdown draining shared work. Existing comparison, PDF reuse and board mutation tests remain in the regression run. Frontend type checking and existing workflow tests also run; they do not constitute a browser stress test or a measured memory-leak soak test.
