"""Model capability helpers shared by server model-selection routes."""

_EMBEDDING_MODEL_PREFIXES = (
    "all-minilm",
    "bge-",
    "bge_",
    "e5-",
    "e5_",
    "gte-",
    "gte_",
    "jina-embeddings",
    "nomic-bert",
    "sentence-transformers",
)


def is_embed_only_model(model_name: str) -> bool:
    """Return whether a model identifier denotes a non-chat embedder.

    Ollama does not expose capabilities through its model-list response, so
    model selection needs a conservative name-based guard.  Most embedding
    models contain ``embed``; the explicit prefixes cover common families
    such as MiniLM, BGE, E5, and GTE whose names do not.
    """
    name = (model_name or "").strip().lower()
    leaf = name.rsplit("/", 1)[-1].split(":", 1)[0]
    return (
        "embed" in leaf
        or "minilm" in leaf
        or leaf.startswith(_EMBEDDING_MODEL_PREFIXES)
    )


__all__ = ["is_embed_only_model"]


#: Agent mode's recommended models, by the memory they need (GB). Smaller
#: models often miss or garble tool calls; 9B is the reliable floor that still
#: runs on a typical laptop.
AGENT_MODEL_LADDER = (
    ("qwen3.5:9b", 12.0),
    ("qwen3.5:4b", 8.0),
)
#: Installed models this size or bigger are good enough for Agent mode.
AGENT_MIN_PARAMS_B = 7.0


def model_params_b(model_name: str) -> float:
    """Parameter count in billions from a name like ``qwen3.5:9b`` (else 0)."""
    import re

    match = re.search(r"(?:^|[:\-_/])(\d+(?:\.\d+)?)b(?=$|[-_.:])", model_name.lower())
    return float(match.group(1)) if match else 0.0


def _fits(params_b: float, ram_gb: float) -> bool:
    # A 4-bit model needs about 0.75 GB per billion parameters, plus headroom.
    return params_b * 0.75 + 4 <= ram_gb


def agent_model_recommendation(installed: list, ram_gb: float) -> dict:
    """The model Agent mode should use on this computer.

    Prefers the largest installed model that's big enough and fits in memory,
    then the ladder's best fit to download. ``model`` is empty when the
    computer has too little memory for Agent mode to work well.
    """
    usable = sorted(
        (
            m
            for m in installed
            if not is_embed_only_model(m)
            and model_params_b(m) >= AGENT_MIN_PARAMS_B
            and _fits(model_params_b(m), ram_gb)
        ),
        key=model_params_b,
        reverse=True,
    )
    if usable:
        return {
            "model": usable[0],
            "installed": True,
            "ram_gb": round(ram_gb),
            "reason": f"{usable[0]} is installed and handles tools well.",
        }
    for model, min_ram in AGENT_MODEL_LADDER:
        if ram_gb >= min_ram:
            reason = (
                f"{model} handles tools reliably on {round(ram_gb)} GB of memory."
                if model_params_b(model) >= AGENT_MIN_PARAMS_B
                else f"{model} is the largest that fits in {round(ram_gb)} GB;"
                " Agent mode works, but may miss steps."
            )
            return {
                "model": model,
                "installed": model in installed,
                "ram_gb": round(ram_gb),
                "reason": reason,
            }
    return {
        "model": "",
        "installed": False,
        "ram_gb": round(ram_gb),
        "reason": "Agent mode needs at least 8 GB of memory to work well.",
    }
