// webapp/static/js/app.js

function qs(sel) { return document.querySelector(sel); }

function addBubble(kind, text) {
  const chat = qs(".chat");
  const div = document.createElement("div");
  div.className = `bubble ${kind}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function addDownloadLink(url) {
  const chat = qs(".chat");
  const div = document.createElement("div");
  div.className = "bubble assistant";
  const a = document.createElement("a");
  a.href = url;
  a.textContent = "Download PDF";
  a.target = "_blank";
  div.appendChild(a);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch("/upload", { method: "POST", body: form });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Upload failed: ${res.status} ${t}`);
  }
  return await res.json();
}

document.addEventListener("DOMContentLoaded", () => {
  const sendBtn = qs("button.send");
  const prompt = qs("input.prompt");
  const fileInput = qs("input#file-input");
  const attachLabel = qs("label.attach");

  async function sendMessage() {
    const text = (prompt.value || "").trim();
    if (!text) return;
    addBubble("user", text);
    prompt.value = "";
    addBubble("assistant", "Got it. (Chat scaffold; uploads store only and return a plan preview.)");
  }

  sendBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    sendMessage();
  });

  prompt?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage();
    }
  });

  fileInput?.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;

    addBubble("user", `Uploading: ${file.name} ...`);
    try {
      const out = await uploadFile(file);
      const fname = (out.attachment && out.attachment.filename) || out.filename || file.name;
      addBubble("assistant", `Stored upload: ${fname}`);

      if (out.plan_preview && out.plan_preview.ordered_steps) {
        const steps = out.plan_preview.ordered_steps.map(s => s.kind).join(" → ") || 'none';
        addBubble("assistant", `Plan preview: ${steps}`);
        addBubble("assistant", "Upload ≠ process. Confirm-to-run is implemented in the main /api web door.");
      } else {
        addBubble("assistant", "Upload stored. No plan preview payload was returned.");
      }
    } catch (err) {
      addBubble("assistant", `Upload error: ${err.message || err}`);
    } finally {
      fileInput.value = "";
    }
  });

  attachLabel?.addEventListener("click", () => {
    fileInput?.click();
  });
});
