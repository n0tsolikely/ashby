from __future__ import annotations

import json
from pathlib import Path

from ashby.modules.meetings.pipeline.align import align_transcript_time_overlap
from ashby.modules.meetings.schemas.artifacts_v1 import dump_json


def test_alignment_time_overlap_assigns_speaker(tmp_path: Path):
    run_dir = tmp_path / 'runs' / 'run_x'
    art = run_dir / 'artifacts'
    art.mkdir(parents=True, exist_ok=True)

    transcript = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "engine": "stub",
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1000, "speaker": "SPEAKER_00", "text": "hi"},
            {"segment_id": 1, "start_ms": 1000, "end_ms": 2000, "speaker": "SPEAKER_00", "text": "yo"},
        ],
    }
    diar = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "engine": "stub",
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1500, "speaker": "SPEAKER_01", "confidence": 1.0},
            {"segment_id": 1, "start_ms": 1500, "end_ms": 2500, "speaker": "SPEAKER_02", "confidence": 1.0},
        ],
    }

    dump_json(art / 'transcript.json', transcript, write_once=True)
    dump_json(art / 'diarization.json', diar, write_once=True)

    a = align_transcript_time_overlap(run_dir)
    out_path = Path(a['path'])
    payload = json.loads(out_path.read_text(encoding='utf-8'))

    segs = payload['segments']
    assert len(segs) >= 1
    # first chunk should resolve to one of the overlapping diar speakers.
    assert segs[0]['speaker'] in ('SPEAKER_01', 'SPEAKER_02')


def test_alignment_splits_cross_speaker_segment_and_preserves_order(tmp_path: Path):
    run_dir = tmp_path / 'runs' / 'run_x'
    art = run_dir / 'artifacts'
    art.mkdir(parents=True, exist_ok=True)

    transcript = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "engine": "stub",
        "segments": [
            {
                "segment_id": 0,
                "start_ms": 0,
                "end_ms": 4000,
                "speaker": "SPEAKER_00",
                "text": "hello how are you doing today oh im fine thank you how are you",
            },
        ],
    }
    diar = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "engine": "stub",
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 1800, "speaker": "SPEAKER_00", "confidence": 1.0},
            {"segment_id": 1, "start_ms": 1800, "end_ms": 4000, "speaker": "SPEAKER_01", "confidence": 1.0},
        ],
    }
    dump_json(art / 'transcript.json', transcript, write_once=True)
    dump_json(art / 'diarization.json', diar, write_once=True)

    a = align_transcript_time_overlap(run_dir)
    payload = json.loads(Path(a['path']).read_text(encoding='utf-8'))
    segs = payload["segments"]

    assert len(segs) >= 2
    assert segs[0]["speaker"] == "SPEAKER_00"
    assert segs[1]["speaker"] == "SPEAKER_01"
    assert segs[0]["start_ms"] <= segs[1]["start_ms"]
    assert segs[0]["text"]
    assert segs[1]["text"]


def test_alignment_merges_adjacent_same_speaker_chunks(tmp_path: Path):
    run_dir = tmp_path / 'runs' / 'run_x'
    art = run_dir / 'artifacts'
    art.mkdir(parents=True, exist_ok=True)

    transcript = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "engine": "stub",
        "segments": [
            {
                "segment_id": 0,
                "start_ms": 0,
                "end_ms": 1000,
                "speaker": "SPEAKER_00",
                "text": "the weather outside today is",
            },
            {
                "segment_id": 1,
                "start_ms": 1050,
                "end_ms": 2200,
                "speaker": "SPEAKER_00",
                "text": "warm and i think its supposed to rain later on today",
            },
        ],
    }
    diar = {
        "version": 1,
        "session_id": "ses_x",
        "run_id": "run_x",
        "engine": "stub",
        "segments": [
            {"segment_id": 0, "start_ms": 0, "end_ms": 2200, "speaker": "SPEAKER_00", "confidence": 1.0},
        ],
    }
    dump_json(art / 'transcript.json', transcript, write_once=True)
    dump_json(art / 'diarization.json', diar, write_once=True)

    a = align_transcript_time_overlap(run_dir)
    payload = json.loads(Path(a['path']).read_text(encoding='utf-8'))
    segs = payload["segments"]
    assert len(segs) == 1
    assert segs[0]["speaker"] == "SPEAKER_00"
    assert "weather outside today is warm and i think its supposed to rain" in segs[0]["text"]
