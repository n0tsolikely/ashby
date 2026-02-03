from ashby.interfaces.telegram.stuart_door_core import (
    STUART_CB_PREFIX,
    start_from_upload,
    apply_mode,
    apply_speakers,
    parse_callback_data,
)


def test_start_from_upload_prompts_mode():
    st, prompt = start_from_upload(local_path="/tmp/x.wav", source_kind="audio")
    assert st.stage == "awaiting_mode"
    assert "pick mode" in prompt.text.lower()
    assert any(b.data.startswith(STUART_CB_PREFIX + "mode:") for b in prompt.buttons)


def test_mode_then_speakers_then_ready():
    st, _ = start_from_upload(local_path="/tmp/x.wav", source_kind="audio")
    st, prompt = apply_mode(st, "meeting")
    assert st.stage == "awaiting_speakers"
    assert st.mode == "meeting"
    assert any(b.data.startswith(STUART_CB_PREFIX + "spk:") for b in prompt.buttons)

    st = apply_speakers(st, "2")
    assert st.stage == "ready"
    assert st.speakers == "2"


def test_parse_callback_data():
    assert parse_callback_data("nope") is None
    assert parse_callback_data(STUART_CB_PREFIX + "mode:meeting") == ("mode", "meeting")
    assert parse_callback_data(STUART_CB_PREFIX + "spk:3+") == ("spk", "3+")
