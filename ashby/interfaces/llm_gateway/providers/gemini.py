from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from ashby.interfaces.llm_gateway.schemas import FormalizeRequest
from ashby.modules.meetings.formalize.retention_prompts import get_retention_prompt


class GeminiProvider:
    """Gemini adapter used by the LLM gateway.

    Key rails:
    - API key from env only (GEMINI_API_KEY).
    - Model from env only (GEMINI_MODEL, default gemini-1.5-flash).
    """

    provider_name = "gemini"

    def __init__(self) -> None:
        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for llm_gateway startup")
        self._api_key = api_key
        self.model = (os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()

    def _build_prompt(self, request: FormalizeRequest) -> str:
        retention_policy = get_retention_prompt(request.retention)
        if request.mode == "meeting":
            schema_keys = "header, participants, topics, decisions, action_items, notes, open_questions"
            mode_rules = (
                "meeting schema rules: citations are required for notes, topics, decisions, action_items, open_questions. "
                "When segment mapping is unavailable, use segment_id=0 as whole-transcript anchor."
            )
        else:
            schema_keys = "header, narrative_sections, action_items, key_points, feelings, mood"
            mode_rules = (
                "journal schema rules: key_points/action_items with factual claims should include citations. "
                "When segment mapping is unavailable, use segment_id=0 as whole-transcript anchor."
            )
        return (
            "Return ONLY JSON object (no markdown fences). "
            f"Mode={request.mode}; required top-level keys={schema_keys}. "
            "Output must be schema-valid for Stuart formalization gateway.\n"
            "For any schema field typed as string, return plain human-readable text only. "
            "Never embed JSON objects/arrays (or escaped JSON) inside string fields.\n"
            f"Template={request.template_id}; retention={request.retention}.\n"
            f"Retention policy: {retention_policy}\n"
            f"{mode_rules}\n"
            "For MED, HIGH, and NEAR_VERBATIM keep at least one substantive content item "
            "(notes for meeting or narrative_sections for journal).\n\n"
            f"TRANSCRIPT:\n{request.transcript_text}"
        )

    def _gemini_url(self) -> str:
        model_enc = urllib.parse.quote(self.model, safe="")
        key_enc = urllib.parse.quote(self._api_key, safe="")
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model_enc}:generateContent?key={key_enc}"

    def _generate(self, request: FormalizeRequest) -> Dict[str, Any]:
        payload = {
            "contents": [{"parts": [{"text": self._build_prompt(request)}]}],
            "generationConfig": {"temperature": 0.2},
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._gemini_url(),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"gemini_http_error status={e.code} body={detail[:500]}") from e
        except Exception as e:
            raise RuntimeError(f"gemini_request_failed: {type(e).__name__}: {e}") from e

    @staticmethod
    def _extract_text(resp_json: Dict[str, Any]) -> str:
        try:
            cands = resp_json.get("candidates") or []
            parts = (((cands[0] or {}).get("content") or {}).get("parts") or [])
            text = (parts[0] or {}).get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_usage(resp_json: Dict[str, Any], transcript_text: str) -> Dict[str, Any]:
        usage = resp_json.get("usageMetadata") if isinstance(resp_json, dict) else None
        if not isinstance(usage, dict):
            return {"char_count": len(transcript_text)}
        return {
            "prompt_tokens": usage.get("promptTokenCount"),
            "completion_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
            "char_count": len(transcript_text),
        }

    @staticmethod
    def _map_text_to_output_json(request: FormalizeRequest, text: str) -> Dict[str, Any]:
        if request.mode == "meeting":
            return {
                "header": {
                    "title": "Meeting Minutes",
                    "mode": "meeting",
                    "retention": request.retention,
                    "template_id": request.template_id,
                },
                "participants": [],
                "topics": [],
                "decisions": [],
                "action_items": [],
                "notes": [{"note_id": "note_0001", "text": text or "No summary content returned.", "citations": [{"segment_id": 0}]}],
                "open_questions": [],
            }
        return {
            "header": {
                "title": "Journal Entry",
                "mode": "journal",
                "retention": request.retention,
                "template_id": request.template_id,
            },
            "narrative_sections": [{"section_id": "sec_001", "text": text or "No summary content returned."}],
            "action_items": [],
            "key_points": [],
            "feelings": [],
            "mood": "",
        }

    def formalize(self, request: FormalizeRequest) -> Dict[str, Any]:
        resp_json = self._generate(request)
        text = self._extract_text(resp_json)

        # If model returned JSON string payload, prefer explicit output_json/evidence_map/usage.
        as_json: Dict[str, Any] | None = None
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    as_json = parsed
            except Exception:
                as_json = None

        if isinstance(as_json, dict):
            output_json = as_json.get("output_json")
            evidence_map = as_json.get("evidence_map")
            usage = as_json.get("usage")
            return {
                "output_json": output_json if isinstance(output_json, dict) else self._map_text_to_output_json(request, text),
                "evidence_map": evidence_map if isinstance(evidence_map, dict) else {},
                "usage": usage if isinstance(usage, dict) else self._extract_usage(resp_json, request.transcript_text),
            }

        return {
            "output_json": self._map_text_to_output_json(request, text),
            "evidence_map": {},
            "usage": self._extract_usage(resp_json, request.transcript_text),
        }
