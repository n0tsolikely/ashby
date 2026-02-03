let REGISTRY = null;
let ACTIVE_SESSION = null;
let ATTACHMENTS = []; // {filename,mime_type,size_bytes,sha256}

const el = (id) => document.getElementById(id);

function addBubble(kind, text){
  const node = document.createElement('div');
  node.className = `msg ${kind}`;
  node.textContent = text;
  el('chat').appendChild(node);
  el('chat').scrollTop = el('chat').scrollHeight;
}

function addCard(title, lines){
  const card = document.createElement('div');
  card.className = 'card';
  const h = document.createElement('h3');
  h.textContent = title;
  card.appendChild(h);

  for(const [k,v] of lines){
    const row = document.createElement('div');
    row.className = 'kv';
    row.innerHTML = `<span class="k">${k}</span>${v}`;
    card.appendChild(row);
  }

  el('chat').appendChild(card);
  el('chat').scrollTop = el('chat').scrollHeight;
  return card;
}

function renderClarify(clarify){
  addCard('Clarify', [['Message:', clarify.message]]);
  const optsWrap = document.createElement('div');
  optsWrap.className = 'options';

  const fields = clarify.fields_needed || [];
  if(fields.includes('mode')){
    (clarify.options.mode || []).forEach((opt) => {
      const b = document.createElement('button');
      b.className = 'pill primary';
      b.textContent = opt.value;
      b.onclick = () => setMode(opt.value);
      optsWrap.appendChild(b);
    });
  }

  el('chat').appendChild(optsWrap);
  el('chat').scrollTop = el('chat').scrollHeight;
}

function renderArtifacts(runId, arts){
  if(!arts || !arts.length){
    addBubble('assistant', 'Run completed, but no downloads were found.');
    return;
  }
  const lines = arts.map(a => {
    const url = `/download/${runId}/${encodeURIComponent(a.name)}`;
    return ['download:', `<a href="${url}" target="_blank" rel="noopener">${a.name}</a> (${a.kind}, ${a.size} bytes)`];
  });
  addCard('Downloads', lines);
}

async function pollRun(runId){
  for(let i=0;i<120;i++){
    const r = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
    const data = await r.json();
    const st = (data.state || {}).status;
    if(st === 'succeeded'){
      addBubble('assistant', 'Run succeeded.');
      renderArtifacts(runId, data.artifacts || []);
      return;
    }
    if(st === 'failed'){
      addBubble('assistant', 'Run failed.');
      return;
    }
    // still pending/running
    await new Promise(res => setTimeout(res, 500));
  }
  addBubble('assistant', 'Run is taking a while; check status again.');
}

async function runNow(){
  const sid = await ensureSession();
  const ui = {
    mode: el('modeSelect').value || null,
    template: el('templateSelect').value || 'default',
    speakers: null,
  };

  addBubble('assistant', 'Starting run...');
  const r = await fetch('/api/run', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sid, ui: ui})
  });
  const data = await r.json();
  if(!data.ok){
    addBubble('assistant', `Run failed to start: ${(data || {}).error || 'unknown'}`);
    return;
  }
  const runId = data.run_id;
  addBubble('assistant', `Run started: ${runId}`);
  await pollRun(runId);
}

function renderPreview(preview){
  // UI state sync: reflect resolved defaults/overrides
  if(preview.mode){
    el('modeSelect').value = preview.mode;
    setMode(preview.mode);
  }
  if(preview.template){
    el('templateSelect').disabled = false;
    el('templateSelect').value = preview.template;
  }

  const card = addCard('Plan Preview', [
    ['mode:', preview.mode],
    ['template:', preview.template],
    ['speakers:', preview.speakers],
    ['defaults:', (preview.defaults_used || []).join(', ') || 'none'],
    ['steps:', (preview.ordered_steps || []).map(s => s.kind).join(' → ') || 'none'],
  ]);

  const btn = document.createElement('button');
  btn.className = 'run-btn';
  btn.textContent = 'Run';
  btn.onclick = runNow;
  card.appendChild(btn);
}

async function fetchRegistry(){
  const r = await fetch('/api/registry');
  REGISTRY = await r.json();

  const modeSel = el('modeSelect');
  REGISTRY.modes.forEach(m => {
    const o = document.createElement('option');
    o.value = m;
    o.textContent = m;
    modeSel.appendChild(o);
  });
}

function setMode(mode){
  el('modeSelect').value = mode;
  const templSel = el('templateSelect');
  templSel.innerHTML = '<option value="" selected disabled>Template</option>';
  templSel.disabled = false;

  const allowed = (REGISTRY.templates_by_mode || {})[mode] || [];
  allowed.forEach(t => {
    const o = document.createElement('option');
    o.value = t;
    o.textContent = t;
    templSel.appendChild(o);
  });

  if(allowed.includes('default')){
    templSel.value = 'default';
  }
}

async function fetchSessions(){
  const r = await fetch('/api/sessions');
  const data = await r.json();
  const host = el('sessions');
  host.innerHTML = '';

  (data.sessions || []).forEach(s => {
    const item = document.createElement('div');
    item.className = 'session-item' + (s.session_id === ACTIVE_SESSION ? ' active' : '');
    const title = s.title || s.session_id;
    item.textContent = `${title} (${s.mode || 'unknown'})`;
    item.onclick = () => {
      ACTIVE_SESSION = s.session_id;
      ATTACHMENTS = [];
      localStorage.setItem('stuart_active_session', ACTIVE_SESSION);
      fetchSessions();
      addBubble('assistant', `Switched to session ${ACTIVE_SESSION}`);
    };
    host.appendChild(item);
  });
}

async function ensureSession(){
  if(ACTIVE_SESSION) return ACTIVE_SESSION;
  const mode = el('modeSelect').value;
  if(!mode) return null;

  const res = await fetch('/api/sessions', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({mode: mode, title: null})
  });
  const data = await res.json();
  ACTIVE_SESSION = data.session_id;
  localStorage.setItem('stuart_active_session', ACTIVE_SESSION);
  await fetchSessions();
  return ACTIVE_SESSION;
}

async function uploadSelectedFile(file){
  const sid = await ensureSession();
  if(!sid){
    addBubble('assistant', 'Choose a mode first to create a session.');
    return;
  }
  addBubble('assistant', `Uploading ${file.name}...`);
  const form = new FormData();
  form.append('file', file);

  const r = await fetch(`/api/upload?session_id=${encodeURIComponent(sid)}`, {
    method:'POST',
    body: form
  });
  const data = await r.json();
  if(!data.ok){
    addBubble('assistant', `Upload failed: ${(data || {}).error || 'unknown'}`);
    return;
  }
  const a = data.attachment;
  ATTACHMENTS = [a]; // v1: single attachment
  addCard('Attachment', [
    ['file:', a.filename],
    ['sha256:', (a.sha256 || '').slice(0,12) + '…'],
    ['size:', a.size_bytes || 'unknown'],
  ]);
}

async function doSearch(q){
  const sid = await ensureSession();
  const url = `/api/search?q=${encodeURIComponent(q)}&session_id=${encodeURIComponent(sid)}`;
  const r = await fetch(url);
  const data = await r.json();
  if(!data.ok){
    addBubble('assistant', 'Search failed.');
    return;
  }
  const hits = data.hits || [];
  if(!hits.length){
    addBubble('assistant', 'No hits.');
    return;
  }
  const lines = hits.slice(0,10).map(h => {
    const cite = `run:${h.run_id} seg:${h.segment_id} t:${h.t_start || ''}-${h.t_end || ''}`;
    return ['hit:', `${h.snippet} <span class="muted">(${cite})</span>`];
  });
  addCard('Search Results', lines);
}

async function sendMessage(){
  const text = el('msgInput').value.trim();
  if(!text && !ATTACHMENTS.length) return;

  if(text){
    addBubble('user', text);
    el('msgInput').value = '';
  }

  if(text.startsWith('/search ')){
    const q = text.slice(8).trim();
    if(q) await doSearch(q);
    return;
  }

  const sid = await ensureSession();
  const ui = {
    mode: el('modeSelect').value || null,
    template: el('templateSelect').value || null,
    speakers: null,
  };

  const r = await fetch('/api/message', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sid, text: text, ui: ui, attachments: ATTACHMENTS})
  });
  const data = await r.json();
  const result = (data || {}).result || {};

  if(result.needs_clarification){
    renderClarify(result.clarify);
  } else {
    renderPreview(result.preview);
  }
}

window.addEventListener('load', async () => {
  ACTIVE_SESSION = localStorage.getItem('stuart_active_session') || null;

  await fetchRegistry();
  await fetchSessions();

  el('modeSelect').addEventListener('change', (e) => {
    setMode(e.target.value);
  });

  // attach wiring
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'audio/*,video/*';
  fileInput.style.display = 'none';
  fileInput.onchange = async () => {
    if(fileInput.files && fileInput.files[0]){
      await uploadSelectedFile(fileInput.files[0]);
    }
    fileInput.value = '';
  };
  document.body.appendChild(fileInput);

  el('attachBtn').addEventListener('click', () => fileInput.click());

  el('sendBtn').addEventListener('click', sendMessage);
  el('msgInput').addEventListener('keydown', (e) => {
    if(e.key === 'Enter') sendMessage();
  });

  addBubble('assistant', 'Select a mode, attach a file, then message. Use /search <query> to search.');
});
