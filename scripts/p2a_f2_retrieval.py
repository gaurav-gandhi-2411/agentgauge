#!/usr/bin/env python3
"""P2-A F2 retrieval-readiness test: BM25 + embedding ranking.

Measures whether Guard-B descriptions improve tool-retrieval ranking over thin
descriptions on underspecified queries - queries that state the general
capability WITHOUT encoding the within-family distinguishing axis.

This tests the F2 thesis: retrieval indexes rank on description alone (no task
context), so the finding that 'task context resolves danger' (which undercuts
direct-selection for high-stakes families) does NOT apply here.

Pre-registration: evals/fixtures/p2a_f2_retrieval_spec.json must be committed
before this script is run (enforced by git check below).

Usage:
    uv run python scripts/p2a_f2_retrieval.py
    uv run python scripts/p2a_f2_retrieval.py --no-embed
    uv run python scripts/p2a_f2_retrieval.py --ollama-url http://localhost:11435
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from evals.fixtures.p2a_internal_proxy_catalog import (
    ARM_A_DESCRIPTIONS,
    ARM_O_DESCRIPTIONS,
    CONTESTED_TOOLS,
    FAMILIES,
)

_SPEC_PATH = REPO_ROOT / "evals" / "fixtures" / "p2a_f2_retrieval_spec.json"
_GUARDB_PATH = REPO_ROOT / "evals" / "fixtures" / "p2a_arm_guardb_descriptions.json"

_STOPWORDS = frozenset({
    "a", "an", "the", "to", "of", "for", "in", "on", "at", "by", "and",
    "or", "is", "are", "be", "with", "from", "as", "it", "its", "that",
    "this", "not", "no", "up", "out",
})


# ── BM25 ──────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return [
        t.strip(".,;:!?'\"()")
        for t in text.lower().split()
        if t.strip(".,;:!?'\"()") not in _STOPWORDS
    ]


@dataclass
class BM25Index:
    docs: list[str]
    k1: float = 1.5
    b: float = 0.75

    _tokens: list[list[str]] = field(default_factory=list, init=False, repr=False)
    _idf: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _avgdl: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._tokens = [_tokenize(d) for d in self.docs]
        N = len(self._tokens)
        self._avgdl = sum(len(t) for t in self._tokens) / N if N else 1.0
        df: Counter[str] = Counter()
        for toks in self._tokens:
            for t in set(toks):
                df[t] += 1
        for term, n in df.items():
            self._idf[term] = math.log((N - n + 0.5) / (n + 0.5) + 1)

    def scores(self, query: str) -> list[float]:
        qtoks = _tokenize(query)
        result = []
        for toks in self._tokens:
            dl = len(toks)
            tf = Counter(toks)
            s = 0.0
            for t in qtoks:
                if t not in tf:
                    continue
                idf = self._idf.get(t, 0.0)
                f = tf[t]
                s += idf * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                )
            result.append(s)
        return result

    def rank(self, query: str) -> list[tuple[int, float]]:
        """Return (doc_idx, score) pairs sorted descending. Ties share average rank."""
        sc = self.scores(query)
        return sorted(enumerate(sc), key=lambda x: x[1], reverse=True)


# ── Embedding via Ollama ───────────────────────────────────────────────────────

def _embed_text(text: str, ollama_url: str, model: str = "nomic-embed-text") -> list[float] | None:
    try:
        resp = httpx.post(
            f"{ollama_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class EmbedIndex:
    """Pre-computed document embeddings for one arm. Queries are cached by text
    across all lookups (same query string is reused across arms and families)."""

    doc_vecs: list[list[float]]  # one per corpus doc, pre-computed
    _query_cache: dict[str, list[float]] = field(
        default_factory=dict, init=False, repr=False
    )
    ollama_url: str = ""

    def rank(self, query: str) -> list[tuple[int, float]] | None:
        if query not in self._query_cache:
            q_vec = _embed_text(query, self.ollama_url)
            if q_vec is None:
                return None
            self._query_cache[query] = q_vec
        q = self._query_cache[query]
        scored = [(i, _cosine(q, d)) for i, d in enumerate(self.doc_vecs)]
        return sorted(scored, key=lambda x: x[1], reverse=True)


def build_embed_index(
    docs: list[str], ollama_url: str, label: str = ""
) -> EmbedIndex | None:
    """Embed all 48 corpus docs once; return None on first failure."""
    vecs: list[list[float]] = []
    for i, doc in enumerate(docs):
        v = _embed_text(doc, ollama_url)
        if v is None:
            print(f"  [embed] failed on doc {i} ({label}) — disabling embedding", flush=True)
            return None
        vecs.append(v)
    return EmbedIndex(doc_vecs=vecs, ollama_url=ollama_url)


# ── TF-IDF cosine (pure Python, no extra deps) ────────────────────────────────

@dataclass
class TFIDFIndex:
    """Bag-of-words TF-IDF cosine similarity — captures inverse-document-frequency
    weighting without requiring a neural model. More symmetric than BM25 (query and
    doc use the same IDF table); useful as a lightweight 'semantic' baseline."""

    docs: list[str]

    _idf: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _vecs: list[dict[str, float]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        tokens_list = [_tokenize(d) for d in self.docs]
        N = len(self.docs)
        df: Counter[str] = Counter()
        for toks in tokens_list:
            for t in set(toks):
                df[t] += 1
        for term, n in df.items():
            self._idf[term] = math.log((N + 1) / (n + 1)) + 1.0  # smooth IDF
        self._vecs = [self._tfidf_vec(toks) for toks in tokens_list]

    def _tfidf_vec(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def rank(self, query: str) -> list[tuple[int, float]]:
        qtoks = _tokenize(query)
        qvec = self._tfidf_vec(qtoks)
        scored = []
        for i, dvec in enumerate(self._vecs):
            sim = sum(qvec.get(t, 0.0) * dvec.get(t, 0.0) for t in qvec)
            scored.append((i, sim))
        return sorted(scored, key=lambda x: x[1], reverse=True)


# ── Rank metrics ──────────────────────────────────────────────────────────────

def reciprocal_rank(
    ranked: list[tuple[int, float]], gold_idx: int
) -> float:
    """Fractional reciprocal rank - ties share the average of their rank positions."""
    gold_score = next((s for i, s in ranked if i == gold_idx), None)
    if gold_score is None:
        return 0.0
    tied = [i for i, (idx, s) in enumerate(ranked) if s == gold_score]
    avg_pos = sum(tied) / len(tied) + 1  # 1-based
    return 1.0 / avg_pos


def gold_rank(ranked: list[tuple[int, float]], gold_idx: int) -> float:
    """1-based rank of the gold document (fractional on ties)."""
    gold_score = next((s for i, s in ranked if i == gold_idx), None)
    if gold_score is None:
        return float(len(ranked) + 1)
    tied = [i for i, (idx, s) in enumerate(ranked) if s == gold_score]
    return sum(tied) / len(tied) + 1


# ── Per-arm description lookup ─────────────────────────────────────────────────

def load_descriptions() -> dict[str, dict[str, str]]:
    guardb_raw = json.loads(_GUARDB_PATH.read_text(encoding="utf-8"))
    # File is {tool_name: description} dict, not a list
    guardb: dict[str, str] = guardb_raw
    return {
        "thin": ARM_A_DESCRIPTIONS,
        "guardb": guardb,
        "oracle": ARM_O_DESCRIPTIONS,
    }


# ── Main ───────────────────────────────────────────────────────────────────────

@dataclass
class FamilyResult:
    arm: str
    retriever: str
    mrr: float
    rank_at_1: float  # fraction of queries where gold ranks first
    mean_rank: float
    n_queries: int


def run_family(
    family_name: str,
    family_tools: list[str],
    tool_names: list[str],           # all 48 tools in corpus order
    descs_by_arm: dict[str, dict[str, str]],
    queries_by_tool: dict[str, list[str]],
    embed_indexes: dict[str, EmbedIndex | None],  # pre-built per arm; None = skip
) -> list[FamilyResult]:
    contested_in_family = [t for t in family_tools if t in CONTESTED_TOOLS]
    corpus_queries: list[tuple[str, str]] = []  # (tool_name, query)
    for tool in contested_in_family:
        for q in queries_by_tool.get(tool, []):
            corpus_queries.append((tool, q))

    if not corpus_queries:
        return []

    results: list[FamilyResult] = []

    for arm, arm_descs in descs_by_arm.items():
        docs = [arm_descs[t] for t in tool_names]
        bm25 = BM25Index(docs=docs)
        tfidf = TFIDFIndex(docs=docs)
        embed_idx = embed_indexes.get(arm)

        rr_bm25: list[float] = []
        rk_bm25: list[float] = []
        at1_bm25: list[float] = []

        rr_tfidf: list[float] = []
        rk_tfidf: list[float] = []
        at1_tfidf: list[float] = []

        rr_emb: list[float] = []
        rk_emb: list[float] = []
        at1_emb: list[float] = []

        for tool, query in corpus_queries:
            gold_idx = tool_names.index(tool)

            ranked_b = bm25.rank(query)
            rr_bm25.append(reciprocal_rank(ranked_b, gold_idx))
            rk_bm25.append(gold_rank(ranked_b, gold_idx))
            at1_bm25.append(1.0 if ranked_b[0][0] == gold_idx else 0.0)

            ranked_t = tfidf.rank(query)
            rr_tfidf.append(reciprocal_rank(ranked_t, gold_idx))
            rk_tfidf.append(gold_rank(ranked_t, gold_idx))
            at1_tfidf.append(1.0 if ranked_t[0][0] == gold_idx else 0.0)

            if embed_idx is not None:
                ranked_e = embed_idx.rank(query)
                if ranked_e is not None:
                    rr_emb.append(reciprocal_rank(ranked_e, gold_idx))
                    rk_emb.append(gold_rank(ranked_e, gold_idx))
                    at1_emb.append(1.0 if ranked_e[0][0] == gold_idx else 0.0)

        n = len(corpus_queries)
        results.append(FamilyResult(
            arm=arm, retriever="BM25",
            mrr=sum(rr_bm25) / n, rank_at_1=sum(at1_bm25) / n,
            mean_rank=sum(rk_bm25) / n, n_queries=n,
        ))
        results.append(FamilyResult(
            arm=arm, retriever="TFIDF",
            mrr=sum(rr_tfidf) / n, rank_at_1=sum(at1_tfidf) / n,
            mean_rank=sum(rk_tfidf) / n, n_queries=n,
        ))
        if rr_emb:
            n_e = len(rr_emb)
            results.append(FamilyResult(
                arm=arm, retriever="embed",
                mrr=sum(rr_emb) / n_e, rank_at_1=sum(at1_emb) / n_e,
                mean_rank=sum(rk_emb) / n_e, n_queries=n_e,
            ))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="P2-A F2 retrieval-readiness test")
    parser.add_argument("--no-embed", action="store_true", help="Skip embedding retrieval")
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama base URL for nomic-embed-text (default: http://localhost:11434)",
    )
    args = parser.parse_args()

    spec = json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
    queries_by_tool: dict[str, list[str]] = spec["queries_per_tool"]
    queries_by_tool = {k: v for k, v in queries_by_tool.items() if not k.startswith("_")}

    descs_by_arm = load_descriptions()

    # Build corpus: all 48 tools in deterministic order
    tool_names = list(ARM_A_DESCRIPTIONS.keys())

    ollama_url: str | None = None
    if not args.no_embed:
        # Probe Ollama availability
        probe = _embed_text("probe", args.ollama_url)
        if probe is None:
            print("  [embed] Ollama not available or nomic-embed-text not pulled - BM25 only.")
        else:
            ollama_url = args.ollama_url
            print(f"  [embed] Ollama ready at {ollama_url}")

    print("\n" + "=" * 100)
    print("P2-A F2 Retrieval-Readiness Test - underspecified queries, description-only indexing")
    print("Pre-registered spec: evals/fixtures/p2a_f2_retrieval_spec.json")
    print(f"Corpus: {len(tool_names)} tools | Arms: thin / guardb / oracle | "
          f"Retrievers: BM25 + TFIDF{' + embed' if ollama_url else ''}")
    print("=" * 100)

    # Pre-build embedding indexes (48 docs x 3 arms = 144 calls total).
    # Queries are cached inside EmbedIndex on first use (93 unique query strings).
    embed_indexes: dict[str, EmbedIndex | None] = {}
    if ollama_url:
        for arm, arm_descs in descs_by_arm.items():
            docs = [arm_descs[t] for t in tool_names]
            print(f"  [embed] indexing arm={arm} ({len(docs)} docs)...", flush=True)
            idx = build_embed_index(docs, ollama_url, label=arm)
            embed_indexes[arm] = idx
            if idx is None:
                ollama_url = None
                print("  [embed] disabled after index failure", flush=True)
                break

    all_by_family: dict[str, list[FamilyResult]] = {}
    for fam, tools in FAMILIES.items():
        fam_results = run_family(
            fam, tools, tool_names, descs_by_arm, queries_by_tool, embed_indexes
        )
        all_by_family[fam] = fam_results

    # ── Per-family table ───────────────────────────────────────────────────────
    has_embed = any(v is not None for v in embed_indexes.values())
    retrievers_to_show = ["BM25", "TFIDF"] + (["embed"] if has_embed else [])
    for retriever in retrievers_to_show:
        print(f"\n-- {retriever} retrieval (description-only, underspecified queries) " + "-" * 40)
        print(f"  {'Family':<30} {'Arm':<9} {'MRR':>7} {'R@1':>7} {'MeanRk':>8}  Interpretation")
        print("  " + "-" * 90)
        for fam, results in all_by_family.items():
            fam_short = fam.replace("_family", "")
            rows = [r for r in results if r.retriever == retriever]
            if not rows:
                continue
            # Sort thin / guardb / oracle
            for arm_label in ("thin", "guardb", "oracle"):
                row = next((r for r in rows if r.arm == arm_label), None)
                if row is None:
                    continue
                # Compute vs thin delta for guardb/oracle
                thin_row = next((r for r in rows if r.arm == "thin"), None)
                if arm_label != "thin" and thin_row:
                    delta_mrr = row.mrr - thin_row.mrr
                    note = f"{'+'if delta_mrr>=0 else ''}{delta_mrr:+.3f} MRR vs thin"
                    if delta_mrr < -0.05:
                        note += " [HARM]"
                    elif delta_mrr > 0.05:
                        note += " [IMPROVED]"
                    else:
                        note += " [NEUTRAL]"
                else:
                    note = "(baseline)"
                print(
                    f"  {fam_short:<30} {arm_label:<9} {row.mrr:>7.3f} "
                    f"{row.rank_at_1:>7.3f} {row.mean_rank:>8.1f}  {note}"
                )
        print("  " + "=" * 90)

    # ── Aggregate contested-set summary ───────────────────────────────────────
    print("\n-- Aggregate over ALL 31 contested tools " + "-" * 50)
    for retriever in retrievers_to_show:
        print(f"\n  {retriever}:")
        for arm_label in ("thin", "guardb", "oracle"):
            rows = [
                r for fam_results in all_by_family.values()
                for r in fam_results
                if r.retriever == retriever and r.arm == arm_label
            ]
            if not rows:
                continue
            total_q = sum(r.n_queries for r in rows)
            agg_mrr = sum(r.mrr * r.n_queries for r in rows) / total_q
            agg_at1 = sum(r.rank_at_1 * r.n_queries for r in rows) / total_q
            agg_rk = sum(r.mean_rank * r.n_queries for r in rows) / total_q
            print(f"    {arm_label:<9} MRR={agg_mrr:.3f}  R@1={agg_at1:.3f}  MeanRk={agg_rk:.1f}")

    # ── Pre-committed interpretation reminder ─────────────────────────────────
    print("\n-- Pre-committed interpretation branches " + "-" * 49)
    for branch, text in spec["pre_committed_interpretation"].items():
        print(f"\n  [{branch}]")
        print(f"    {text[:200]}{'...' if len(text) > 200 else ''}")

    print("\nDone. Apply the pre-committed interpretation to the per-family MRR table above.")


if __name__ == "__main__":
    main()
