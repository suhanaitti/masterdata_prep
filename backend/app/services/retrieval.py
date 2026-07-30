"""
retrieval.py
------------
Keyword (BM25) retrieval and ERP-domain synonym expansion, used ALONGSIDE the
existing embedding-based semantic search in mapping_engine.py - not instead of it.
Embeddings can dilute an exact/near-exact term match across a whole-sentence vector;
BM25 catches strong literal word overlap (e.g. two fields that both say "purchasing
group") that a semantic score can under-rate. The two rankings are combined via
Reciprocal Rank Fusion (RRF) in mapping_engine._candidates_per_source() - this module
only produces individual rankings and the fusion primitive, it makes no matching
decisions itself.

Hand-rolled (no external bm25 package): the corpus here is at most a few thousand
short, label-like field descriptions per side - small enough that a plain Python
implementation of the standard Okapi BM25 formula is fast, and this avoids adding a
dependency for a well-understood, easily-reimplemented classic-IR technique.
"""
import math
import re
from collections import Counter

# ERP business-term synonym groups. This is what "ERP synonym / business rule
# matching" means concretely in this pipeline: known cross-system vocabulary that
# means the same underlying concept is folded into a shared token during BM25
# tokenization, so e.g. "Buyer Group" and "Purchasing Group" share term-overlap
# credit even though neither word is literally the other. The LLM step downstream
# still makes the actual equivalence judgment - this only improves what keyword
# search surfaces as a candidate worth showing it.
ERP_SYNONYM_GROUPS = [
    {"number", "no", "num", "nr"},
    {"description", "desc", "text", "txt", "bez"},
    {"quantity", "qty", "menge"},
    {"unit", "uom", "meins", "einh", "measure"},
    {"weight", "wt", "gew", "gewicht"},
    {"date", "dt", "datum"},
    {"indicator", "ind", "flag", "kz"},
    {"code", "cd"},
    {"group", "grp"},
    {"category", "cat", "klasse", "class"},
    {"vendor", "supplier", "lifnr"},
    {"customer", "cust", "kunnr"},
    {"plant", "site", "werks"},
    {"material", "matnr", "item", "product", "prod"},
    {"purchasing", "purchase", "buying", "procurement", "buyer"},
    {"sales", "selling", "sale", "seller"},
    {"warehouse", "whse", "storage"},
    {"batch", "lot"},
    {"currency", "curr", "waers"},
    {"price", "cost"},
    {"discount", "rebate", "allowance"},
    {"invoice", "billing", "bill"},
    {"delivery", "shipment", "shipping"},
    {"tax", "vat", "duty"},
    {"profile", "template"},
    {"tolerance", "variance", "deviation"},
    {"length", "size", "dimension"},
    {"height", "width", "depth"},
    {"organization", "org", "company", "entity"},
    {"employee", "worker", "personnel"},
    {"contract", "agreement"},
    {"status", "state"},
    {"priority", "urgency"},
    {"manufacturer", "producer", "maker"},
    {"expiry", "expiration", "shelf life"},
]
# Deliberately NOT included: "id"/"identifier"/"key"/"reference" as a blanket synonym
# group. Boosting retrieval on the mere presence of "id"-like vocabulary would directly
# fight the internal/system-ID penalty in mapping_engine.py (_is_internal_id_name) -
# two fields both being "an ID" is exactly the weak signal that penalty exists to guard
# against, so keyword search should not be handing it extra credit for that alone.
_SYNONYM_LOOKUP = {}
for _group in ERP_SYNONYM_GROUPS:
    _canon = min(_group, key=len)  # shortest word in the group is the canonical token
    for _w in _group:
        _SYNONYM_LOOKUP[_w] = f"__syn_{_canon}__"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list:
    """Lowercase word tokens, plus one synonym-group token appended for any word
    that belongs to a known ERP synonym group above."""
    if not text:
        return []
    words = _TOKEN_RE.findall(text.lower())
    tokens = list(words)
    for w in words:
        syn = _SYNONYM_LOOKUP.get(w)
        if syn:
            tokens.append(syn)
    return tokens


class BM25Index:
    """Minimal Okapi BM25 over a fixed list of (doc_id, doc_text) pairs. Standard
    k1=1.5, b=0.75 defaults - not tuned for this corpus specifically, since the
    corpus is small, short-text, and BM25's main value here is catching strong
    literal/synonym term overlap, not fine-grained ranking within long documents."""

    def __init__(self, doc_ids: list, doc_texts: list, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_ids = list(doc_ids)
        doc_tokens = [tokenize(t) for t in doc_texts]
        self.doc_len = [len(toks) for toks in doc_tokens]
        self.n = len(doc_tokens)
        self.avg_len = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.doc_freqs = [Counter(toks) for toks in doc_tokens]

        df = Counter()
        for toks in doc_tokens:
            for term in set(toks):
                df[term] += 1
        # Standard Robertson-Sparck Jones IDF, floored at a small positive value so a
        # term appearing in nearly every document never produces a negative weight.
        self.idf = {
            term: max(0.01, math.log((self.n - freq + 0.5) / (freq + 0.5) + 1))
            for term, freq in df.items()
        }

    def top_n(self, query_text: str, n: int) -> list:
        """Returns up to n doc_ids, best BM25 score first."""
        if self.n == 0:
            return []
        q_tokens = tokenize(query_text)
        if not q_tokens:
            return []
        scores = [0.0] * self.n
        for term in set(q_tokens):
            idf = self.idf.get(term)
            if not idf:
                continue
            for i in range(self.n):
                f = self.doc_freqs[i].get(term)
                if not f:
                    continue
                dl = self.doc_len[i]
                denom = f + self.k1 * (1 - self.b + self.b * (dl / self.avg_len if self.avg_len else 1))
                scores[i] += idf * (f * (self.k1 + 1)) / denom
        ranked = [i for i in range(self.n) if scores[i] > 0]
        ranked.sort(key=lambda i: scores[i], reverse=True)
        return [self.doc_ids[i] for i in ranked[:n]]


def reciprocal_rank_fusion(ranked_lists: list, k: int = 60) -> list:
    """Combines multiple ranked lists over the SAME id-space into one fused ranking.
    Each id's fused score is the sum of 1/(k + rank + 1) across every list it appears
    in (0 contribution from lists it's absent from). Standard RRF constant k=60, so
    fusion isn't dominated by whichever single list ranked something #1. Returns ids
    sorted by fused score, best first; ids present in more lists / at better ranks
    naturally float to the top."""
    scores = {}
    for lst in ranked_lists:
        for rank, doc_id in enumerate(lst):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
