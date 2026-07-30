"""
config.py
---------
DB connection + multi-provider LLM chat completion with automatic key/provider
fallback. Same pattern proven out in the sibling Header_Mapping project's
config.py (numbered KEY_1/KEY_2/... env vars, tried in order, falling through to the
next provider on failure) - reimplemented independently here rather than imported
across projects, since each project under Suhana.khan/ owns its own config/DB.
"""
import itertools
import os
import re
import time

import psycopg2
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _collect_keys(prefix: str) -> list[str]:
    numbered = [os.environ.get(f"{prefix}_{i}", "") for i in range(1, 6)]
    single = os.environ.get(prefix, "")
    return [k for k in ([single] + numbered) if k]


_CLIENT_TIMEOUT = 30.0

_OPENROUTER_KEYS = _collect_keys("OPENROUTER_API_KEY")
_openrouter_clients = [
    OpenAI(api_key=k, base_url="https://openrouter.ai/api/v1", timeout=_CLIENT_TIMEOUT, max_retries=0)
    for k in _OPENROUTER_KEYS
]

_GROQ_KEYS = _collect_keys("GROQ_API_KEY")
_groq_clients = [
    OpenAI(api_key=k, base_url="https://api.groq.com/openai/v1", timeout=_CLIENT_TIMEOUT, max_retries=0)
    for k in _GROQ_KEYS
]

_OPENROUTER_MODEL = "openai/gpt-4o-mini"
_GROQ_MODEL = "llama-3.3-70b-versatile"

AI_AVAILABLE = bool(_openrouter_clients or _groq_clients)

# Groq's 429 body includes a literal "Please try again in 23.48s" phrase - a real
# per-minute-window rate limit that normally clears in well under a minute. Worth
# waiting out on the SAME key rather than immediately burning the only other
# configured provider (this project only has OpenRouter + Groq, so exhausting both
# on one transient rate limit means the whole request fails for no good reason).
# Capped so a request never blocks longer than this on one provider.
_RATE_LIMIT_RETRY_CAP_SECONDS = 30.0
_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)


def _extract_retry_after_seconds(e: Exception) -> float | None:
    match = _RETRY_AFTER_RE.search(str(e))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def log_provider_status() -> None:
    counts = [("OpenRouter", len(_openrouter_clients)), ("Groq", len(_groq_clients))]
    configured = ", ".join(f"{name}={n}" for name, n in counts if n)
    print(f"[config] AI_AVAILABLE={AI_AVAILABLE} | keys configured: {configured or '(none)'}")


def get_provider_pool() -> list[tuple]:
    providers = []
    for i, client in enumerate(_openrouter_clients, start=1):
        providers.append((client, _OPENROUTER_MODEL, f"OpenRouter (key {i})"))
    for i, client in enumerate(_groq_clients, start=1):
        providers.append((client, _GROQ_MODEL, f"Groq (key {i})"))
    return providers


# Every call site (master_classifier.py, metadata_generator.py per chunk,
# field_mapping_engine.py per batch) used to call chat_complete[_with_meta] without
# ever passing start_index, which defaulted to a fixed 0 - meaning EVERY call always
# tried the same first provider first. With multiple Groq keys configured, that's
# not a fallback chain, it's a waterfall: key 1 absorbs 100% of real traffic and
# exhausts its own 12k TPM / 100k TPD limit while keys 2/3 sit idle until key 1 is
# already dead for the day. This counter rotates the default starting point across
# calls (round-robin) so load actually spreads across every configured key from the
# start - explicit fallback-on-failure still tries the FULL pool either way, this
# only changes which provider gets tried FIRST. A bare itertools.count() isn't
# perfectly atomic under concurrent threads (the mapping-run background thread), but
# a rare duplicate start_index is a harmless, no-correctness-impact load-balancing
# imperfection, not a bug worth a lock for.
_start_index_rotation = itertools.count()


def chat_complete_with_meta(messages: list[dict], start_index: int = None, max_tokens: int = 2000) -> tuple[str, str, int]:
    """Same fallback chain as chat_complete(), but also returns WHICH provider/key
    actually served the request and how long it took - (content, agent_name,
    duration_ms). Exists so callers that need to log agent activity (see
    app/services/events.py) don't have to duplicate the fallback loop; chat_complete()
    below is a thin wrapper over this for callers that only want the text.

    start_index defaults to None, which auto-rotates (see _start_index_rotation) -
    pass an explicit value only if you specifically want to pin/control where in the
    pool a call starts."""
    if not AI_AVAILABLE:
        raise RuntimeError("No AI provider configured - set at least one API key in .env")

    providers = get_provider_pool()
    n = len(providers)
    if start_index is None:
        start_index = next(_start_index_rotation)
    last_error = None
    for offset in range(n):
        client, model, name = providers[(start_index + offset) % n]
        t0 = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=0.0, max_tokens=max_tokens,
            )
            return resp.choices[0].message.content, name, int((time.monotonic() - t0) * 1000)
        except Exception as e:
            retry_after = _extract_retry_after_seconds(e)
            if retry_after is not None and retry_after <= _RATE_LIMIT_RETRY_CAP_SECONDS:
                print(f"    [AI] {name} rate-limited - waiting {retry_after:.1f}s and retrying the same key")
                time.sleep(retry_after)
                try:
                    resp = client.chat.completions.create(
                        model=model, messages=messages, temperature=0.0, max_tokens=max_tokens,
                    )
                    return resp.choices[0].message.content, name, int((time.monotonic() - t0) * 1000)
                except Exception as e2:
                    last_error = e2
                    print(f"    [AI] {name} failed again after waiting ({e2}) -> trying next")
                    continue
            last_error = e
            print(f"    [AI] {name} failed ({e}) -> trying next")
            continue

    raise RuntimeError(f"All AI providers failed. Last error: {last_error}")


def chat_complete(messages: list[dict], start_index: int = None, max_tokens: int = 2000) -> str:
    """OpenRouter (gpt-4o-mini) -> Groq (llama-3.3-70b), trying every configured key
    within a provider before moving to the next. Raises RuntimeError if no provider
    is configured or all of them fail. start_index defaults to auto-rotating - see
    chat_complete_with_meta()."""
    content, _agent, _duration_ms = chat_complete_with_meta(messages, start_index=start_index, max_tokens=max_tokens)
    return content


DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "database": os.environ.get("DB_NAME", "erp_masterdata_prep"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
}
if not DB_CONFIG["password"]:
    raise EnvironmentError("DB_PASSWORD is not set - copy .env.example to .env and fill it in.")


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_admin_connection():
    """Connects to the default 'postgres' maintenance DB, used only to create the
    erp_masterdata_prep database itself."""
    admin_cfg = dict(DB_CONFIG)
    admin_cfg["database"] = "postgres"
    return psycopg2.connect(**admin_cfg)
