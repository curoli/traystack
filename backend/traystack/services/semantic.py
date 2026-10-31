"""Offline embeddings of actual candidates, with content-addressed local reuse."""

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from traystack.semantic_model import (
    MAX_TOKENS,
    MODEL_ID,
    PIPELINE_VERSION,
    SCORE_VERSION,
    verify_artifacts,
)
from traystack.services.textual_matching import SearchTooBroad

logger = logging.getLogger(__name__)


class SemanticUnavailable(ValueError):
    pass


class SemanticInputTooLong(ValueError):
    pass


def semantic_score(query: str, passage: str, cosine: float) -> float:
    if query == passage:
        return 100.0
    # Reserve 100 for actual identity, including in two-decimal UI rendering.
    return min(99.99, max(0.0, cosine) * 100)


class SemanticEngine:
    def __init__(self, model_path: Path, cache_path: Path):
        ort.disable_telemetry_events()
        verify_artifacts(model_path)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.use_deterministic_compute = True
        self.session = ort.InferenceSession(
            str(model_path / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = Tokenizer.from_file(str(model_path / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        # The runtime versions participate in identity and prevent cross-version cache reuse.
        self.identity = (
            f"{MODEL_ID}|{PIPELINE_VERSION}|ort={version('onnxruntime')}"
            f"|tok={version('tokenizers')}"
        )
        self.cache_path = cache_path / hashlib.sha256(self.identity.encode()).hexdigest()
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.gate = threading.Lock()

    def _cache_file(self, text):
        return self.cache_path / (hashlib.sha256(text.encode()).hexdigest() + ".json")

    def _read(self, text):
        try:
            vector = np.asarray(json.loads(self._cache_file(text).read_text()), dtype=np.float32)
            if vector.shape == (384,) and np.isfinite(vector).all():
                if abs(float(np.linalg.norm(vector)) - 1) < 0.001:
                    return vector
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _write(self, text, vector):
        with tempfile.NamedTemporaryFile(mode="w", dir=self.cache_path, delete=False) as output:
            temporary = Path(output.name)
            json.dump(vector.tolist(), output)
        try:
            os.replace(temporary, self._cache_file(text))
        finally:
            temporary.unlink(missing_ok=True)

    def compare(self, query: str, passages: list[str]):
        if not self.gate.acquire(blocking=False):
            raise SemanticUnavailable("Semantic comparison is busy. Please try again shortly.")
        try:
            return self._compare(query, passages)
        except (SemanticUnavailable, SemanticInputTooLong, SearchTooBroad):
            raise
        except Exception as error:
            logger.error("Semantic comparison failed: %s", type(error).__name__)
            raise SemanticUnavailable(
                "Semantic comparison failed. No results were returned. Please try again "
                "or switch semantic comparison off."
            ) from error
        finally:
            self.gate.release()

    def _compare(self, query, passages):
        started = time.monotonic()
        texts = list(dict.fromkeys([query, *passages]))
        encodings = [self.tokenizer.encode(text) for text in texts]
        if any(len(item.ids) > MAX_TOKENS for item in encodings):
            raise SemanticInputTooLong(
                "Semantic comparison accepts at most 128 model tokens per expression or passage. "
                "Use a shorter expression or a stricter textual threshold. No text was truncated."
            )
        total_tokens = sum(len(item.ids) for item in encodings)
        if total_tokens > 40_000:
            raise SearchTooBroad(
                "Semantic comparison exceeded its token budget. Narrow the selection or raise "
                "the textual threshold.",
                reason="semantic_token_limit",
                resource="semantic_tokens",
                limit=40_000,
                observed=total_tokens,
            )
        vectors, missing = {}, []
        for text, encoding in zip(texts, encodings, strict=True):
            cached = self._read(text)
            if cached is not None:
                vectors[text] = cached
            else:
                missing.append((text, encoding))
        # Bounded cache: full caches still permit successful inference without new writes.
        cache_slots = max(0, 10_000 - sum(1 for _ in self.cache_path.glob("*.json")))
        # Dynamic INT8 quantization depends on the batch contents. A singleton
        # with fixed padding makes a text's vector independent of its neighbours
        # and whether other texts were already cached.
        for offset in range(len(missing)):
            self._check_time(started)
            batch = missing[offset : offset + 1]
            width = MAX_TOKENS
            ids = np.ones((len(batch), width), dtype=np.int64)
            mask = np.zeros_like(ids)
            types = np.zeros_like(ids)
            for index, (_, item) in enumerate(batch):
                length = len(item.ids)
                ids[index, :length] = item.ids
                mask[index, :length] = item.attention_mask
                types[index, :length] = item.type_ids
            hidden = self.session.run(
                ["last_hidden_state"],
                {
                    "input_ids": ids,
                    "attention_mask": mask,
                    "token_type_ids": types,
                },
            )[0]
            pooled = (hidden * mask[..., None]).sum(1) / mask.sum(1)[:, None]
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            if not np.isfinite(pooled).all() or (norms <= 0).any():
                raise SemanticUnavailable("Semantic comparison produced invalid vectors.")
            normalized = (pooled / norms).astype(np.float32)
            for (text, _), vector in zip(batch, normalized, strict=True):
                vectors[text] = vector
                if cache_slots > 0:
                    self._write(text, vector)
                    cache_slots -= 1
        self._check_time(started)
        similarities = [
            max(-1.0, min(1.0, float(vectors[query] @ vectors[text]))) for text in passages
        ]
        return [
            (semantic_score(query, text, cosine), cosine)
            for text, cosine in zip(passages, similarities, strict=True)
        ]

    @staticmethod
    def _check_time(started):
        elapsed = time.monotonic() - started
        if elapsed > 20:
            raise SearchTooBroad(
                "Semantic comparison exceeded its time budget. Narrow the selection or "
                "raise the textual threshold.",
                reason="semantic_time_limit",
                resource="semantic_seconds",
                limit=20,
                observed=elapsed,
            )

    def provenance(self):
        return {
            "model": MODEL_ID,
            "pipeline": self.identity,
            "score_version": SCORE_VERSION,
            "max_tokens": MAX_TOKENS,
        }


_engine_lock = threading.Lock()


@lru_cache(maxsize=2)
def _engine(model_path, cache_path):
    return SemanticEngine(Path(model_path), Path(cache_path))


def get_engine(model_path: Path, cache_path: Path):
    try:
        with _engine_lock:
            return _engine(str(model_path.resolve()), str(cache_path.resolve()))
    except Exception as error:
        raise SemanticUnavailable(
            "Semantic model is unavailable. Prepare the pinned model during setup; "
            "textual search remains available with semantic comparison switched off."
        ) from error
