#!/usr/bin/env python3
"""Stuart v1 preflight checks (new-machine install sanity).

This script is intentionally lightweight and side-effect minimal.
It does NOT download models.

Usage:
  python3 scripts/stuart_preflight.py
  python3 scripts/stuart_preflight.py --strict
  python3 scripts/stuart_preflight.py --json

Exit codes:
  0 = ok (required checks pass)
  2 = one or more required checks failed
  3 = --strict and one or more optional checks failed
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    detail: str = ""
    hint: str = ""


def _repo_root() -> Path:
    # scripts/ is one level below the repo root
    return Path(__file__).resolve().parents[1]


def _ensure_repo_on_syspath(root: Path) -> None:
    p = str(root)
    if p not in sys.path:
        sys.path.insert(0, p)


def _import_check(module: str, *, required: bool, hint: str = "") -> CheckResult:
    try:
        m = importlib.import_module(module)
        ver = getattr(m, "__version__", None)
        det = "import ok" + (f" (version={ver})" if ver else "")
        return CheckResult(name=f"import:{module}", ok=True, required=required, detail=det)
    except Exception as e:
        return CheckResult(
            name=f"import:{module}",
            ok=False,
            required=required,
            detail=f"{type(e).__name__}: {e}",
            hint=hint,
        )


def _python_version_check(*, required: bool) -> CheckResult:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    det = f"{v.major}.{v.minor}.{v.micro}"
    hint = "Use Python 3.10+" if not ok else ""
    return CheckResult(name="python>=3.10", ok=ok, required=required, detail=det, hint=hint)


def _ffmpeg_check(*, required: bool) -> CheckResult:
    p = shutil.which("ffmpeg")
    ok = bool(p)
    hint = "Install ffmpeg and ensure it is on PATH (required for normalize stage)." if not ok else ""
    return CheckResult(name="ffmpeg on PATH", ok=ok, required=required, detail=(p or "not found"), hint=hint)


def _stuart_root_check(*, required: bool) -> CheckResult:
    sr = os.environ.get("STUART_ROOT")
    if not sr:
        # Mirror ashby.modules.meetings.config default
        sr = str(Path.home() / "ashby_runtime" / "stuart")
    p = Path(sr).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
        # Ensure it's writable by attempting to create a temp marker then remove.
        marker = p / ".preflight_write_test"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink(missing_ok=True)
        return CheckResult(name="STUART_ROOT writable", ok=True, required=required, detail=str(p))
    except Exception as e:
        return CheckResult(
            name="STUART_ROOT writable",
            ok=False,
            required=required,
            detail=f"{type(e).__name__}: {e}",
            hint="Set STUART_ROOT to a writable directory.",
        )


def _env_var_check(var: str, *, required: bool, hint: str) -> CheckResult:
    v = (os.environ.get(var) or "").strip()
    ok = bool(v)
    return CheckResult(
        name=f"env:{var}",
        ok=ok,
        required=required,
        detail=("set" if ok else "missing"),
        hint=(hint if not ok else ""),
    )


def run_checks(*, strict: bool) -> List[CheckResult]:
    root = _repo_root()
    _ensure_repo_on_syspath(root)

    results: List[CheckResult] = []

    # Baseline
    results.append(_python_version_check(required=True))
    results.append(CheckResult(name="repo root", ok=root.exists(), required=True, detail=str(root)))

    # Ashby import sanity (required for anything)
    results.append(
        _import_check(
            "ashby",
            required=True,
            hint="Ensure PYTHONPATH includes the Ashby_Engine repo root (or run from repo).",
        )
    )

    # Runtime root
    results.append(_stuart_root_check(required=True))

    # System deps
    results.append(_ffmpeg_check(required=True))

    # Door deps (web)
    results.append(_import_check("fastapi", required=strict, hint="pip install -r requirements-stuart-v1.txt"))
    results.append(_import_check("uvicorn", required=strict, hint="pip install -r requirements-stuart-v1.txt"))
    results.append(_import_check("jinja2", required=strict, hint="pip install -r requirements-stuart-v1.txt"))
    results.append(_import_check("multipart", required=False, hint="pip install python-multipart"))

    # Real engines (recommended; strict => required)
    results.append(
        _import_check(
            "weasyprint",
            required=strict,
            hint="Install OS Cairo/Pango deps then: pip install weasyprint",
        )
    )
    results.append(
        _import_check(
            "faster_whisper",
            required=strict,
            hint="pip install faster-whisper (and ctranslate2)",
        )
    )

    # torch is required if you want pyannote diarization
    results.append(
        _import_check(
            "torch",
            required=strict,
            hint="Install torch with the correct CPU/GPU wheel for your platform (see PyTorch install docs).",
        )
    )
    results.append(
        _import_check(
            "pyannote.audio",
            required=strict,
            hint="pip install pyannote.audio (requires torch). Some models are gated on HuggingFace.",
        )
    )

    # Optional remote formalizer deps
    results.append(_import_check("openai", required=False, hint="pip install openai"))
    results.append(
        _env_var_check(
            "OPENAI_API_KEY",
            required=False,
            hint="Set OPENAI_API_KEY if using remote formalize (ASHBY_MEETINGS_LLM_ENABLED=1).",
        )
    )

    # HF token guidance (only required if diarization is in use)
    results.append(
        _env_var_check(
            "HUGGINGFACE_TOKEN",
            required=False,
            hint="Set HUGGINGFACE_TOKEN for pyannote diarization (and accept gated model terms if required).",
        )
    )

    return results


def _status_label(r: CheckResult) -> str:
    if r.ok:
        return "PASS"
    if r.required:
        return "FAIL"
    return "WARN"


def main() -> int:
    ap = argparse.ArgumentParser(description="Stuart v1 preflight checks")
    ap.add_argument("--strict", action="store_true", help="Fail if optional checks are missing (real engines + web door)")
    ap.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = ap.parse_args()

    results = run_checks(strict=bool(args.strict))

    # Determine exit code
    required_fail = any((not r.ok) and r.required for r in results)
    optional_fail = any((not r.ok) and (not r.required) for r in results)

    meta: Dict[str, Any] = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "repo_root": str(_repo_root()),
        "strict": bool(args.strict),
    }

    if args.json:
        payload = {
            "meta": meta,
            "results": [asdict(r) for r in results],
            "ok": (not required_fail) and (not (args.strict and optional_fail)),
        }
        print(json.dumps(payload, indent=2))
    else:
        print("STUART PREFLIGHT (v1)")
        print(f"Platform: {meta['platform']}")
        print(f"Python:   {meta['python']}")
        print(f"Repo:     {meta['repo_root']}")
        print(f"Mode:     {'STRICT' if args.strict else 'DEFAULT'}")
        print("")
        for r in results:
            lab = _status_label(r)
            req = "required" if r.required else "optional"
            line = f"[{lab}] {r.name} ({req})"
            if r.detail:
                line += f" :: {r.detail}"
            print(line)
            if (not r.ok) and r.hint:
                print(f"      hint: {r.hint}")
        print("")
        if required_fail:
            print("RESULT: FAIL (required checks)")
        elif args.strict and optional_fail:
            print("RESULT: FAIL (--strict)")
        else:
            print("RESULT: OK")

    if required_fail:
        return 2
    if args.strict and optional_fail:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
