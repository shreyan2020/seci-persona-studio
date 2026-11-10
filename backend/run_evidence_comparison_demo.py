"""Reproduce extraction on previously verified real PDFs, without editing a project."""
import asyncio
import json
from pathlib import Path
from research_board import ResearchBoard, verified_pdf_evidence
from evidence_comparison import build_comparison
from ollama_client import ollama

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/evidence_comparison_live'

async def main():
    if OUT.exists():
        raise ValueError('Keep prior results; use a new output path for another run.')
    OUT.mkdir(parents=True)
    source = ROOT / 'artifacts/research_board_verified_live'
    board = ResearchBoard.model_validate_json((source/'board_before_answer.json').read_text(encoding='utf-8'))
    state = json.loads((source/'workspace.json').read_text(encoding='utf-8'))
    evidence = verified_pdf_evidence(state, ROOT/'backend/data/paper_evidence')
    calls = 0
    async def generate(prompt, **kwargs):
        nonlocal calls
        calls += 1
        print(f'Extracting source {calls}',flush=True)
        result = await ollama.generate_json(prompt,num_ctx=8192,**kwargs)
        (OUT/f'call_{calls}.json').write_text(json.dumps({'prompt':prompt,'response':result,'model':ollama.model,'num_ctx':8192},indent=2),encoding='utf-8')
        return result
    result = await build_comparison(board,evidence,generate)
    (OUT/'board.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
    print(json.dumps({'verified_passages':len(evidence),'source_calls':calls,
                      'facts':len(result.experiment_facts),'experiments':len(result.experiment_records),
                      'unresolved':sum(r.link_status == 'unresolved' for r in result.experiment_records),
                      'warnings':result.comparison_warnings}),flush=True)
    await ollama.close()

if __name__ == '__main__':
    asyncio.run(main())
