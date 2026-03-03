const SPEAKER_ID_RE = /^SPEAKER_(\d+)$/i;

export function speakerIdToDisplayLabel(speakerId) {
  const raw = String(speakerId || "").trim();
  if (!raw) return "Unknown";

  const m = raw.match(SPEAKER_ID_RE);
  if (!m) return raw;

  const n = Number(m[1]);
  if (!Number.isInteger(n) || n < 0) return raw;
  return `Speaker-${String(n + 1).padStart(2, "0")}`;
}

export function displaySpeakerName(speakerId, speakerMap = {}) {
  const key = String(speakerId || "").trim();
  const mapped = speakerMap?.[key];
  if (typeof mapped === "string" && mapped.trim()) return mapped.trim();
  return speakerIdToDisplayLabel(key);
}
