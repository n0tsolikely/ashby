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
    addBubble("assistant", "Got it. (Chat is scaffold-only; uploads run Stuart and return a PDF link.)");
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
      addBubble("assistant", `Uploaded: ${out.filename}`);
      if (out.pdf_url) {
        addBubble("assistant", "PDF ready:");
        addDownloadLink(out.pdf_url);
      } else {
        addBubble("assistant", "Run completed but no PDF URL was returned.");
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
