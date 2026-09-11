"""Cloud fine-tuning & structure creation via OpenAI-compatible APIs.

OpenAI:
  - Files upload (purpose=fine-tune)
  - Fine-tuning jobs SFT (and DPO when supported)
  - List/cancel/retrieve jobs
  - Register finished fine-tuned model as Studio profile

OpenRouter / other OpenAI-compatible:
  - Inference + teacher distillation dataset generation
  - Not used for hosted FT jobs (API does not train weights)
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.paths import model_datasets_dir, train_jobs_dir
from app.core.services.data.storage import _read_json, _write_json, load_config
from app.core.services.ai.train_lab import get_job, save_job, _append_log  # type: ignore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _headers(api_key: str, base_url: str = "") -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {(api_key or '').strip()}",
    }
    if "openrouter.ai" in (base_url or ""):
        h["HTTP-Referer"] = "https://ai-agent-studio.local"
        h["X-Title"] = "AI Agent Studio"
    return h


def resolve_cloud_credentials(
    *,
    api_key: str = "",
    base_url: str = "",
    prefer: str = "openai",
) -> dict[str, str]:
    """Resolve key/base from args or active provider / config."""
    from app.core.services.llm.providers import resolve_active_llm

    active = resolve_active_llm()
    cfg = load_config()
    key = (api_key or active.get("api_key") or cfg.get("api_key") or "").strip()
    base = (
        base_url
        or active.get("base_url")
        or cfg.get("api_base_url")
        or "https://api.openai.com/v1"
    ).strip().rstrip("/")
    # Fine-tune only works on OpenAI platform API (not OpenRouter)
    if prefer == "openai_ft":
        # Force OpenAI if user has openai key in providers
        try:
            from app.services import providers as prov

            store = prov.load_providers()
            for p in store.get("providers") or []:
                if p.get("id") == "openai" and p.get("keys"):
                    k = p["keys"][0]
                    key = (k.get("key") or key).strip()
                    base = (p.get("base_url") or "https://api.openai.com/v1").rstrip("/")
                    break
        except Exception:  # noqa: BLE001
            if "openrouter" in base.lower():
                base = "https://api.openai.com/v1"
    return {"api_key": key, "base_url": base}


def _http_json(
    method: str,
    url: str,
    *,
    api_key: str,
    base_url: str = "",
    body: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    data = None
    headers = _headers(api_key, base_url)
    headers["Content-Type"] = "application/json"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network: {e.reason}") from e


def upload_finetune_file(
    jsonl_path: str | Path,
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
) -> dict[str, Any]:
    """Multipart upload to OpenAI /files with purpose=fine-tune."""
    path = Path(jsonl_path)
    if not path.exists():
        return {"ok": False, "error": f"File not found: {path}"}
    # Use urllib multipart manually
    boundary = f"----StudioBoundary{uuid.uuid4().hex}"
    file_bytes = path.read_bytes()
    filename = path.name
    parts: list[bytes] = []
    # purpose field
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="purpose"\r\n\r\n'
            f"fine-tune\r\n"
        ).encode("utf-8")
    )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/jsonl\r\n\r\n"
        ).encode("utf-8")
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    url = base_url.rstrip("/") + "/files"
    headers = _headers(api_key, base_url)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return {"ok": True, "file_id": payload.get("id"), "raw": payload}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        return {"ok": False, "error": f"HTTP {e.code}: {detail}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def create_openai_ft_job(
    *,
    training_file_id: str,
    model: str = "gpt-4o-mini-2024-07-18",
    api_key: str = "",
    base_url: str = "",
    suffix: str = "studio",
    method: str = "supervised",  # supervised | dpo
    n_epochs: int | None = None,
    hyperparameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /v1/fine_tuning/jobs"""
    if "openrouter" in (base_url or "").lower():
        return {
            "ok": False,
            "error": (
                "OpenRouter does not host fine-tune jobs. "
                "Use an OpenAI API key + https://api.openai.com/v1 for SFT, "
                "or use OpenRouter as teacher for distillation."
            ),
        }
    creds = resolve_cloud_credentials(api_key=api_key, base_url=base_url, prefer="openai_ft")
    key, base = creds["api_key"], creds["base_url"]
    if not key:
        return {"ok": False, "error": "No API key (need OpenAI key for fine-tuning)"}
    if "openrouter" in base.lower():
        return {
            "ok": False,
            "error": (
                "Active endpoint is OpenRouter — fine-tuning needs OpenAI platform. "
                "Add an OpenAI provider key in Settings, or use method distill_then_sft "
                "with OpenRouter as teacher only."
            ),
        }
    body: dict[str, Any] = {
        "training_file": training_file_id,
        "model": model,
        "suffix": (suffix or "studio")[:18],
    }
    hp = dict(hyperparameters or {})
    if n_epochs is not None:
        hp["n_epochs"] = n_epochs
    if hp:
        body["hyperparameters"] = hp
    # DPO method (API may reject if model/method unsupported)
    if method == "dpo":
        body["method"] = {
            "type": "dpo",
            "dpo": {"hyperparameters": hp or {}},
        }
    try:
        payload = _http_json(
            "POST",
            base + "/fine_tuning/jobs",
            api_key=key,
            base_url=base,
            body=body,
            timeout=120.0,
        )
        return {"ok": True, "job": payload, "job_id": payload.get("id")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def get_openai_ft_job(job_id: str, *, api_key: str = "", base_url: str = "") -> dict[str, Any]:
    creds = resolve_cloud_credentials(api_key=api_key, base_url=base_url, prefer="openai_ft")
    try:
        payload = _http_json(
            "GET",
            creds["base_url"] + f"/fine_tuning/jobs/{job_id}",
            api_key=creds["api_key"],
            base_url=creds["base_url"],
        )
        return {"ok": True, "job": payload}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def list_openai_ft_jobs(*, api_key: str = "", base_url: str = "", limit: int = 20) -> dict[str, Any]:
    creds = resolve_cloud_credentials(api_key=api_key, base_url=base_url, prefer="openai_ft")
    try:
        payload = _http_json(
            "GET",
            creds["base_url"] + f"/fine_tuning/jobs?limit={limit}",
            api_key=creds["api_key"],
            base_url=creds["base_url"],
        )
        return {"ok": True, "jobs": payload.get("data") or []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "jobs": []}


def cancel_openai_ft_job(job_id: str, *, api_key: str = "", base_url: str = "") -> dict[str, Any]:
    creds = resolve_cloud_credentials(api_key=api_key, base_url=base_url, prefer="openai_ft")
    try:
        payload = _http_json(
            "POST",
            creds["base_url"] + f"/fine_tuning/jobs/{job_id}/cancel",
            api_key=creds["api_key"],
            base_url=creds["base_url"],
            body={},
        )
        return {"ok": True, "job": payload}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def start_openai_sft_from_dataset(
    dataset_id: str,
    *,
    base_model: str = "gpt-4o-mini-2024-07-18",
    name: str = "openai-sft",
    n_epochs: int | None = 3,
    api_key: str = "",
    method: str = "supervised",
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Full pipeline: find dataset JSONL → upload → create FT job → track in train_jobs.
    Polls in background until succeeded/failed.
    """
    from app.core.services.ai.train_lab import create_job
    from app.core.services.llm.model_profiles import create_profile
    from app.core.services.system.ops_monitor import log_event

    def prog(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001
                pass

    meta = _read_json(model_datasets_dir() / dataset_id / "meta.json", None)
    if not isinstance(meta, dict):
        return {"ok": False, "error": "Dataset not found — export Chat/Team first"}
    path = Path(str(meta.get("path") or ""))
    if not path.exists():
        return {"ok": False, "error": f"Missing JSONL: {path}"}

    # Studio tracking job
    job = create_job(
        name=name or f"openai-sft-{dataset_id[:6]}",
        base_model=base_model,
        dataset_id=dataset_id,
        method="openai_sft" if method != "dpo" else "openai_dpo",
        epochs=int(n_epochs or 3),
        dry_run=False,
        notes="OpenAI Fine-tuning API",
    )
    job["backend"] = "openai"
    job["status"] = "running"
    job["started_at"] = _now()
    save_job(job)
    jid = str(job["id"])

    def worker() -> None:
        j = get_job(jid) or job
        try:
            prog("Uploading training file to OpenAI…")
            _append_log(j, "Uploading JSONL to OpenAI Files API")
            up = upload_finetune_file(path, api_key=api_key)
            if not up.get("ok"):
                raise RuntimeError(up.get("error") or "upload failed")
            file_id = str(up.get("file_id") or "")
            j["cloud_file_id"] = file_id
            _append_log(j, f"File id: {file_id}")
            save_job(j)

            prog(f"Creating fine-tune job on {base_model}…")
            created = create_openai_ft_job(
                training_file_id=file_id,
                model=base_model,
                api_key=api_key,
                suffix="studio",
                method="dpo" if method == "dpo" else "supervised",
                n_epochs=n_epochs,
            )
            if not created.get("ok"):
                raise RuntimeError(created.get("error") or "create job failed")
            cloud_id = str(created.get("job_id") or "")
            j["cloud_job_id"] = cloud_id
            _append_log(j, f"Cloud job: {cloud_id}")
            save_job(j)
            log_event("train", f"OpenAI FT started {cloud_id}", source="openai_ft", meta={"id": jid})

            # Poll
            for i in range(1, 600):  # up to long runs
                time.sleep(15 if i > 2 else 5)
                st = get_openai_ft_job(cloud_id, api_key=api_key)
                if not st.get("ok"):
                    _append_log(j, f"poll error: {st.get('error')}")
                    continue
                cj = st.get("job") or {}
                status = str(cj.get("status") or "")
                j["cloud_status"] = status
                j["progress"] = min(0.95, 0.1 + i * 0.01)
                fine_tuned = cj.get("fine_tuned_model") or ""
                if fine_tuned:
                    j["fine_tuned_model"] = fine_tuned
                _append_log(j, f"status={status} model={fine_tuned or '—'}")
                save_job(j)
                prog(f"OpenAI FT: {status}")
                if status in ("succeeded", "failed", "cancelled"):
                    if status == "succeeded" and fine_tuned:
                        j["status"] = "done"
                        j["progress"] = 1.0
                        # Register profile pointing at OpenAI
                        prof = create_profile(
                            f"FT · {name or fine_tuned}",
                            kind="cloud",
                            base_url="https://api.openai.com/v1",
                            model=str(fine_tuned),
                            api_key=api_key
                            or resolve_cloud_credentials(prefer="openai_ft")["api_key"],
                            notes=f"OpenAI fine-tune job {cloud_id}",
                        )
                        j["profile_id"] = prof.get("id")
                        _append_log(j, f"Registered profile {prof.get('name')} → {fine_tuned}")
                        log_event(
                            "train",
                            f"OpenAI FT done: {fine_tuned}",
                            source="openai_ft",
                            level="info",
                        )
                    else:
                        j["status"] = "failed" if status == "failed" else "cancelled"
                        j["error"] = str(cj.get("error") or status)
                    j["finished_at"] = _now()
                    save_job(j)
                    return
            j["status"] = "failed"
            j["error"] = "Timeout waiting for OpenAI job"
            j["finished_at"] = _now()
            save_job(j)
        except Exception as e:  # noqa: BLE001
            j = get_job(jid) or j
            j["status"] = "failed"
            j["error"] = str(e)
            j["finished_at"] = _now()
            _append_log(j, f"FAILED: {e}")
            save_job(j)
            prog(f"Failed: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "job_id": jid, "studio_job": job}


def distill_with_teacher(
    prompts: list[str],
    *,
    teacher_model: str = "openai/gpt-4o-mini",
    api_key: str = "",
    base_url: str = "",
    name: str = "distill",
    system: str = "Answer helpfully and completely.",
    use_openrouter_distill_flag: bool = True,
) -> dict[str, Any]:
    """
    Call teacher (OpenRouter or OpenAI) for each prompt → write JSONL dataset.
    OpenRouter: set enforce_distillable_text when supported via extra body field
    (best-effort; ignored if provider rejects).
    """
    from app.core.services.llm.llm import LLMError, chat_completion
    from app.core.services.system.ops_monitor import log_event

    creds = resolve_cloud_credentials(api_key=api_key, base_url=base_url, prefer="")
    key, base = creds["api_key"], creds["base_url"]
    if not key:
        return {"ok": False, "error": "No API key for teacher"}
    if not prompts:
        return {"ok": False, "error": "No prompts to distill"}

    ds_id = str(uuid.uuid4())[:10]
    out_dir = model_datasets_dir() / ds_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "train.jsonl"
    samples: list[dict[str, Any]] = []
    errors = 0
    for i, prompt in enumerate(prompts):
        prompt = (prompt or "").strip()
        if not prompt:
            continue
        try:
            # OpenRouter distill flag is not in our chat_completion body — still works for allowed models
            reply = chat_completion(
                api_key=key,
                base_url=base,
                model=teacher_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                timeout=90.0,
                max_tokens=1500,
                temperature=0.4,
                normalize_tools=False,
            )
            samples.append(
                {
                    "messages": [
                        {"role": "user", "content": prompt[:8000]},
                        {"role": "assistant", "content": str(reply or "")[:8000]},
                    ]
                }
            )
        except (LLMError, Exception):
            errors += 1
            continue

    with path.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    meta = {
        "id": ds_id,
        "name": name,
        "path": str(path),
        "count": len(samples),
        "source": "distill",
        "teacher_model": teacher_model,
        "teacher_base": base,
        "errors": errors,
        "created_at": _now(),
    }
    _write_json(out_dir / "meta.json", meta)
    log_event(
        "dataset",
        f"Distilled {len(samples)} pairs via {teacher_model} (err={errors})",
        source="distill",
    )
    return {"ok": True, "dataset": meta}


def distill_from_dataset_prompts(
    dataset_id: str,
    *,
    teacher_model: str = "openai/gpt-4o-mini",
    api_key: str = "",
    base_url: str = "",
    max_prompts: int = 40,
) -> dict[str, Any]:
    """Re-distill: take user sides from an existing JSONL as prompts."""
    meta = _read_json(model_datasets_dir() / dataset_id / "meta.json", None)
    if not isinstance(meta, dict):
        return {"ok": False, "error": "Dataset not found"}
    path = Path(str(meta.get("path") or ""))
    prompts: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if len(prompts) >= max_prompts:
                break
            try:
                obj = json.loads(line)
                msgs = obj.get("messages") or []
                for m in msgs:
                    if m.get("role") == "user" and m.get("content"):
                        prompts.append(str(m["content"]))
                        break
            except json.JSONDecodeError:
                continue
    return distill_with_teacher(
        prompts,
        teacher_model=teacher_model,
        api_key=api_key,
        base_url=base_url,
        name=f"distill-from-{dataset_id[:6]}",
    )


def create_ollama_modelfile_model(
    name: str,
    *,
    from_model: str = "llama3.2",
    system_prompt: str = "",
) -> dict[str, Any]:
    """Create local Ollama model via /api/create (Modelfile text)."""
    import json
    import urllib.request

    name = (name or "").strip().replace(" ", "-").lower()
    if not name:
        return {"ok": False, "error": "Name required"}
    from_model = (from_model or "llama3.2").strip()
    system_prompt = (system_prompt or "You are a helpful assistant.").strip()
    modelfile = f"FROM {from_model}\nSYSTEM \"\"\"{system_prompt}\"\"\"\n"
    body = json.dumps({"name": name, "modelfile": modelfile, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/create",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        from app.core.services.llm.model_profiles import create_profile

        prof = create_profile(
            f"Offline · Ollama (local) · {name}",
            kind="ollama",
            base_url="http://127.0.0.1:11434/v1",
            model=name,
            api_key="ollama",
            system_prompt=system_prompt,
            notes=f"Created via Modelfile FROM {from_model}",
        )
        return {"ok": True, "model": name, "profile": prof, "raw": raw[:300]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def ab_eval_profiles(
    profile_a_id: str,
    profile_b_id: str,
    prompts: list[str],
) -> dict[str, Any]:
    """Run same prompts on two profiles; return comparison rows."""
    from app.core.services.llm.model_profiles import get_profile, profile_to_llm_config, test_profile_completion
    from app.core.services.llm.llm import LLMError, chat_completion

    pa = get_profile(profile_a_id)
    pb = get_profile(profile_b_id)
    if not pa or not pb:
        return {"ok": False, "error": "Both profiles required"}
    ca, cb = profile_to_llm_config(pa), profile_to_llm_config(pb)
    rows: list[dict[str, Any]] = []
    for prompt in prompts:
        prompt = (prompt or "").strip()
        if not prompt:
            continue
        row: dict[str, Any] = {"prompt": prompt, "a": "", "b": "", "error_a": "", "error_b": ""}
        for label, cfg, key in (("a", ca, "a"), ("b", cb, "b")):
            try:
                text = chat_completion(
                    api_key=cfg["api_key"],
                    model=cfg["model"],
                    base_url=cfg["base_url"],
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60.0,
                    max_tokens=500,
                    temperature=0.3,
                    normalize_tools=False,
                )
                row[key] = str(text)[:2000]
            except Exception as e:  # noqa: BLE001
                row[f"error_{key}"] = str(e)
        rows.append(row)
    return {
        "ok": True,
        "profile_a": pa.get("name"),
        "profile_b": pb.get("name"),
        "rows": rows,
    }
