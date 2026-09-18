"""Measure extraction accuracy against the golden set.

    python -m pipeline.eval.run_eval                     # the model from .env
    python -m pipeline.eval.run_eval gemma-4-31b-it      # compare another model
    python -m pipeline.eval.run_eval --verbose           # list every disagreement

Sends each labelled posting through the production prompt and scores the answer. Uses the
same pacing as a real run, but does not touch the daily quota counter or store anything:
an evaluation is a measurement, not part of the pipeline's output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pipeline.config import require_env
from pipeline.eval.score import Report, score
from pipeline.extract.llm import GeminiBackend, ModelError
from pipeline.extract.prompt import build_prompt, response_schema
from pipeline.extract.quota import Pacer
from pipeline.extract.schema import Extraction
from pipeline.http import HttpError, make_client

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.jsonl"


def load_golden_set() -> list[dict[str, Any]]:
    if not GOLDEN_SET_PATH.exists():
        raise RuntimeError("No golden set yet. Run: python -m pipeline.eval.build_golden_set")
    with GOLDEN_SET_PATH.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def evaluate(model: str, postings: list[dict[str, Any]]) -> Report:
    """Run every labelled posting through `model` and score the answers."""
    pacer = Pacer()
    schema = response_schema()
    results = []
    with make_client(timeout_seconds=180) as client:
        backend = GeminiBackend(api_key=require_env("GEMINI_API_KEY"), model=model, client=client)
        for posting in postings:
            prompt = build_prompt(
                title=posting["title"],
                company=posting["company"],
                location=posting["location"],
                description=posting["description"],
            )
            pacer.wait()
            try:
                answer = backend.generate(prompt, schema)
                extraction = Extraction.model_validate_json(answer.text)
            except (HttpError, ModelError, ValidationError) as error:
                results.append(
                    (posting["id"], posting["labels"], f"{type(error).__name__}: {error}")
                )
                continue
            results.append((posting["id"], posting["labels"], extraction.model_dump(mode="json")))
    return score(results)


def main(argv: list[str]) -> None:
    verbose = "--verbose" in argv
    models = [arg for arg in argv if not arg.startswith("-")] or [require_env("EXTRACTION_MODEL")]
    postings = load_golden_set()

    for model in models:
        print(f"\n=== {model} on {len(postings)} labelled postings", flush=True)
        report = evaluate(model, postings)
        print(report.summary())
        if verbose:
            print("\n".join(f"  {line}" for line in report.mismatches))


if __name__ == "__main__":
    main(sys.argv[1:])
