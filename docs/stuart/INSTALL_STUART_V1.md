# Stuart v1 — Install & verify

This is the “don’t guess” install path for **Stuart v1** (Ashby meetings module).

## 1) System deps

Start here:
- [SYSTEM_DEPENDENCIES.md](./SYSTEM_DEPENDENCIES.md)

At minimum you want:
- `ffmpeg` on PATH

If you want real PDFs:
- Install the WeasyPrint (Cairo/Pango) stack.

## 2) Python environment (recommended)

```bash
cd /path/to/Ashby_Engine
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
```

## 3) Install Python deps

From the repo root (`Ashby_Engine`):

```bash
pip install -r requirements-stuart-v1.txt
```

### Torch note (diarization)
Diarization uses `pyannote.audio`, which depends on **torch**.

Because torch wheels differ per machine (CPU vs CUDA), we keep torch out of `requirements-stuart-v1.txt`.

Install torch in whatever way matches your hardware, then install the requirements file.

## 4) Configure runtime root

Stuart writes all sessions/runs/artifacts under `STUART_ROOT`.

Default (if unset):
- `~/ashby_runtime/stuart`

Optional override:
```bash
export STUART_ROOT="$HOME/ashby_runtime/stuart"
```

## 5) Tokens / remote toggles

### HuggingFace (pyannote diarization)
If you want diarization:

```bash
export HUGGINGFACE_TOKEN="..."
```

Notes:
- Some models are gated (you must accept terms in HuggingFace).
- If the token is missing or lacks access, diarization should fail loudly.

### OpenAI (remote formalize)
Stuart supports deterministic local formalization, and optional remote LLM formalization.

Enable remote:
```bash
export ASHBY_MEETINGS_LLM_ENABLED=1
export OPENAI_API_KEY="..."
```

## 6) Run preflight

Default mode (required checks only):
```bash
python3 scripts/stuart_preflight.py
```

Strict mode (treat missing “real engines” as failures):
```bash
python3 scripts/stuart_preflight.py --strict
```

JSON mode:
```bash
python3 scripts/stuart_preflight.py --json
```

## 7) Smoke test

### Run the unit tests
```bash
PYTHONPATH=. pytest -q
```

### Run the web door
```bash
PYTHONPATH=. python3 scripts/stuart_web.py
```

Then open the printed URL.

## 8) Common failure modes

- **ffmpeg missing** → normalize stage fails immediately.
- **WeasyPrint import fails** → you’re missing Cairo/Pango system deps.
- **pyannote fails with auth errors** → token missing or gated model access not accepted.
