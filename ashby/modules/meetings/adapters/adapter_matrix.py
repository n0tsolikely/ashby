from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Protocol, Any

from ashby.core.profile import ExecutionProfile
from ashby.modules.meetings.pipeline.transcribe import transcribe_stub
from ashby.modules.meetings.adapters.transcribe_faster_whisper import transcribe_faster_whisper_or_stub
from ashby.modules.meetings.pipeline.diarize import diarize_stub
from ashby.modules.meetings.adapters.diarize_pyannote import diarize_pyannote
from ashby.modules.meetings.pipeline.normalize import normalize_ffmpeg
from ashby.modules.meetings.pipeline.align import align_transcript_time_overlap
from ashby.modules.meetings.render.export_pdf import export_pdf_stub
from ashby.modules.meetings.render.pdf_weasyprint import render_pdf_adapter


# Stage callable protocols (kept loose for v1 stubs; later quests tighten signatures)
TranscribeFn = Callable[[Path], Dict[str, Any]]
DiarizeFn = Callable[[Path], Dict[str, Any]]
PdfFn = Callable[..., Dict[str, Any]]
NormalizeFn = Callable[[Path, Path], Dict[str, Any]]
AlignFn = Callable[[Path], Dict[str, Any]]


@dataclass(frozen=True)
class MeetingsAdapterMatrix:
    normalize: NormalizeFn
    align: AlignFn
    profile: ExecutionProfile
    transcribe: TranscribeFn
    diarize: DiarizeFn
    pdf: PdfFn


def get_meetings_adapter_matrix(profile: ExecutionProfile) -> MeetingsAdapterMatrix:
    """Return adapter matrix for the given profile.

    V1 behavior:
    - All profiles still use stubs until Post-30 real engine quests replace them.
    - The matrix exists now so later swaps don't require refactors.
    """
    # LOCAL_ONLY default
    return MeetingsAdapterMatrix(
        profile=profile,
        normalize=normalize_ffmpeg,
        align=align_transcript_time_overlap,
        transcribe=transcribe_faster_whisper_or_stub,
        diarize=diarize_pyannote,
        pdf=render_pdf_adapter,
    )
