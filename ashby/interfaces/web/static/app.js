let REGISTRY = null;
let ACTIVE_SESSION = null;
let ATTACHMENTS = []; // {filename,mime_type,size_bytes,sha256}
let REFORMALIZE_RENDERED = new Set();

const el = (id) => document.getElementById(id);

// SIDE-QUEST_079: persistent UX status strip (session/file/run)
function _setStatus(id, text, cls){
  const node = el(id);
  if(!node) return;
  node.textContent = text;
  node.classList.remove('ok','warn','bad');
  if(cls) node.classList.add(cls);
}

function _fmtTs(ts){
  if(!(ts === 0 || ts)) return '';
  try{
    const d = new Date(Number(ts) * 1000);
    return d.toLocaleString();
  }catch(e){
    return '';
  }
}

function _shortId(id){
  if(!id) return '';
  return String(id).slice(0,8);
}

function _sessionLabel(s){
  if(!s) return 'none';
  const mode = (s.mode || 'unknown');
  const title = (s.title || '').trim();
  const ts = _fmtTs(s.created_ts);
  const sid = s.session_id || '';
  if(title){
    return `${title} · ${mode}${ts ? ` · ${ts}` : ''}`;
  }
  return `${mode} · ${_shortId(sid)}${ts ? ` · ${ts}` : ''}`;
}

function _runLabel(state){
  if(!state) return 'idle';
  const status = state.status || 'unknown';
  const stage = state.stage || '';
  const pct = (state.progress === 0 || state.progress) ? `${state.progress}%` : '';
  return `${status}${stage ? ` · ${stage}` : ''}${pct ? ` · ${pct}` : ''}`;
}

function _statusClassForRun(state){
  const st = (state || {}).status || '';
  if(st === 'succeeded') return 'ok';
  if(st === 'failed') return 'bad';
  if(st === 'queued' || st === 'running') return 'warn';
  return null;
}

function addBanner(text){
  const node = document.createElement('div');
  node.className = 'banner';
  node.textContent = text;
  el('chat').appendChild(node);
  el('chat').scrollTop = el('chat').scrollHeight;
  return node;
}

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

function _downloadUrl(runId, name){
  return `/download/${encodeURIComponent(runId)}/${encodeURIComponent(name)}`;
}

function _renderCuratedExtras(runId, arts){
  const names = new Set((arts || []).map(a => a.name));

  const want = [
    ['transcript.txt', 'transcript.txt'],
    ['transcript.json', 'transcript.json'],
    ['aligned_transcript.json', 'aligned_transcript.json'],
    ['diarization.json', 'diarization.json'],
    ['truth_gate_report.json', 'truth_gate_report.json'],
  ];

  const lines = [];
  for(const [label, name] of want){
    if(!names.has(name)) continue;
    const url = _downloadUrl(runId, name);
    lines.push([`${label}:`, `<a href="${url}" target="_blank" rel="noopener">${name}</a>`]);
  }

  if(lines.length){
    addCard('Transcripts & Reports', lines);
    return true;
  }
  return false;
}

function renderPrimaryDownloads(runId, downloads, arts){
  const primary = (downloads || {}).primary || {};
  const lines = [];

  const add = (label, item) => {
    if(!item || !item.url) return;
    lines.push([`${label}:`, `<a href="${item.url}" target="_blank" rel="noopener">${item.name}</a>`]);
  };

  // Deterministic outputs derived from run.json['primary_outputs'] (QUEST_063)
  add('pdf', primary.pdf);
  add('md', primary.md);
  add('json', primary.json);
  add('evidence', primary.evidence_map);

  const hadPrimary = lines.length > 0;
  if(hadPrimary){
    addCard('Primary Outputs', lines);
  }

  // SIDE-QUEST_079: always surface curated transcript artifacts when available.
  _renderCuratedExtras(runId, arts);
  return hadPrimary;
}

function renderArtifactsFallback(runId, arts){
  if(!arts || !arts.length){
    addBubble('assistant', 'Run completed, but no downloads were found.');
    return;
  }
  const lines = arts.map(a => {
    const url = `/download/${runId}/${encodeURIComponent(a.name)}`;
    return ['artifact:', `<a href="${url}" target="_blank" rel="noopener">${a.name}</a> (${a.kind}, ${a.size} bytes)`];
  });
  addCard('All Artifacts', lines);
}


function getFormalizeMode(state){
  try{
    const plan = (state || {}).plan || {};
    const steps = plan.steps || [];
    for(const st of steps){
      if(((st || {}).kind || '').toLowerCase() === 'formalize'){
        const params = (st || {}).params || {};
        return params.mode || null;
      }
    }
  }catch(e){}
  return null;
}

function getFormalizeParams(state){
  // Returns {mode, template, retention} from the plan formalize step.
  try{
    const plan = (state || {}).plan || {};
    const steps = plan.steps || [];
    for(const st of steps){
      if(((st || {}).kind || '').toLowerCase() === 'formalize'){
        const params = (st || {}).params || {};
        return {
          mode: params.mode || null,
          template: params.template_id || params.template || null,
          retention: params.retention || null,
        };
      }
    }
  }catch(e){}
  return {mode:null, template:null, retention:null};
}

async function maybeRenderReformalizeUI(runId, state){
  if(!runId || !state) return;
  if(REFORMALIZE_RENDERED.has(runId)) return;

  // Only offer reformalize controls when the base run has completed successfully.
  if((state.status || '') !== 'succeeded') return;

  const fp = getFormalizeParams(state);
  const mode = (fp.mode || '').toLowerCase();
  if(!mode) return;

  REFORMALIZE_RENDERED.add(runId);

  const templatesByMode = (REGISTRY || {}).templates_by_mode || {};
  const allowedTemplates = templatesByMode[mode] || [];
  const retentions = (REGISTRY || {}).retentions || ['LOW','MED','HIGH','NEAR_VERBATIM'];
  const defaultRetention = (REGISTRY || {}).default_retention || 'MED';

  const card = document.createElement('div');
  card.className = 'card';

  const h = document.createElement('h3');
  h.textContent = 'Re-Formalize';
  card.appendChild(h);

  const info = document.createElement('div');
  info.className = 'kv';
  info.innerHTML = '<span class="k">Change template/retention.</span> <span class="v">Creates a new run and reuses transcripts (no re-upload / no re-transcribe).</span>';
  card.appendChild(info);

  const controls = document.createElement('div');
  controls.className = 'reformalize-controls';

  const templateSel = document.createElement('select');
  templateSel.className = 'reformalize-select';
  (allowedTemplates.length ? allowedTemplates : ['default']).forEach(t => {
    const o = document.createElement('option');
    o.value = t;
    o.textContent = `template: ${t}`;
    templateSel.appendChild(o);
  });

  const curTemplate = (fp.template || 'default').toLowerCase();
  if(curTemplate){
    templateSel.value = curTemplate;
  }

  const retentionSel = document.createElement('select');
  retentionSel.className = 'reformalize-select';
  retentions.forEach(r => {
    const o = document.createElement('option');
    o.value = r;
    o.textContent = `retention: ${r}`;
    retentionSel.appendChild(o);
  });

  const curRet = (fp.retention || defaultRetention || 'MED').toUpperCase();
  if(curRet){
    retentionSel.value = curRet;
  }

  controls.appendChild(templateSel);
  controls.appendChild(retentionSel);
  card.appendChild(controls);

  const btn = document.createElement('button');
  btn.className = 'run-btn';
  btn.textContent = 'Re-Formalize (no re-ingest)';
  btn.onclick = async () => {
    addBubble('assistant', 'Starting re-formalize...');
    const resp = await fetch(`/api/runs/${encodeURIComponent(runId)}/reformalize`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({template_id: templateSel.value, retention: retentionSel.value})
    });
    const out = await resp.json();
    if(!out.ok){
      addBubble('assistant', `Re-formalize failed: ${(out || {}).error || 'unknown'}`);
      return;
    }
    const newId = out.rerun_run_id;
    addBubble('assistant', `Re-formalize started: ${newId}`);
    await pollRun(newId);
  };
  card.appendChild(btn);

  el('chat').appendChild(card);
  el('chat').scrollTop = el('chat').scrollHeight;
}

async function maybeRenderSpeakerMapUI(runId, state){
  const mode = getFormalizeMode(state);
  if(mode !== 'meeting'){
    return;
  }

  let data = null;
  try{
    const r = await fetch(`/api/runs/${encodeURIComponent(runId)}/speakers`);
    data = await r.json();
  }catch(e){
    return;
  }

  if(!data || !data.ok){
    return;
  }
  const speakers = data.speakers || [];
  if(!speakers.length){
    return;
  }

  const card = document.createElement('div');
  card.className = 'card';
  const h = document.createElement('h3');
  h.textContent = 'Speaker Mapping';
  card.appendChild(h);

  const info = document.createElement('div');
  info.className = 'kv';
  info.innerHTML = '<span class="k">Map diarization labels to names.</span> <span class="v">Creates an overlay and rerenders.</span>';
  card.appendChild(info);

  const wrap = document.createElement('div');
  wrap.className = 'speaker-map';

  speakers.forEach(label => {
    const row = document.createElement('div');
    row.className = 'speaker-row';

    const l = document.createElement('span');
    l.className = 'speaker-label';
    l.textContent = label;

    const inp = document.createElement('input');
    inp.className = 'speaker-input';
    inp.type = 'text';
    inp.placeholder = 'Name (e.g., Greg)';
    inp.dataset.speakerLabel = label;

    row.appendChild(l);
    row.appendChild(inp);
    wrap.appendChild(row);
  });

  card.appendChild(wrap);

  const btn = document.createElement('button');
  btn.className = 'run-btn';
  btn.textContent = 'Apply Names & Rerender';
  btn.onclick = async () => {
    const mapping = {};
    card.querySelectorAll('input.speaker-input').forEach(inp => {
      const label = inp.dataset.speakerLabel;
      const name = (inp.value || '').trim();
      if(label && name){
        mapping[label] = name;
      }
    });

    if(Object.keys(mapping).length === 0){
      addBubble('assistant', 'No names entered; nothing to apply.');
      return;
    }

    addBubble('assistant', 'Saving speaker map overlay and rerendering...');

    const resp = await fetch(`/api/runs/${encodeURIComponent(runId)}/speaker_map`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mapping: mapping, rerender: true})
    });
    const out = await resp.json();

    if(!out.ok){
      addBubble('assistant', `Speaker map failed: ${(out || {}).error || 'unknown'}`);
      return;
    }

    if(out.rerender_run_id){
      addBubble('assistant', `Rerender started: ${out.rerender_run_id}`);
      await pollRun(out.rerender_run_id);
    }else{
      addBubble('assistant', 'Speaker map saved.');
    }
  };

  card.appendChild(btn);
  el('chat').appendChild(card);
  el('chat').scrollTop = el('chat').scrollHeight;
}

async function showOutputs(runId){
  if(!runId) return;
  addBubble('assistant', `Loading outputs for ${runId}...`);
  const r = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  const data = await r.json();
  const ok = renderPrimaryDownloads(runId, data.downloads || {}, data.artifacts || []);
  await maybeRenderSpeakerMapUI(runId, data.state || {});
  await maybeRenderReformalizeUI(runId, data.state || {});
  if(!ok){
    renderArtifactsFallback(runId, data.artifacts || []);
  }
}

function addRunStatusCard(runId){
  const card = document.createElement('div');
  card.className = 'card';
  const h = document.createElement('h3');
  h.textContent = 'Run Status';
  card.appendChild(h);

  const mk = (k) => {
    const row = document.createElement('div');
    row.className = 'kv';
    const kk = document.createElement('span');
    kk.className = 'k';
    kk.textContent = k;
    const vv = document.createElement('span');
    vv.className = 'v';
    row.appendChild(kk);
    row.appendChild(vv);
    card.appendChild(row);
    return vv;
  };

  const runIdV = mk('run_id:');
  runIdV.textContent = runId;

  const statusV = mk('status:');
  const stageV = mk('stage:');
  const progressV = mk('progress:');

  el('chat').appendChild(card);
  el('chat').scrollTop = el('chat').scrollHeight;

  return {statusV, stageV, progressV};
}

async function pollRun(runId){
  const ui = addRunStatusCard(runId);

  // Long runs are normal; poll for a while before asking the user to re-check.
  // (This avoids the UI looking "stuck" at ~90%.)
  const MAX_ITERS = 1200; // ~10 minutes at 500ms/1s cadence

  for(let i=0;i<MAX_ITERS;i++){
    const r = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
    const data = await r.json();
    const state = data.state || {};

    const status = state.status || 'unknown';
    const stage = state.stage || '';
    const progress = (state.progress === 0 || state.progress) ? `${state.progress}%` : '';

    ui.statusV.textContent = status;
    ui.stageV.textContent = stage;
    ui.progressV.textContent = progress;

    // Status strip sync
    _setStatus('runLabel', _runLabel(state), _statusClassForRun(state));

    if(status === 'succeeded'){
      addBubble('assistant', 'Run succeeded.');
      const ok = renderPrimaryDownloads(runId, data.downloads || {}, data.artifacts || []);
      await maybeRenderSpeakerMapUI(runId, state);
      await maybeRenderReformalizeUI(runId, state);
      if(!ok){
        renderArtifactsFallback(runId, data.artifacts || []);
      }
      return;
    }

    if(status === 'failed'){
      const errs = Array.isArray(state.errors) ? state.errors : [];
      const last = errs.length ? errs[errs.length - 1] : null;
      const et = (last && last.type) ? String(last.type) : 'Error';
      const em = (last && last.message) ? String(last.message) : 'Run failed (no details).';
      addBanner(`Run failed: ${et}: ${em}`);

      // Surface whatever artifacts are available so the user isn't forced into the filesystem.
      renderPrimaryDownloads(runId, data.downloads || {}, data.artifacts || []);
      renderArtifactsFallback(runId, data.artifacts || []);
      return;
    }

    // cadence: fast early, slower later
    const sleepMs = (i < 60) ? 500 : 1000;
    await new Promise(res => setTimeout(res, sleepMs));
  }

  addBanner(`Run is still in progress: ${runId} · ${_runLabel({status: ui.statusV.textContent, stage: ui.stageV.textContent, progress: (ui.progressV.textContent||'').replace('%','')})}`);
  addBubble('assistant', 'Still running. Use Library/Outputs later to re-check.');
}

async function runNow(){
  const sid = await ensureSession();
  if(!sid){
    addBubble('assistant', 'Choose a mode first to create a session.');
    return;
  }
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
  btn.textContent = 'Confirm & Run';
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

  let activeObj = null;

  (data.sessions || []).forEach(s => {
    const item = document.createElement('div');
    item.className = 'session-item' + (s.session_id === ACTIVE_SESSION ? ' active' : '');
    const label = _sessionLabel(s);
    item.textContent = label;
    item.title = s.session_id || '';
    if(s.session_id === ACTIVE_SESSION){
      activeObj = s;
    }
    item.onclick = () => {
      ACTIVE_SESSION = s.session_id;
      ATTACHMENTS = [];
      localStorage.setItem('stuart_active_session', ACTIVE_SESSION);
      fetchSessions();
      _setStatus('sessionLabel', _sessionLabel(s), 'ok');
      _setStatus('fileLabel', 'none', null);
      _setStatus('runLabel', 'idle', null);
      addBubble('assistant', `Switched to session ${_shortId(ACTIVE_SESSION)}`);
    };
    host.appendChild(item);
  });

  if(activeObj){
    _setStatus('sessionLabel', _sessionLabel(activeObj), 'ok');
  }else{
    _setStatus('sessionLabel', ACTIVE_SESSION ? `unknown · ${_shortId(ACTIVE_SESSION)}` : 'none', ACTIVE_SESSION ? 'warn' : null);
  }
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
  _setStatus('fileLabel', `uploading · ${file.name}`, 'warn');
  addBubble('assistant', `Uploading ${file.name}...`);
  const form = new FormData();
  form.append('file', file);

  const r = await fetch(`/api/upload?session_id=${encodeURIComponent(sid)}`, {
    method:'POST',
    body: form
  });
  const data = await r.json();
  if(!data.ok){
    _setStatus('fileLabel', `upload failed · ${file.name}`, 'bad');
    addBubble('assistant', `Upload failed: ${(data || {}).error || 'unknown'}`);
    return;
  }
  const a = data.attachment;
  ATTACHMENTS = [a]; // v1: single attachment
  _setStatus('fileLabel', `uploaded · ${a.filename}`, 'ok');
  addBubble('assistant', 'Upload complete.');
  addCard('Attachment', [
    ['file:', a.filename],
    ['sha256:', (a.sha256 || '').slice(0,12) + '…'],
    ['size:', a.size_bytes || 'unknown'],
  ]);
}

async function doSearch(q){
  const url = `/api/search?q=${encodeURIComponent(q)}&limit=20`;
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
  renderSearchResultsCard(hits);
}

function renderSearchResultsCard(hits){
  const card = document.createElement('div');
  card.className = 'card';

  const h = document.createElement('h3');
  h.textContent = 'Search Results';
  card.appendChild(h);

  hits.slice(0,20).forEach(hit => {
    const row = document.createElement('div');
    row.className = 'search-row';

    const snippet = document.createElement('div');
    snippet.className = 'search-snippet';
    snippet.textContent = hit.snippet || '';

    const meta = document.createElement('div');
    meta.className = 'search-meta';
    const title = hit.title || hit.session_id;
    const t0 = (hit.t_start === 0 || hit.t_start) ? hit.t_start.toFixed(2) : '';
    const t1 = (hit.t_end === 0 || hit.t_end) ? hit.t_end.toFixed(2) : '';
    meta.textContent = `${title} · ${hit.mode || 'unknown'} · run:${hit.run_id} · seg:${hit.segment_id}` + ((t0||t1) ? ` · t:${t0}-${t1}` : '');

    const actions = document.createElement('div');
    actions.className = 'search-actions';

    const b1 = document.createElement('button');
    b1.className = 'pill primary';
    b1.type = 'button';
    b1.textContent = 'Outputs';
    b1.onclick = () => showOutputs(hit.run_id);
    actions.appendChild(b1);

    const b2 = document.createElement('button');
    b2.className = 'pill';
    b2.type = 'button';
    b2.textContent = 'Open Session';
    b2.onclick = async () => {
      ACTIVE_SESSION = hit.session_id;
      ATTACHMENTS = [];
      localStorage.setItem('stuart_active_session', ACTIVE_SESSION);
      await fetchSessions();
      _setStatus('fileLabel', 'none', null);
      _setStatus('runLabel', 'idle', null);
      addBubble('assistant', `Switched to session ${ACTIVE_SESSION}`);
    };
    actions.appendChild(b2);

    row.appendChild(snippet);
    row.appendChild(meta);
    row.appendChild(actions);
    card.appendChild(row);
  });

  el('chat').appendChild(card);
  el('chat').scrollTop = el('chat').scrollHeight;
}

async function showLibrary(){
  const r = await fetch('/api/library?limit=50');
  const data = await r.json();
  if(!data.ok){
    addBubble('assistant', 'Library failed to load.');
    return;
  }
  const sessions = data.sessions || [];
  if(!sessions.length){
    addBubble('assistant', 'Library is empty.');
    return;
  }

  const card = document.createElement('div');
  card.className = 'card';

  const h = document.createElement('h3');
  h.textContent = 'Library';
  card.appendChild(h);

  sessions.slice(0,50).forEach(s => {
    const row = document.createElement('div');
    row.className = 'lib-row';

    const title = document.createElement('div');
    title.className = 'lib-title';
    title.textContent = _sessionLabel(s);

    const meta = document.createElement('div');
    meta.className = 'lib-meta';
    const st = s.latest_run_status ? `latest:${s.latest_run_status}` : 'no runs yet';
    meta.textContent = s.latest_run_id ? `${st} · run:${s.latest_run_id}` : st;

    const actions = document.createElement('div');
    actions.className = 'lib-actions';

    const b1 = document.createElement('button');
    b1.className = 'pill';
    b1.type = 'button';
    b1.textContent = 'Set Active';
    b1.onclick = async () => {
      ACTIVE_SESSION = s.session_id;
      ATTACHMENTS = [];
      localStorage.setItem('stuart_active_session', ACTIVE_SESSION);
      await fetchSessions();
      _setStatus('fileLabel', 'none', null);
      _setStatus('runLabel', 'idle', null);
      addBubble('assistant', `Switched to session ${ACTIVE_SESSION}`);
    };
    actions.appendChild(b1);

    const b2 = document.createElement('button');
    b2.className = 'pill primary';
    b2.type = 'button';
    b2.textContent = 'Latest Outputs';
    b2.disabled = !s.latest_run_id;
    b2.onclick = () => showOutputs(s.latest_run_id);
    actions.appendChild(b2);

    row.appendChild(title);
    row.appendChild(meta);
    row.appendChild(actions);
    card.appendChild(row);
  });

  el('chat').appendChild(card);
  el('chat').scrollTop = el('chat').scrollHeight;
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

  // status strip defaults
  _setStatus('fileLabel', 'none', null);
  _setStatus('runLabel', 'idle', null);

  await fetchRegistry();
  await fetchSessions();

  el('modeSelect').addEventListener('change', (e) => {
    setMode(e.target.value);
  });

  // library + search UI (QUEST_064)
  el('libraryBtn').addEventListener('click', showLibrary);
  el('searchBtn').addEventListener('click', async () => {
    const q = (el('searchInput').value || '').trim();
    if(q) await doSearch(q);
  });
  el('searchInput').addEventListener('keydown', async (e) => {
    if(e.key === 'Enter'){
      const q = (el('searchInput').value || '').trim();
      if(q) await doSearch(q);
    }
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
