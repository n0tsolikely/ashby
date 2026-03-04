#!/usr/bin/env bash
set -euo pipefail

# D12 smoke scaffold (phase-only in QUEST_198).
# QUEST_200 fills phases 1-3 (server/create/upload).

DATE_UTC="$(date -u +%F)"
OUT_DIR="docs/smoke_outputs/${DATE_UTC}"
RUN_LOG="${OUT_DIR}/run.log"
MEETING_FIXTURE="tests/fixtures/stuart_smoke/meeting_fixture_3speakers_36s.wav"
JOURNAL_FIXTURE="tests/fixtures/stuart_smoke/journal_fixture_1speaker_42s.wav"
USE_MINI_FIXTURES="${STUART_SMOKE_USE_MINI_FIXTURES:-0}"
BASE_URL="${STUART_BASE_URL:-http://127.0.0.1:8844}"
FRONTEND_URL="${STUART_FRONTEND_URL:-http://127.0.0.1:4173}"
AUTOSTART_BACKEND="${STUART_SMOKE_AUTOSTART_BACKEND:-1}"
AUTOSTART_FRONTEND="${STUART_SMOKE_AUTOSTART_FRONTEND:-1}"
STARTED_BACKEND_PID=""
STARTED_FRONTEND_PID=""
RUN_TIMEOUT_SEC="${STUART_SMOKE_RUN_TIMEOUT_SEC:-1800}"

if [[ "${USE_MINI_FIXTURES}" == "1" ]]; then
  MEETING_FIXTURE="tests/fixtures/stuart_smoke/meeting_fixture_3speakers_8s.wav"
  JOURNAL_FIXTURE="tests/fixtures/stuart_smoke/journal_fixture_1speaker_8s.wav"
fi

mkdir -p "${OUT_DIR}"
exec > >(tee "${RUN_LOG}") 2>&1

cleanup() {
  if [[ -n "${STARTED_BACKEND_PID}" ]] && kill -0 "${STARTED_BACKEND_PID}" 2>/dev/null; then
    kill "${STARTED_BACKEND_PID}" || true
  fi
  if [[ -n "${STARTED_FRONTEND_PID}" ]] && kill -0 "${STARTED_FRONTEND_PID}" 2>/dev/null; then
    kill "${STARTED_FRONTEND_PID}" || true
  fi
}
trap cleanup EXIT

json_get() {
  local key="$1"
  python3 -c 'import json,sys; key=sys.argv[1]; obj=json.loads(sys.stdin.read()); print(obj.get(key) or obj.get("result", {}).get(key) or "")' "$key"
}

json_path() {
  local path="$1"
  python3 -c 'import json,sys; path=sys.argv[1].split("."); obj=json.loads(sys.stdin.read()); cur=obj
for p in path:
    if isinstance(cur, dict):
        cur = cur.get(p)
    else:
        cur = None
        break
print("" if cur is None else cur)' "$path"
}

wait_api() {
  local tries=30
  local i=1
  while [[ "${i}" -le "${tries}" ]]; do
    if curl --noproxy '*' -fsS "${BASE_URL}/api/registry" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    i=$((i+1))
  done
  return 1
}

wait_frontend() {
  local tries=45
  local i=1
  while [[ "${i}" -le "${tries}" ]]; do
    if curl --noproxy '*' -fsS "${FRONTEND_URL}/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    i=$((i+1))
  done
  return 1
}

wait_run_terminal() {
  local run_id="$1"
  local tries="${RUN_TIMEOUT_SEC}"
  local i=1
  while [[ "${i}" -le "${tries}" ]]; do
    local st
    st="$(curl --noproxy '*' -fsS "${BASE_URL}/api/runs/${run_id}" | json_path 'state.status')"
    if [[ "${st}" == "succeeded" ]]; then
      echo "RUN ${run_id} status=${st}"
      return 0
    fi
    if [[ "${st}" == "failed" || "${st}" == "cancelled" ]]; then
      echo "RUN ${run_id} status=${st}"
      return 1
    fi
    sleep 1
    i=$((i+1))
  done
  echo "RUN ${run_id} status=timeout"
  return 1
}

echo "D12 FULL SYSTEM SMOKE TEST"
echo "DATE_UTC=${DATE_UTC}"
echo "OUT_DIR=${OUT_DIR}"
echo "BASE_URL=${BASE_URL}"
echo "FRONTEND_URL=${FRONTEND_URL}"
echo "USE_MINI_FIXTURES=${USE_MINI_FIXTURES}"
echo "MEETING_FIXTURE=${MEETING_FIXTURE}"
echo "JOURNAL_FIXTURE=${JOURNAL_FIXTURE}"
echo "SKIP: HYBRID profile smoke not enabled in baseline LOCAL_ONLY run"
echo "SKIP: CLOUD profile smoke not enabled in baseline LOCAL_ONLY run"
echo

echo "PHASE 1: Start server"
if ! wait_api; then
  if [[ "${AUTOSTART_BACKEND}" != "1" ]]; then
    echo "FAIL: API not reachable at ${BASE_URL} and autostart disabled."
    exit 1
  fi
  echo "API not reachable. Starting backend via scripts/stuart_web.py ..."
  cd /home/notsolikely/Ashby_Engine
  PYTHONPATH=/home/notsolikely/Ashby_Engine python3 scripts/stuart_web.py >/tmp/stuart_smoke_backend.log 2>&1 &
  STARTED_BACKEND_PID="$!"
  cd - >/dev/null
  if ! wait_api; then
    echo "FAIL: backend startup failed. See /tmp/stuart_smoke_backend.log"
    exit 1
  fi
fi
echo "PASS: API reachable at ${BASE_URL}"

echo "PHASE 2: Create session(s)"
MEETING_CREATE="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/sessions" -H 'Content-Type: application/json' -d '{"mode":"meeting","title":"D12 Meeting Fixture"}')"
JOURNAL_CREATE="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/sessions" -H 'Content-Type: application/json' -d '{"mode":"journal","title":"D12 Journal Fixture"}')"
MEETING_SESSION_ID="$(printf '%s' "${MEETING_CREATE}" | json_get session_id)"
JOURNAL_SESSION_ID="$(printf '%s' "${JOURNAL_CREATE}" | json_get session_id)"
if [[ -z "${MEETING_SESSION_ID}" || -z "${JOURNAL_SESSION_ID}" ]]; then
  echo "FAIL: unable to parse created session ids"
  echo "MEETING_CREATE=${MEETING_CREATE}"
  echo "JOURNAL_CREATE=${JOURNAL_CREATE}"
  exit 1
fi
echo "PASS: meeting_session_id=${MEETING_SESSION_ID}"
echo "PASS: journal_session_id=${JOURNAL_SESSION_ID}"

echo "PHASE 3: Upload fixture audio"
curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/upload?session_id=${MEETING_SESSION_ID}&mode=meeting&title=D12%20Meeting%20Fixture" \
  -F "file=@${MEETING_FIXTURE}" >/tmp/d12_upload_meeting.json
curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/upload?session_id=${JOURNAL_SESSION_ID}&mode=journal&title=D12%20Journal%20Fixture" \
  -F "file=@${JOURNAL_FIXTURE}" >/tmp/d12_upload_journal.json
echo "PASS: uploaded meeting fixture -> /tmp/d12_upload_meeting.json"
echo "PASS: uploaded journal fixture -> /tmp/d12_upload_journal.json"

echo "PHASE 4: Transcribe (diarize ON/OFF)"
TRANSCRIBE_ON="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/transcribe" -H 'Content-Type: application/json' -d "{\"session_id\":\"${MEETING_SESSION_ID}\",\"mode\":\"meeting\",\"diarization_enabled\":true}")"
TRANSCRIBE_OFF="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/transcribe" -H 'Content-Type: application/json' -d "{\"session_id\":\"${MEETING_SESSION_ID}\",\"mode\":\"meeting\",\"diarization_enabled\":false}")"
RUN_ON="$(printf '%s' "${TRANSCRIBE_ON}" | json_get run_id)"
RUN_OFF="$(printf '%s' "${TRANSCRIBE_OFF}" | json_get run_id)"
if [[ -z "${RUN_ON}" || -z "${RUN_OFF}" ]]; then
  echo "FAIL: unable to parse transcribe run ids"
  echo "TRANSCRIBE_ON=${TRANSCRIBE_ON}"
  echo "TRANSCRIBE_OFF=${TRANSCRIBE_OFF}"
  exit 1
fi
wait_run_terminal "${RUN_ON}"
wait_run_terminal "${RUN_OFF}"
TRANSCRIPTS_JSON="$(curl --noproxy '*' -fsS "${BASE_URL}/api/sessions/${MEETING_SESSION_ID}/transcripts")"
printf '%s' "${TRANSCRIPTS_JSON}" >/tmp/d12_transcripts_meeting.json
TV_COUNT="$(printf '%s' "${TRANSCRIPTS_JSON}" | python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); rows=obj.get("result",{}).get("transcripts",[]) if isinstance(obj.get("result"),dict) else obj.get("transcripts",[]); print(len(rows) if isinstance(rows,list) else 0)')"
if [[ "${TV_COUNT}" -lt 2 ]]; then
  echo "FAIL: expected at least 2 transcript versions, got ${TV_COUNT}"
  exit 1
fi
echo "PASS: transcript_versions_count=${TV_COUNT} (details in /tmp/d12_transcripts_meeting.json)"

echo "PHASE 5: Map speakers"
DIARIZED_TRV="$(printf '%s' "${TRANSCRIPTS_JSON}" | python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); rows=obj.get("transcripts",[]); out=""; 
for r in rows:
    if bool(r.get("diarization_enabled")):
        out=str(r.get("transcript_version_id") or "").strip()
        break
print(out)')"
if [[ -z "${DIARIZED_TRV}" ]]; then
  echo "FAIL: no diarized transcript version found for speaker-map phase"
  exit 1
fi
PUT_MAP_RESP="$(curl --noproxy '*' -fsS -X PUT "${BASE_URL}/api/transcripts/${DIARIZED_TRV}/speaker_map" -H 'Content-Type: application/json' -d '{"mapping":{"SPEAKER_00":"Host","SPEAKER_01":"Guest"},"author":"smoke"}')"
GET_MAP_RESP="$(curl --noproxy '*' -fsS "${BASE_URL}/api/transcripts/${DIARIZED_TRV}/speaker_map")"
printf '%s' "${GET_MAP_RESP}" >/tmp/d12_speaker_map_get.json
MAP_OK="$(printf '%s' "${GET_MAP_RESP}" | python3 -c 'import json,sys; obj=json.loads(sys.stdin.read()); m=obj.get("speaker_map") or {}; print("yes" if isinstance(m,dict) and m.get("SPEAKER_00")=="Host" else "no")')"
if [[ "${MAP_OK}" != "yes" ]]; then
  echo "FAIL: speaker_map persistence assertion failed"
  echo "PUT_MAP_RESP=${PUT_MAP_RESP}"
  echo "GET_MAP_RESP=${GET_MAP_RESP}"
  exit 1
fi
echo "PASS: speaker_map persisted for transcript_version_id=${DIARIZED_TRV} (details in /tmp/d12_speaker_map_get.json)"

echo "PHASE 6: Formalize (DEFAULT_TEST_TEMPLATE)"
MEETING_FORMALIZE="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/run" -H 'Content-Type: application/json' -d "{\"session_id\":\"${MEETING_SESSION_ID}\",\"ui\":{\"mode\":\"meeting\",\"template_id\":\"default\",\"retention\":\"MED\",\"speakers\":\"auto\"}}")"
JOURNAL_FORMALIZE="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/run" -H 'Content-Type: application/json' -d "{\"session_id\":\"${JOURNAL_SESSION_ID}\",\"ui\":{\"mode\":\"journal\",\"template_id\":\"default\",\"retention\":\"MED\",\"speakers\":1}}")"
MEETING_FORMALIZE_RUN="$(printf '%s' "${MEETING_FORMALIZE}" | json_get run_id)"
JOURNAL_FORMALIZE_RUN="$(printf '%s' "${JOURNAL_FORMALIZE}" | json_get run_id)"
if [[ -z "${MEETING_FORMALIZE_RUN}" || -z "${JOURNAL_FORMALIZE_RUN}" ]]; then
  echo "FAIL: unable to parse formalize run ids"
  echo "MEETING_FORMALIZE=${MEETING_FORMALIZE}"
  echo "JOURNAL_FORMALIZE=${JOURNAL_FORMALIZE}"
  exit 1
fi
wait_run_terminal "${MEETING_FORMALIZE_RUN}"
wait_run_terminal "${JOURNAL_FORMALIZE_RUN}"

MEETING_RUN_JSON="$(curl --noproxy '*' -fsS "${BASE_URL}/api/runs/${MEETING_FORMALIZE_RUN}")"
JOURNAL_RUN_JSON="$(curl --noproxy '*' -fsS "${BASE_URL}/api/runs/${JOURNAL_FORMALIZE_RUN}")"
printf '%s' "${MEETING_RUN_JSON}" >/tmp/d12_meeting_formalize_run.json
printf '%s' "${JOURNAL_RUN_JSON}" >/tmp/d12_journal_formalize_run.json

MEETING_PDF_URL="$(printf '%s' "${MEETING_RUN_JSON}" | json_path 'downloads.primary.pdf.url')"
JOURNAL_PDF_URL="$(printf '%s' "${JOURNAL_RUN_JSON}" | json_path 'downloads.primary.pdf.url')"
if [[ -z "${MEETING_PDF_URL}" || -z "${JOURNAL_PDF_URL}" ]]; then
  echo "FAIL: missing PDF download url in formalize run status"
  echo "MEETING_PDF_URL=${MEETING_PDF_URL}"
  echo "JOURNAL_PDF_URL=${JOURNAL_PDF_URL}"
  exit 1
fi

python3 - << 'PY' /tmp/d12_meeting_formalize_run.json /tmp/d12_journal_formalize_run.json
import json
import sys
from pathlib import Path

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def assert_meta(run_obj: dict, mode_expected: str):
    state = run_obj.get("state") or {}
    arts = state.get("artifacts") or []
    json_path = None
    for a in arts:
        p = str((a or {}).get("path") or "")
        if p.endswith("minutes.json") or p.endswith("journal.json"):
            json_path = p
            break
    if not json_path:
        raise SystemExit(f"no formalization json artifact found for mode={mode_expected}")
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    template_id = payload.get("template_id") or (payload.get("metadata") or {}).get("template_id")
    retention = payload.get("retention") or (payload.get("metadata") or {}).get("retention")
    template_version = (
        payload.get("template_version")
        or (payload.get("metadata") or {}).get("template_version")
        or ((payload.get("template") or {}).get("version") if isinstance(payload.get("template"), dict) else None)
    )
    if str(template_id or "").strip().lower() != "default":
        raise SystemExit(f"template_id invalid for {mode_expected}: {template_id!r}")
    if str(retention or "").strip().upper() != "MED":
        raise SystemExit(f"retention invalid for {mode_expected}: {retention!r}")
    if not str(template_version or "").strip():
        raise SystemExit(f"template_version missing for {mode_expected}")
    print(f"meta_ok mode={mode_expected} template_id={template_id} retention={retention} template_version={template_version}")

assert_meta(load(Path(sys.argv[1])), "meeting")
assert_meta(load(Path(sys.argv[2])), "journal")
PY
echo "PASS: formalize meeting+journal metadata and PDF checks complete"

echo "PHASE 7: Session chat hard-lock checks"
RUN_ON_JSON="$(curl --noproxy '*' -fsS "${BASE_URL}/api/runs/${RUN_ON}")"
printf '%s' "${RUN_ON_JSON}" >/tmp/d12_run_on_status.json
DIARIZED_DETAIL_JSON="$(curl --noproxy '*' -fsS "${BASE_URL}/api/transcripts/${DIARIZED_TRV}")"
printf '%s' "${DIARIZED_DETAIL_JSON}" >/tmp/d12_transcript_detail.json

SESSION_QUERY_TOKEN="$(python3 - << 'PY' "${BASE_URL}" "${MEETING_SESSION_ID}" /tmp/d12_transcript_detail.json /tmp/d12_run_on_status.json
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

base_url = sys.argv[1].rstrip("/")
session_id = sys.argv[2]
detail = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
run_status = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
rows = detail.get("segments")
if not isinstance(rows, list):
    rows = ((detail.get("result") or {}).get("segments")) if isinstance(detail.get("result"), dict) else None
if not isinstance(rows, list):
    rows = []

blob = " ".join(str((r or {}).get("text") or "") for r in rows if isinstance(r, dict))
if not blob.strip():
    arts = ((run_status.get("state") or {}).get("artifacts")) or []
    transcript_json_path = None
    for a in arts:
        p = str((a or {}).get("path") or "")
        if p.endswith("transcript.json"):
            transcript_json_path = p
            break
    if transcript_json_path and Path(transcript_json_path).exists():
        t_obj = json.loads(Path(transcript_json_path).read_text(encoding="utf-8"))
        t_rows = t_obj.get("segments") if isinstance(t_obj.get("segments"), list) else []
        blob = " ".join(str((r or {}).get("text") or "") for r in t_rows if isinstance(r, dict))
words = []
seen = set()
for w in re.findall(r"[A-Za-z0-9_]{4,}", blob.lower()):
    if w in {"speaker", "audio", "transcript"}:
        continue
    if w in seen:
        continue
    seen.add(w)
    words.append(w)

selected = None
probe = {"ok": False, "candidates": words[:20], "selected_token": None, "hits_count": 0}
for token in words[:25]:
    qs = urllib.parse.urlencode({"q": token, "session_id": session_id, "limit": 5})
    url = f"{base_url}/api/search?{qs}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    hits = payload.get("hits") if isinstance(payload, dict) else []
    n = len(hits) if isinstance(hits, list) else 0
    if n > 0:
        selected = token
        probe["ok"] = True
        probe["selected_token"] = token
        probe["hits_count"] = n
        probe["sample_hit"] = hits[0]
        break

if not selected:
    selected = words[0] if words else "meeting"
    probe["selected_token"] = selected
    probe["hits_count"] = 0
    probe["note"] = "search returned no hits for transcript-derived tokens; continuing with truth-gate branch"

Path("/tmp/d12_search_probe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
print(selected)
PY
)"
echo "PHASE7_SEARCH_TOKEN=${SESSION_QUERY_TOKEN}"
echo "PHASE7_SEARCH_PROBE_FILE=/tmp/d12_search_probe.json"

SESSION_CHAT_PAYLOAD="$(python3 - << 'PY' "${MEETING_SESSION_ID}" "${SESSION_QUERY_TOKEN}"
import json, sys
print(json.dumps({
    "session_id": sys.argv[1],
    "text": f"Summarize evidence in this session for {sys.argv[2]}",
    "ui": {"selected_session_id": sys.argv[1]},
    "history_tail": [],
}))
PY
)"
printf '%s' "${SESSION_CHAT_PAYLOAD}" >/tmp/d12_chat_session_grounded_request.json
echo "PHASE7_SESSION_CHAT_REQUEST_JSON=${SESSION_CHAT_PAYLOAD}"
SESSION_CHAT_RESP="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/chat" -H 'Content-Type: application/json' -d "${SESSION_CHAT_PAYLOAD}")"
printf '%s' "${SESSION_CHAT_RESP}" >/tmp/d12_chat_session_grounded.json
echo "PHASE7_SESSION_CHAT_RESPONSE_FILE=/tmp/d12_chat_session_grounded.json"

python3 - << 'PY' /tmp/d12_chat_session_grounded.json "${MEETING_SESSION_ID}"
import json, sys
obj = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
reply = obj.get("reply") or {}
text = str(reply.get("text") or "")
text_l = text.lower()
citations = reply.get("citations") or []
if isinstance(citations, list) and len(citations) > 0:
    for c in citations:
        sid = str((c or {}).get("session_id") or "")
        if sid != sys.argv[2]:
            raise SystemExit(f"session chat citation leaked session_id={sid!r}")
    print(f"session_chat_citations_ok count={len(citations)}")
elif "couldn't find evidence" in text_l or "could not find evidence" in text_l:
    print("session_chat_truth_gate_no_evidence_ok")
else:
    raise SystemExit(f"session chat neither cited evidence nor emitted no-evidence truth gate text: {text!r}")
PY

LOCK_CHAT_PAYLOAD="$(python3 - << 'PY' "${MEETING_SESSION_ID}" "${JOURNAL_SESSION_ID}"
import json, sys
print(json.dumps({
    "session_id": sys.argv[1],
    "text": f"Compare this with session {sys.argv[2]} across sessions and show what is there",
    "ui": {"selected_session_id": sys.argv[1]},
    "history_tail": [],
}))
PY
)"
LOCK_CHAT_RESP="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/chat" -H 'Content-Type: application/json' -d "${LOCK_CHAT_PAYLOAD}")"
printf '%s' "${LOCK_CHAT_RESP}" >/tmp/d12_chat_session_lock.json

python3 - << 'PY' /tmp/d12_chat_session_lock.json "${MEETING_SESSION_ID}"
import json, sys
obj = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
reply = obj.get("reply") or {}
text = str(reply.get("text") or "").lower()
if "global" not in text and "across session" not in text:
    raise SystemExit("session lock response missing global guidance")
for row in (reply.get("citations") or []):
    sid = str((row or {}).get("session_id") or "")
    if sid and sid != sys.argv[2]:
        raise SystemExit(f"session lock citation leaked session_id={sid!r}")
for row in (reply.get("hits") or []):
    sid = str((row or {}).get("session_id") or "")
    if sid and sid != sys.argv[2]:
        raise SystemExit(f"session lock hit leaked session_id={sid!r}")
print("session_scope_lock_ok")
PY
echo "PASS: session chat citations + scope lock checks complete"

echo "PHASE 8: Global chat cold-start checks"
GLOBAL_CHAT_PAYLOAD="$(python3 - << 'PY' "${SESSION_QUERY_TOKEN}"
import json, sys
print(json.dumps({
    "text": f"{sys.argv[1]}",
    "ui": {},
    "history_tail": [],
}))
PY
)"
printf '%s' "${GLOBAL_CHAT_PAYLOAD}" >/tmp/d12_chat_global_request.json
echo "PHASE8_GLOBAL_CHAT_REQUEST_JSON=${GLOBAL_CHAT_PAYLOAD}"
GLOBAL_CHAT_RESP="$(curl --noproxy '*' -fsS -X POST "${BASE_URL}/api/chat/global" -H 'Content-Type: application/json' -d "${GLOBAL_CHAT_PAYLOAD}")"
printf '%s' "${GLOBAL_CHAT_RESP}" >/tmp/d12_chat_global.json
echo "PHASE8_GLOBAL_CHAT_RESPONSE_FILE=/tmp/d12_chat_global.json"

python3 - << 'PY' /tmp/d12_chat_global.json
import json, sys
obj = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
if obj.get("ok") is not True:
    raise SystemExit("global chat expected ok=true")
if str(obj.get("scope") or "") != "global":
    raise SystemExit(f"global chat expected scope=global got {obj.get('scope')!r}")
reply = obj.get("reply") or {}
hits = reply.get("hits") or []
actions = reply.get("actions") or []
if not isinstance(hits, list) or len(hits) == 0:
    raise SystemExit("global cold-start expected at least one hit")
open_actions = [a for a in actions if isinstance(a, dict) and str(a.get("kind") or "") == "open_session"]
if len(open_actions) == 0:
    raise SystemExit("global cold-start expected at least one open_session action")
cit = (hits[0] or {}).get("citation") if isinstance(hits[0], dict) else None
if not isinstance(cit, dict):
    raise SystemExit("global cold-start first hit missing citation object")
sid = str(cit.get("session_id") or "")
seg = cit.get("segment_id")
t0 = cit.get("t_start")
t1 = cit.get("t_end")
if not sid:
    raise SystemExit("global cold-start citation missing session_id")
if not isinstance(seg, int):
    raise SystemExit("global cold-start citation missing integer segment_id")
if not isinstance(t0, (int, float)) or not isinstance(t1, (int, float)):
    raise SystemExit("global cold-start citation missing numeric timestamps")
print(f"global_chat_hits_ok count={len(hits)}")
print(f"global_chat_open_session_ok count={len(open_actions)}")
print(f"global_chat_citation_ok session_id={sid} segment_id={seg} t_start={t0} t_end={t1}")
PY
echo "PASS: global chat cold-start hits/actions/citations checks complete"

echo "PHASE 9: Root UI surface check"
if ! wait_frontend; then
  if [[ "${AUTOSTART_FRONTEND}" != "1" ]]; then
    echo "FAIL: frontend not reachable at ${FRONTEND_URL} and autostart disabled."
    exit 1
  fi
  echo "Frontend not reachable. Starting Vite frontend..."
  (
    cd /home/notsolikely/Ashby_Engine/webapp/stuart_frontend/stuart_app
    npm run dev -- --host 127.0.0.1 --port 4173
  ) >/tmp/stuart_smoke_frontend.log 2>&1 &
  STARTED_FRONTEND_PID="$!"
  if ! wait_frontend; then
    echo "FAIL: frontend startup failed. See /tmp/stuart_smoke_frontend.log"
    exit 1
  fi
fi
ROOT_HTML="$(curl --noproxy '*' -fsS "${FRONTEND_URL}/")"
printf '%s' "${ROOT_HTML}" >/tmp/d12_root_ui.html
python3 - << 'PY' /tmp/d12_root_ui.html
import sys
from pathlib import Path
html = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
need_any = ["id=\"root\"", "id='root'"]
if not any(x in html for x in need_any):
    raise SystemExit("frontend root check: missing React root mount element")
has_vite_signal = ("/src/main.jsx" in html) or ("<script type=\"module\" crossorigin src=\"/assets/" in html)
if not has_vite_signal:
    raise SystemExit("frontend root check: missing Vite module script signal")
legacy_markers = ["id=\"sessions\"", "Message Stuart...", "Topbar", "/static/app.js"]
for m in legacy_markers:
    if m in html:
        raise SystemExit(f"frontend root check: legacy marker found: {m}")
print("root_ui_surface_ok")
PY
echo "PASS: root UI surface check complete"

echo "PHASE 10: Export bundle checks"
curl --noproxy '*' -fsS "${BASE_URL}/api/sessions/${MEETING_SESSION_ID}/export?export_type=full_bundle&format=zip&transcript_formats=txt,pdf&formalization_formats=md" -o /tmp/d12_export_user_full.zip
curl --noproxy '*' -fsS "${BASE_URL}/api/sessions/${MEETING_SESSION_ID}/export?export_type=transcript_only&format=zip&transcript_formats=md" -o /tmp/d12_export_user_transcript_only.zip
curl --noproxy '*' -fsS "${BASE_URL}/api/sessions/${MEETING_SESSION_ID}/export?export_type=formalization_only&format=zip&formalization_formats=pdf" -o /tmp/d12_export_user_formalization_only.zip
curl --noproxy '*' -fsS "${BASE_URL}/api/sessions/${MEETING_SESSION_ID}/export?export_type=dev_bundle&format=zip" -o /tmp/d12_export_dev_bundle.zip

python3 - << 'PY'
import json
import re
import zipfile
from pathlib import Path

def names(zip_path: str):
    with zipfile.ZipFile(zip_path, "r") as zf:
        return zf.namelist()

def assert_no_abs(zip_path: str):
    with zipfile.ZipFile(zip_path, "r") as zf:
        for n in zf.namelist():
            if n.startswith("/") or ".." in Path(n).parts:
                raise SystemExit(f"{zip_path}: invalid archive path {n!r}")
        for n in zf.namelist():
            if not n.endswith(".json"):
                continue
            txt = zf.read(n).decode("utf-8", errors="ignore")
            if "/home/" in txt or re.search(r"[A-Za-z]:\\\\", txt):
                raise SystemExit(f"{zip_path}: absolute path marker found in {n}")

full_n = names("/tmp/d12_export_user_full.zip")
if not any(n.startswith("transcripts/") and n.endswith("/transcript.txt") for n in full_n):
    raise SystemExit("user full bundle missing transcript.txt")
if not any(n.startswith("transcripts/") and n.endswith("/transcript.pdf") for n in full_n):
    raise SystemExit("user full bundle missing transcript.pdf")
if not any(n.startswith("formalizations/") and n.endswith(".md") for n in full_n):
    raise SystemExit("user full bundle missing formalization .md")
if any(n.startswith("formalizations/") and n.endswith(".pdf") for n in full_n):
    raise SystemExit("user full bundle unexpectedly contains formalization .pdf with md-only filter")

tr_n = names("/tmp/d12_export_user_transcript_only.zip")
if not any(n.startswith("transcripts/") and n.endswith("/transcript.md") for n in tr_n):
    raise SystemExit("transcript-only bundle missing transcript.md")
if any(n.startswith("formalizations/") for n in tr_n):
    raise SystemExit("transcript-only bundle unexpectedly contains formalizations/")

fo_n = names("/tmp/d12_export_user_formalization_only.zip")
if not any(n.startswith("formalizations/") and n.endswith(".pdf") for n in fo_n):
    raise SystemExit("formalization-only bundle missing formalization .pdf")
if any(n.startswith("transcripts/") for n in fo_n):
    raise SystemExit("formalization-only bundle unexpectedly contains transcripts/")

dev_n = names("/tmp/d12_export_dev_bundle.zip")
if not any(n.startswith("dev/transcripts/") and n.endswith("/transcript_version.json") for n in dev_n):
    raise SystemExit("dev bundle missing dev transcript payloads")
if not any(n.startswith("dev/formalizations/") and n.endswith("/run.json") for n in dev_n):
    raise SystemExit("dev bundle missing dev run.json payloads")
if not any(n.startswith("dev/formalizations/") and (n.endswith("/minutes.json") or n.endswith("/journal.json")) for n in dev_n):
    raise SystemExit("dev bundle missing raw formalization json payloads")
if not any(n.startswith("dev/formalizations/") and n.endswith("/events.jsonl") for n in dev_n):
    raise SystemExit("dev bundle missing events.jsonl payloads")

for p in [
    "/tmp/d12_export_user_full.zip",
    "/tmp/d12_export_user_transcript_only.zip",
    "/tmp/d12_export_user_formalization_only.zip",
    "/tmp/d12_export_dev_bundle.zip",
]:
    assert_no_abs(p)

print("export_bundle_checks_ok")
PY
echo "PASS: export bundle checks complete"

ARTIFACTS_LIST="${OUT_DIR}/artifacts_list.txt"
EXPORT_LIST="${OUT_DIR}/export_list.txt"

python3 - << 'PY' "${ARTIFACTS_LIST}" "${OUT_DIR}"
from pathlib import Path
import os
import time

out_path = Path(os.sys.argv[1])
out_dir = Path(os.sys.argv[2])
lines = []
lines.append("# D12 artifacts list")
lines.append(f"generated_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
for p in sorted(Path("/tmp").glob("d12_*")):
    if p.is_file():
        lines.append(f"/tmp/{p.name}\t{p.stat().st_size}")
run_log = out_dir / "run.log"
if run_log.exists():
    lines.append(f"{run_log}\t{run_log.stat().st_size}")
out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote_artifacts_list={out_path}")
PY

python3 - << 'PY' "${EXPORT_LIST}"
import os
import time
import zipfile
from pathlib import Path

out_path = Path(os.sys.argv[1])
exports = [
    Path("/tmp/d12_export_user_full.zip"),
    Path("/tmp/d12_export_user_transcript_only.zip"),
    Path("/tmp/d12_export_user_formalization_only.zip"),
    Path("/tmp/d12_export_dev_bundle.zip"),
]
lines = []
lines.append("# D12 export list")
lines.append(f"generated_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
for zpath in exports:
    if not zpath.exists():
        continue
    lines.append(f"[zip] {zpath} size={zpath.stat().st_size}")
    with zipfile.ZipFile(zpath, "r") as zf:
        for name in sorted(zf.namelist()):
            lines.append(f"  - {name}")
out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote_export_list={out_path}")
PY

echo "STATUS=QUEST_207 phases 1-10 complete"
echo "WROTE ${RUN_LOG}"
echo "WROTE ${ARTIFACTS_LIST}"
echo "WROTE ${EXPORT_LIST}"
