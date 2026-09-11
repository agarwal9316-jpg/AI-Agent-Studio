"""Catalog of known LLM *structure creation* methods.

"Structure" here means any way users build a controllable model identity
or weight adaptation — not only GPU fine-tuning.
"""

from __future__ import annotations

from typing import Any


# Each method is selectable in Models GUI and documented for the user.
STRUCTURE_METHODS: list[dict[str, Any]] = [
    {
        "id": "system_profile",
        "name": "System profile (prompt identity)",
        "category": "compose",
        "backend": "local",
        "train": False,
        "description": (
            "Create a named model profile with system prompt, temperature, tools policy. "
            "No weight change — instant. Works with OpenAI, OpenRouter, Ollama."
        ),
        "needs": ["name", "base_url", "model", "system_prompt"],
    },
    {
        "id": "rag_virtual",
        "name": "RAG virtual model",
        "category": "compose",
        "backend": "local",
        "train": False,
        "description": (
            "Profile + Knowledge RAG always on. Model answers from your indexed files. "
            "Best for private docs without fine-tuning."
        ),
        "needs": ["name", "model", "knowledge_enabled"],
    },
    {
        "id": "tool_policy",
        "name": "Tool / skill policy model",
        "category": "compose",
        "backend": "local",
        "train": False,
        "description": (
            "Profile locked to terminal/files/web or skills only. "
            "Use for Coder, Researcher, Operator personas."
        ),
        "needs": ["name", "tools_enabled", "system_prompt"],
    },
    {
        "id": "multi_agent_org",
        "name": "Multi-agent org structure",
        "category": "compose",
        "backend": "local",
        "train": False,
        "description": (
            "Not a single model — AI-designed CEO→dept→agents tree (Team/Org). "
            "Structure of collaboration instead of one weight file."
        ),
        "needs": ["goal"],
        "page": "Org chart",
    },
    {
        "id": "ollama_modelfile",
        "name": "Ollama Modelfile create",
        "category": "local_create",
        "backend": "ollama",
        "train": False,
        "description": (
            "Create a local Ollama model from base + SYSTEM via Modelfile. "
            "Requires Ollama running. Free local 'create'."
        ),
        "needs": ["base_model", "system_prompt", "name"],
    },
    {
        "id": "local_lora",
        "name": "Local LoRA / QLoRA job",
        "category": "train",
        "backend": "local",
        "train": True,
        "description": (
            "Studio train lab: export dataset, hyperparams, adapter folder + recipe. "
            "Dry-run always works; PEFT when torch installed."
        ),
        "needs": ["dataset", "base_model", "hyperparams"],
    },
    {
        "id": "openai_sft",
        "name": "OpenAI supervised fine-tune (SFT)",
        "category": "train",
        "backend": "openai",
        "train": True,
        "description": (
            "Upload chat JSONL to OpenAI Files API (purpose=fine-tune), "
            "create fine_tuning job on gpt-4o-mini / gpt-3.5-turbo / etc. "
            "Resulting model id registered as Studio profile."
        ),
        "needs": ["dataset", "api_key", "base_model"],
        "base_models": [
            "gpt-4o-mini-2024-07-18",
            "gpt-4o-2024-08-06",
            "gpt-3.5-turbo",
            "gpt-4.1-mini-2025-04-14",
            "gpt-4.1-2025-04-14",
        ],
    },
    {
        "id": "openai_dpo",
        "name": "OpenAI preference fine-tune (DPO)",
        "category": "train",
        "backend": "openai",
        "train": True,
        "description": (
            "Preference-format fine-tuning when API supports method=dpo. "
            "Needs preference pairs (chosen/rejected). Falls back with clear error if unsupported."
        ),
        "needs": ["preference_dataset", "api_key", "base_model"],
    },
    {
        "id": "distill_teacher",
        "name": "Teacher distillation (OpenRouter / OpenAI)",
        "category": "train",
        "backend": "openai_compatible",
        "train": True,
        "description": (
            "Use a strong teacher model (OpenRouter or OpenAI) to generate answers "
            "for your prompts → new JSONL dataset → then SFT or LoRA student. "
            "Respects distillable-model routing when using OpenRouter."
        ),
        "needs": ["prompts_or_dataset", "teacher_model", "api_key"],
    },
    {
        "id": "adapter_attach",
        "name": "Attach adapter path",
        "category": "compose",
        "backend": "local",
        "train": False,
        "description": "Point a profile at an existing LoRA/adapter folder from a train job.",
        "needs": ["adapter_path", "base_model"],
    },
    {
        "id": "a_b_eval",
        "name": "A/B eval (base vs new)",
        "category": "eval",
        "backend": "any",
        "train": False,
        "description": (
            "Run the same prompts on two profiles and compare answers side-by-side. "
            "No training — quality gate after create/train."
        ),
        "needs": ["profile_a", "profile_b", "prompts"],
    },
    {
        "id": "hyperparam_sweep",
        "name": "Hyperparam sweep (multi job)",
        "category": "train",
        "backend": "local",
        "train": True,
        "description": "Queue several local LoRA jobs with different r/lr/steps for comparison.",
        "needs": ["dataset", "base_model"],
    },
]


def list_methods(
    *,
    category: str = "",
    train_only: bool | None = None,
) -> list[dict[str, Any]]:
    out = list(STRUCTURE_METHODS)
    if category:
        out = [m for m in out if m.get("category") == category]
    if train_only is True:
        out = [m for m in out if m.get("train")]
    if train_only is False:
        out = [m for m in out if not m.get("train")]
    return out


def get_method(method_id: str) -> dict[str, Any] | None:
    for m in STRUCTURE_METHODS:
        if m.get("id") == method_id:
            return m
    return None


def methods_help_text() -> str:
    lines = ["# LLM structure creation methods\n"]
    for m in STRUCTURE_METHODS:
        lines.append(
            f"## {m['name']} (`{m['id']}`)\n"
            f"- Category: {m['category']} · Backend: {m['backend']} · Train: {m['train']}\n"
            f"- {m['description']}\n"
        )
    lines.append(
        "\n**Note:** OpenRouter is excellent for *inference* and *teacher distillation*. "
        "Hosted weight fine-tuning is done via **OpenAI Fine-tuning API** (or local LoRA). "
        "OpenRouter does not host your custom fine-tune jobs."
    )
    return "\n".join(lines)
