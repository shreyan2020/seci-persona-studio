"""Optional task-specific Ollama models; share the existing queue and client."""
import os


def model_options(task):
    names = {
        'extraction': 'OLLAMA_EXTRACTION_MODEL',
        'perspective': 'OLLAMA_PERSPECTIVE_MODEL',
        'review': 'OLLAMA_REVIEW_MODEL',
    }
    model = os.getenv(names[task], '').strip()
    return {'model': model} if model else {}
