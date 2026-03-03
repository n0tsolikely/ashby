from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union

from ashby.modules.meetings.schemas.plan import UIState


SpeakerHint = Optional[Union[int, str]]


def _norm_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _norm_lower(v: Any) -> Optional[str]:
    s = _norm_str(v)
    return s.lower() if s is not None else None


def _norm_upper(v: Any) -> Optional[str]:
    s = _norm_str(v)
    return s.upper() if s is not None else None


def _norm_speakers(v: Any) -> SpeakerHint:
    """Normalize speaker hint across doors.

    Accepted canonical shapes:
      - int (>=1)
      - "auto"

    We also tolerate string digits ("2") and coerce to int.
    Any other string is preserved (so callers can round-trip) but will
    likely fail strict validation until a later door/UX quest tightens it.
    """

    if v is None:
        return None

    if isinstance(v, bool):
        # avoid treating True/False as 1/0 speakers
        return None

    if isinstance(v, int):
        return v

    s = _norm_str(v)
    if s is None:
        return None

    sl = s.strip().lower()
    if sl == "auto":
        return "auto"

    # Telegram door uses labels like '3+'; treat that as a numeric hint (3).
    if sl.endswith("+") and sl[:-1].isdigit():
        try:
            return int(sl[:-1])
        except Exception:
            return s

    if sl.isdigit():
        try:
            return int(sl)
        except Exception:
            return s

    return s


@dataclass(frozen=True)
class RunRequest:
    """Door-facing run param contract.

    This is the stable structure doors must produce BEFORE the router builds a plan.

    Field names are canonical:
      - mode
      - template_id
      - retention
      - speakers
      - transcript_version_id
    """

    mode: Optional[str] = None
    template_id: Optional[str] = None
    retention: Optional[str] = None
    speakers: SpeakerHint = None
    diarization_enabled: Optional[bool] = None
    transcript_version_id: Optional[str] = None
    include_citations: bool = False
    show_empty_sections: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunRequest":
        # tolerate legacy key 'template'
        template_id = payload.get("template_id")
        if template_id is None:
            template_id = payload.get("template")

        transcript_version_id = payload.get("transcript_version_id")
        if transcript_version_id is None:
            # legacy aliases tolerated for back-compat while doors converge.
            transcript_version_id = payload.get("transcript_id")
        if transcript_version_id is None:
            transcript_version_id = payload.get("active_transcript_version_id")

        speakers = payload.get("speakers")
        if speakers is None:
            speakers = payload.get("speaker_count")
        if speakers is None:
            speakers = payload.get("num_speakers")

        diarization_enabled = payload.get("diarization_enabled")
        if diarization_enabled is None:
            diarization_enabled = payload.get("diarize")
        if isinstance(diarization_enabled, bool):
            diarization_value: Optional[bool] = diarization_enabled
        else:
            diarization_value = None

        include_citations = payload.get("include_citations")
        if include_citations is None:
            include_citations = payload.get("citations")
        if include_citations is None:
            include_citations = payload.get("show_citations")

        show_empty_sections = payload.get("show_empty_sections")
        if show_empty_sections is None:
            show_empty_sections = payload.get("show_sections")
        if show_empty_sections is None:
            show_empty_sections = payload.get("show_empty")

        include_citations_value = bool(include_citations) if isinstance(include_citations, bool) else False
        show_empty_sections_value = bool(show_empty_sections) if isinstance(show_empty_sections, bool) else False

        return cls(
            mode=_norm_lower(payload.get("mode")),
            template_id=_norm_lower(template_id),
            retention=_norm_upper(payload.get("retention")),
            speakers=_norm_speakers(speakers),
            diarization_enabled=diarization_value,
            transcript_version_id=_norm_str(transcript_version_id),
            include_citations=include_citations_value,
            show_empty_sections=show_empty_sections_value,
        )

    @classmethod
    def from_ui_state(cls, ui: UIState) -> "RunRequest":
        return cls(
            mode=_norm_lower(ui.mode),
            template_id=_norm_lower(ui.template),
            retention=_norm_upper(ui.retention),
            speakers=_norm_speakers(ui.speakers),
            diarization_enabled=ui.diarization_enabled if isinstance(ui.diarization_enabled, bool) else None,
            transcript_version_id=_norm_str(ui.transcript_version_id),
            include_citations=bool(ui.include_citations),
            show_empty_sections=bool(ui.show_empty_sections),
        )

    def to_ui_state(self) -> UIState:
        # UIState still uses the field name 'template' (legacy) but it is semantically template_id.
        return UIState(
            mode=_norm_lower(self.mode),
            template=_norm_lower(self.template_id),
            retention=_norm_upper(self.retention),
            speakers=_norm_speakers(self.speakers),
            diarization_enabled=self.diarization_enabled if isinstance(self.diarization_enabled, bool) else None,
            transcript_version_id=_norm_str(self.transcript_version_id),
            include_citations=bool(self.include_citations),
            show_empty_sections=bool(self.show_empty_sections),
        )
