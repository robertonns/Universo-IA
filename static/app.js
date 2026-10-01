import * as THREE from './vendor/three.module.js';

// Utilitários de seleção DOM
const $ = (id) => document.getElementById(id);

// Paleta visual semântica para os nós 3D
const colors = {
  tecnologia: '#81e1d0',
  linguagem: '#c2a7ff',
  ciência: '#80baff',
  viagem: '#f3bd7c',
  cotidiano: '#e899b7',
  contexto: '#b5c5d6',
  probabilidade: '#e9eeb0'
};

// Estado da aplicação
let version = 0;
let answerVersion = 0;
let currentText = '';
let currentMode = 'local'; // 'local' ou 'demo'
let timer = null;
let pauseTimer = null;
let paused = matchMedia('(prefers-reduced-motion: reduce)').matches;
let records = [];
let measurement = {};
let displayedGraph = null;
let pendingGraph = null;
let requestAbort = null;

// Mapa de nós e arestas no Three.js
const nodes = new Map();
let edgeObjects = [];

// Configuração da cena Three.js
const stage = $('stage');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 150);
camera.position.set(0, 0, 17);

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  stage.appendChild(renderer.domElement);
} catch (e) {
  $('scene-empty').textContent = 'WebGL indisponível. Ative a aceleração gráfica do navegador; a IA continua usando CPU.';
}

const root = new THREE.Group();
scene.add(root);

let yaw = 0;
let pitch = 0;
let zoom = 17;
let drag = null;
let moved = false;
let lastFrame = 0;
let focus = null;

// Hash determinístico para dispersão espacial dos nós
function hash(s) {
  let n = 2166136261;
  for (const c of s) {
    n = Math.imul(n ^ c.charCodeAt(0), 16777619);
  }
  return n >>> 0;
}

// Coordenadas calculadas para estabilidade espacial
function location(n) {
  const g = Object.keys(colors).indexOf(n.group);
  const a = g * 2.39996;
  const h = hash(n.id);
  return new THREE.Vector3(
    Math.cos(a) * 4.4 + ((h % 997) / 997 - 0.5) * 4.2,
    Math.sin(a) * 2.0 + (((h >>> 8) % 991) / 991 - 0.5) * 2.8,
    (((h >>> 16) % 983) / 983 - 0.5) * 5.0
  );
}

// Renderiza o rótulo da palavra em sprite de alta resolução
function label(text, color, weight) {
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d');
  c.width = 512;
  c.height = 96;
  ctx.font = '500 36px system-ui';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = color;
  ctx.fillText(text, 256, 48, 490);

  const texture = new THREE.CanvasTexture(c);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(material);
  const scale = 0.85 + weight * 0.9;
  sprite.scale.set(3.0 * scale, 0.563 * scale, 1);
  return sprite;
}

// Aplicação suave do grafo recebido do backend
function applyGraph(graphData) {
  displayedGraph = graphData;
  const ids = new Set(graphData.nodes.map(n => n.id));

  // Remove nós que não existem mais
  for (const [id, obj] of nodes) {
    if (!ids.has(id)) {
      root.remove(obj.sprite);
      obj.sprite.material.map.dispose();
      obj.sprite.material.dispose();
      nodes.delete(id);
    }
  }

  // Adiciona ou atualiza nós
  for (const n of graphData.nodes) {
    let obj = nodes.get(n.id);
    if (!obj) {
      const sprite = label(n.id, colors[n.group] || colors.contexto, n.weight);
      root.add(sprite);
      obj = { sprite, target: location(n), data: n };
      sprite.position.copy(obj.target).multiplyScalar(0.6);
      sprite.userData.id = n.id;
      nodes.set(n.id, obj);
    }
    obj.data = n;
    obj.target = location(n);
    const scale = 0.85 + n.weight * 0.9;
    obj.sprite.scale.set(3 * scale, 0.563 * scale, 1);
  }

  // Recria arestas de conexão
  for (const e of edgeObjects) {
    root.remove(e);
    e.geometry.dispose();
    e.material.dispose();
  }
  edgeObjects = [];

  for (const e of graphData.edges) {
    if (!nodes.has(e.source) || !nodes.has(e.target)) continue;
    const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
    const lineMat = new THREE.LineBasicMaterial({
      color: colors[nodes.get(e.source).data.group] || '#95abbf',
      transparent: true,
      opacity: 0.15
    });
    const line = new THREE.Line(geo, lineMat);
    line.userData = e;
    root.add(line);
    edgeObjects.push(line);
  }

  $('nodes').textContent = `${graphData.nodes.length} / ${graphData.edges.length}`;
  $('scene-empty').hidden = graphData.nodes.length > 0;

  $('legend').replaceChildren(...graphData.groups.map(g => {
    const s = document.createElement('span');
    s.textContent = g;
    s.style.setProperty('--color', colors[g]);
    return s;
  }));
}

// Redimensionamento do palco 3D
function resize() {
  if (!renderer) return;
  const w = stage.clientWidth;
  const h = stage.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);

// Loop de animação por frame
function frame(t) {
  requestAnimationFrame(frame);
  if (!renderer || document.hidden || t - lastFrame < 32) return;
  lastFrame = t;

  root.rotation.y += (yaw - root.rotation.y) * 0.08;
  root.rotation.x += (pitch - root.rotation.x) * 0.08;
  camera.position.z += (zoom - camera.position.z) * 0.1;

  if (!paused && !drag) yaw += 0.0006;

  for (const o of nodes.values()) {
    o.sprite.position.lerp(o.target, 0.08);
    o.sprite.material.opacity = (focus && focus !== o.data.id) ? 0.35 : 1.0;
  }

  for (const e of edgeObjects) {
    const a = nodes.get(e.userData.source)?.sprite.position;
    const b = nodes.get(e.userData.target)?.sprite.position;
    if (a && b) {
      const v = e.geometry.attributes.position;
      v.setXYZ(0, a.x, a.y, a.z);
      v.setXYZ(1, b.x, b.y, b.z);
      v.needsUpdate = true;
      e.material.opacity = focus
        ? ((e.userData.source === focus || e.userData.target === focus) ? 0.6 : 0.04)
        : 0.15;
    }
  }

  renderer.render(scene, camera);
}
requestAnimationFrame(frame);

// Controles de interação (Mouse e Touch)
stage.addEventListener('pointerdown', e => {
  drag = { x: e.clientX, y: e.clientY };
  moved = false;
  stage.setPointerCapture(e.pointerId);
});

stage.addEventListener('pointermove', e => {
  if (!drag) return;
  const dx = e.clientX - drag.x;
  const dy = e.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
  yaw += dx * 0.006;
  pitch = Math.max(-1.1, Math.min(1.1, pitch + dy * 0.005));
  drag = { x: e.clientX, y: e.clientY };
});

stage.addEventListener('pointerup', e => {
  drag = null;
  if (moved) return;

  const rect = stage.getBoundingClientRect();
  const mouse = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1
  );
  const ray = new THREE.Raycaster();
  ray.setFromCamera(mouse, camera);

  const found = ray.intersectObjects([...nodes.values()].map(n => n.sprite));
  focus = found[0]?.object.userData.id || null;
  $('inspector').hidden = !focus;

  if (focus) {
    const n = nodes.get(focus).data;
    $('inspector').textContent = `${n.id} · ${n.group} · origem: ${n.origin} · ${
      n.group === 'probabilidade' ? 'probabilidade' : 'peso lexical'
    }: ${n.weight.toFixed(2)}`;
  }
});

stage.addEventListener('wheel', e => {
  e.preventDefault();
  zoom = Math.max(5, Math.min(35, zoom + e.deltaY * 0.013));
}, { passive: false });

stage.addEventListener('keydown', e => {
  if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '-', '='].includes(e.key)) {
    e.preventDefault();
    if (e.key === 'ArrowLeft') yaw -= 0.15;
    if (e.key === 'ArrowRight') yaw += 0.15;
    if (e.key === 'ArrowUp') pitch -= 0.1;
    if (e.key === 'ArrowDown') pitch += 0.1;
    if (['+', '='].includes(e.key)) zoom = Math.max(5, zoom - 1);
    if (e.key === '-') zoom = Math.min(35, zoom + 1);
  }
});

$('reset').onclick = () => {
  yaw = 0;
  pitch = 0;
  zoom = 17;
  focus = null;
  $('inspector').hidden = true;
};

function pauseLabel() {
  $('pause').textContent = paused ? 'Retomar movimento' : 'Pausar movimento';
  $('pause').setAttribute('aria-pressed', String(paused));
}
pauseLabel();

$('pause').onclick = () => {
  paused = !paused;
  pauseLabel();
};

// Alternância de Modo: Modelo Local vs Demonstração
function setMode(newMode) {
  currentMode = newMode;
  if (currentMode === 'local') {
    $('btn-mode-local').classList.add('active');
    $('btn-mode-local').setAttribute('aria-pressed', 'true');
    $('btn-mode-demo').classList.remove('active');
    $('btn-mode-demo').setAttribute('aria-pressed', 'false');
    $('notice').textContent = 'Modo Modelo Local ativo. Inferência realizada diretamente via CPU.';
  } else {
    $('btn-mode-demo').classList.add('active');
    $('btn-mode-demo').setAttribute('aria-pressed', 'true');
    $('btn-mode-local').classList.remove('active');
    $('btn-mode-local').setAttribute('aria-pressed', 'false');
    $('notice').textContent = 'Modo Demonstração ativo. Navegação 3D sem necessidade do modelo em execução.';
  }
  submit();
}

$('btn-mode-local').onclick = () => setMode('local');
$('btn-mode-demo').onclick = () => setMode('demo');

// Lista de palavras gramaticais/funcionais para dividir os candidatos
const functionalTokens = new Set(
  'a ao aos à às o os as um uma uns umas de do da dos das em no nos na nas por para com sem '
  'sobre entre até após antes desde contra perante segundo conforme que se e ou mas porém portanto '
  'porque pois como eu tu ele ela nós vocês voce você me te se lhe lhes meu minha seus suas este esta '
  'isso isto aquilo aqui aí ali lá não sim já ainda também muito mais menos bem mal sempre nunca talvez'.split(' ')
);

// Renderiza a lista com barras percentuais proporcionais
function renderCandidates(target, mass, items, total) {
  target.replaceChildren();
  if (!items.length) {
    target.textContent = currentMode === 'demo'
      ? 'Indisponível no modo demonstração.'
      : 'Nenhuma alternativa legível nesta posição.';
    mass.textContent = '—';
    return;
  }
  const localMass = items.reduce((sum, item) => sum + item.probability, 0);
  mass.textContent = `${((localMass / total) * 100).toFixed(1)}% da lista`;

  for (const item of items) {
    const row = document.createElement('div');
    row.className = 'candidate';
    const percent = (item.probability / total) * 100;
    row.style.setProperty('--width', `${Math.min(100, percent)}%`);

    const token = document.createElement('span');
    token.textContent = item.token;
    const p = document.createElement('span');
    p.textContent = percent.toFixed(1) + '%';

    row.append(token, p);
    target.append(row);
  }
}

// Distribuição e projeção de nós de probabilidade no Three.js
function candidates(items) {
  if (pendingGraph && answerVersion === version) {
    const extra = items.slice(0, 12).map(c => ({
      id: '↳ ' + JSON.stringify(c.token),
      group: 'probabilidade',
      weight: c.probability,
      origin: 'probabilidade medida na resposta'
    }));

    applyGraph({
      ...pendingGraph,
      nodes: [...pendingGraph.nodes, ...extra],
      groups: [...pendingGraph.groups, ...(extra.length ? ['probabilidade'] : [])]
    });
  }

  if (!items.length) {
    renderCandidates($('candidates-direct'), $('mass-direct'), [], 1);
    renderCandidates($('candidates-indirect'), $('mass-indirect'), [], 1);
    return;
  }

  const direct = items.filter(item => functionalTokens.has(item.token.toLowerCase())).slice(0, 10);
  const indirect = items.filter(item => !functionalTokens.has(item.token.toLowerCase())).slice(0, 10);
  const shown = [...direct, ...indirect];
  const total = shown.reduce((sum, item) => sum + item.probability, 0) || 1;

  renderCandidates($('candidates-direct'), $('mass-direct'), direct, total);
  renderCandidates($('candidates-indirect'), $('mass-indirect'), indirect, total);
}

// Requisições HTTP e SSE Streaming
async function post(path, body, signal) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal
  });
  if (!response.ok) throw new Error(`Erro local ${response.status}`);
  return response.json();
}

async function streamPost(path, body, signal, onEvent) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal
  });

  if (!response.ok) throw new Error(`Erro local ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const next = await reader.read();
    if (next.done) break;
    buffer += decoder.decode(next.value, { stream: true });
    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const packet = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const name = packet.match(/^event: (.+)$/m)?.[1];
      const raw = packet.match(/^data: (.+)$/m)?.[1];
      if (name && raw) {
        onEvent(name, JSON.parse(raw));
      }
    }
  }
}

// Submissão do texto digitado
async function submit(text = $('prompt').value) {
  version++;
  const requestVersion = version;
  currentText = text;
  $('input-status').textContent = 'Atualização automática · espaço + 250 ms';

  if (!text.trim()) {
    applyGraph({ nodes: [], edges: [], groups: [] });
    $('answer').textContent = 'Sua resposta aparecerá aqui e será reformulada enquanto você escreve.';
    candidates([]);
    return;
  }

  $('generation-state').textContent = 'Atualizando mapa…';
  $('answer-version').textContent = `v${requestVersion} · preparando`;

  // 1. Atualização lexical rápida do mapa 3D
  try {
    const initial = await post('/api/graph', { text });
    if (requestVersion !== version) return;
    pendingGraph = initial.graph;
    applyGraph(initial.graph);
    $('words').textContent = initial.words;
    $('graph-version').textContent = '';
  } catch (error) {
    if (requestVersion === version) {
      $('notice').textContent = 'Não foi possível atualizar o mapa local.';
      return;
    }
  }

  // 2. Cancelamento da inferência anterior e início do novo streaming
  if (requestAbort) requestAbort.abort();
  requestAbort = new AbortController();
  answerVersion = requestVersion;
  measurement = {
    version: requestVersion,
    mode: currentMode,
    started_at: new Date().toISOString()
  };

  $('answer').textContent = '';
  $('generation-state').textContent = currentMode === 'demo' ? 'Demonstração em andamento…' : 'Processando na CPU…';
  if (currentMode === 'local') {
    $('notice').textContent = 'Inferência com modelo Qwen quantizado em CPU · Totalmente local.';
  }
  candidates([]);
  $('tokens').textContent = '—';
  $('speed').textContent = '—';

  try {
    await streamPost(
      '/api/generate',
      { text, mode: currentMode },
      requestAbort.signal,
      (name, result) => {
        if (requestVersion !== version) return;

        if (name === 'chunk') {
          $('answer').textContent += result.text || '';
          $('generation-state').textContent = currentMode === 'demo' ? 'Exibindo demonstração…' : 'Gerando resposta…';
          candidates(result.candidates || []);
          return;
        }

        if (name === 'error') {
          throw new Error(result.message);
        }

        if (name === 'done') {
          $('answer').textContent = result.answer || $('answer').textContent;
          $('answer-version').textContent = `v${requestVersion} · atual`;
          $('generation-state').textContent = 'Prévia concluída · continue escrevendo';
          if (result.text_tokens != null) $('tokens').textContent = result.text_tokens;
          $('speed').textContent = result.words_s != null ? `${result.words_s} palavras/s` : '—';
          candidates(result.candidates || []);
          applyGraph(result.graph);
          $('graph-version').textContent = '';
          records.push({ ...measurement, ...result });
          records = records.slice(-100);
        }
      }
    );
  } catch (error) {
    if (error.name === 'AbortError' || requestVersion !== version) return;
    $('notice').textContent = error.message || 'Modelo não disponível';
    $('generation-state').textContent = 'Aguardando modelo';
    $('answer').textContent = currentMode === 'local'
      ? 'Modelo local não detectado. Você pode alternar para o Modo Demonstração no cabeçalho ou iniciar o INICIAR_APP.bat.'
      : 'Ocorreu um erro na demonstração.';
  }
}

// Ouvintes de entrada no campo de texto
$('prompt').addEventListener('input', e => {
  $('chars').textContent = `${e.target.value.length} / 4000`;
  clearTimeout(pauseTimer);
  if (e.isComposing) return;

  if (/\s/.test(e.data || '') || e.inputType === 'insertFromPaste' || e.inputType?.startsWith('delete')) {
    clearTimeout(timer);
    const snapshot = e.target.value;
    timer = setTimeout(() => submit(snapshot), 250);
  }

  pauseTimer = setTimeout(() => {
    if (e.target.value !== currentText) {
      clearTimeout(timer);
      submit();
    }
  }, 850);
});

$('prompt').addEventListener('compositionend', () => {
  clearTimeout(timer);
  timer = setTimeout(() => submit(), 250);
});

// Exemplos rápidos
for (const b of document.querySelectorAll('[data-example]')) {
  b.onclick = () => {
    $('prompt').value = b.dataset.example;
    $('chars').textContent = `${$('prompt').value.length} / 4000`;
    clearTimeout(timer);
    clearTimeout(pauseTimer);
    submit();
    $('prompt').focus();
  };
}

// Exportação de medições JSON
$('export').onclick = () => {
  const blob = new Blob(
    [JSON.stringify({ prototype: '0.1', records }, null, 2)],
    { type: 'application/json' }
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'universo-medicoes.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

// Polling de saúde do modelo local
async function health() {
  try {
    const data = await (await fetch('/api/status')).json();
    if (data.ready) {
      $('connection').textContent = 'Modelo CPU conectado';
      $('connection').style.color = '#81e1d0';
    } else {
      $('connection').textContent = currentMode === 'demo' ? 'Modo Demonstração' : 'Modelo desconectado';
      $('connection').style.color = '#8f9eaf';
    }
  } catch {
    $('connection').textContent = currentMode === 'demo' ? 'Modo Demonstração' : 'Aplicação offline';
  }
}
health();
setInterval(health, 15000);

// Disparo inicial se houver texto prévio
setTimeout(() => {
  if ($('prompt').value && $('prompt').value !== currentText) submit();
}, 350);
