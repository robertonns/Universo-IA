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
  probabilidade: '#e9eeb0',
  conectivos: '#94a3b8'
};

// Armazenamento local seguro e tolerante a falhas
const STORAGE_KEYS = {
  MODE: 'universo_mode',
  BALANCE: 'universo_balance',
  BALANCE_SLIDER: 'universo_balance_slider',
  BALANCE_PROMPT: 'universo_prompt_tokens',
  BALANCE_REPLY: 'universo_reply_tokens',
  TRACE: 'universo_trace',
  CONNECTIVES: 'universo_connectives',
  PAUSED: 'universo_paused'
};

const storage = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem(key);
      return v !== null ? v : fallback;
    } catch (_) {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, String(value));
    } catch (_) {}
  }
};

// Presets da Balança de Tokens
const BALANCE_PRESETS = {
  detailed: {
    id: 'detailed',
    label: '📝 Pergunta Detalhada',
    maxPromptTokens: 1500,
    maxChars: 6000,
    maxTokens: 60,
    sliderValue: 7,
    tokenCapacityDesc: 'Prévia · até 60 tokens'
  },
  balanced: {
    id: 'balanced',
    label: '⚖️ Equilibrado',
    maxPromptTokens: 900,
    maxChars: 3600,
    maxTokens: 140,
    sliderValue: 50,
    tokenCapacityDesc: 'Prévia · até 140 tokens'
  },
  expanded: {
    id: 'expanded',
    label: '💡 Resposta Expandida',
    maxPromptTokens: 400,
    maxChars: 1600,
    maxTokens: 260,
    sliderValue: 86,
    tokenCapacityDesc: 'Prévia · até 260 tokens'
  }
};

// Cor dourada e constante para Linha da Resposta (sinapse ativa)
const TRACE_GOLD = new THREE.Color('#ffc83b');

// Estado da aplicação com persistência
let version = 0;
let answerVersion = 0;
let currentText = '';

let currentMode = storage.get(STORAGE_KEYS.MODE, 'local');
if (currentMode !== 'local' && currentMode !== 'demo') currentMode = 'local';

let currentPreset = storage.get(STORAGE_KEYS.BALANCE, 'balanced');
if (!BALANCE_PRESETS[currentPreset]) currentPreset = 'balanced';

const initialPreset = BALANCE_PRESETS[currentPreset] || BALANCE_PRESETS.balanced;
let currentPromptTokens = parseInt(storage.get(STORAGE_KEYS.BALANCE_PROMPT, String(initialPreset.maxPromptTokens)), 10) || initialPreset.maxPromptTokens;
let currentReplyTokens = parseInt(storage.get(STORAGE_KEYS.BALANCE_REPLY, String(initialPreset.maxTokens)), 10) || initialPreset.maxTokens;
let currentSliderVal = parseInt(storage.get(STORAGE_KEYS.BALANCE_SLIDER, String(initialPreset.sliderValue)), 10) || initialPreset.sliderValue;

let traceActive = false;
let connectivesVisible = false;
let activeDimension = null;
storage.set(STORAGE_KEYS.TRACE, false);
storage.set(STORAGE_KEYS.CONNECTIVES, false);

const savedPaused = storage.get(STORAGE_KEYS.PAUSED);
let paused = savedPaused !== null
  ? savedPaused === 'true'
  : (window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false);

let inputTimer = null;
let pauseTimer = null;
let records = [];
let measurement = {};
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

let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: 'high-performance'
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  stage.appendChild(renderer.domElement);
} catch (e) {
  const emptyElem = $('scene-empty');
  if (emptyElem) {
    emptyElem.textContent = 'WebGL indisponível. Ative a aceleração gráfica do navegador; a IA continua usando CPU.';
  }
}

const root = new THREE.Group();
scene.add(root);

let yaw = 0;
let pitch = 0;
let zoom = 17;
let drag = null;
let moved = false;
let focus = null;

// Hash determinístico para dispersão espacial e cores determinísticas
function hash(s) {
  let n = 2166136261;
  const str = String(s);
  for (let i = 0; i < str.length; i++) {
    n = Math.imul(n ^ str.charCodeAt(i), 16777619);
  }
  return n >>> 0;
}

// Retorna a cor do grupo semântico ou gera cor HSL determinística estável para novos grupos
function getGroupColor(group) {
  if (!group) return colors.contexto;
  if (colors[group]) return colors[group];
  const h = hash(group);
  const hue = h % 360;
  const sat = 65 + (h % 20); // 65% a 85%
  const light = 68 + ((h >>> 8) % 15); // 68% a 83% para alto contraste no tema escuro
  const dynamicColor = `hsl(${hue}, ${sat}%, ${light}%)`;
  colors[group] = dynamicColor;
  return dynamicColor;
}

// Coordenadas tridimensionais calculadas para estabilidade espacial
function getNodePosition(n) {
  getGroupColor(n.group); // garante registro na paleta colors
  const keys = Object.keys(colors);
  const g = keys.indexOf(n.group);
  const a = (g >= 0 ? g : 5) * 2.39996;
  const h = hash(n.id);
  return new THREE.Vector3(
    Math.cos(a) * 4.4 + ((h % 997) / 997 - 0.5) * 4.2,
    Math.sin(a) * 2.0 + (((h >>> 8) % 991) / 991 - 0.5) * 2.8,
    (((h >>> 16) % 983) / 983 - 0.5) * 5.0
  );
}

// Renderiza o rótulo da palavra em sprite de alta nitidez
function createLabelSprite(text, color, weight, isSubtle = false) {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 96;
  const ctx = c.getContext('2d');
  ctx.font = '500 36px system-ui, -apple-system, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = color;
  ctx.fillText(text, 256, 48, 490);

  const texture = new THREE.CanvasTexture(c);
  texture.minFilter = THREE.LinearFilter;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false
  });
  const sprite = new THREE.Sprite(material);
  let scale = 0.85 + (weight || 0.5) * 0.9;
  if (isSubtle) {
    scale *= 0.65; // Redução de ~35% para conectivos estruturais
  }
  sprite.scale.set(3.0 * scale, 0.563 * scale, 1);
  return { sprite, scale };
}

// Aplicação suave e performática do grafo Three.js (gerenciamento de memória e 60 FPS)
function applyGraph(graphData) {
  if (!graphData || !Array.isArray(graphData.nodes)) {
    graphData = { nodes: [], edges: [], groups: [] };
  }

  const ids = new Set(graphData.nodes.map(n => n.id));

  // 1. Liberação de nós obsoletos e descarte de recursos de GPU
  for (const [id, obj] of nodes) {
    if (!ids.has(id)) {
      root.remove(obj.sprite);
      if (obj.sprite.material) {
        if (obj.sprite.material.map) {
          obj.sprite.material.map.dispose();
        }
        obj.sprite.material.dispose();
      }
      nodes.delete(id);
    }
  }

  // 2. Adição ou atualização de nós
  for (const n of graphData.nodes) {
    let obj = nodes.get(n.id);
    const nodeColor = getGroupColor(n.group);
    const targetPos = getNodePosition(n);
    const isSubtle = n.group === 'conectivos';

    if (!obj) {
      const { sprite, scale } = createLabelSprite(n.id, nodeColor, n.weight, isSubtle);
      root.add(sprite);
      obj = { sprite, target: targetPos, data: n, baseScale: scale };
      sprite.position.copy(targetPos).multiplyScalar(0.6);
      sprite.userData.id = n.id;
      nodes.set(n.id, obj);
    } else {
      obj.data = n;
      obj.target.copy(targetPos);
      let scale = 0.85 + (n.weight || 0.5) * 0.9;
      if (isSubtle) {
        scale *= 0.65;
      }
      obj.baseScale = scale;
      obj.sprite.scale.set(3.0 * scale, 0.563 * scale, 1);
    }
  }

  // 3. Descarte completo das arestas e geometrias anteriores
  for (let i = 0; i < edgeObjects.length; i++) {
    const e = edgeObjects[i];
    root.remove(e);
    if (e.geometry) e.geometry.dispose();
    if (e.material) e.material.dispose();
  }
  edgeObjects = [];

  // 4. Criação de arestas normais e arestas-ponte (para ligação direta quando conectivos estiverem ocultos)
  const allEdges = [...(graphData.edges || [])];
  const incomingContentToConn = new Map();
  const outgoingConnToContent = new Map();

  for (const e of allEdges) {
    const isSeq = e.kind_id === 'reply_sequence' || e.kind_id === 'prompt_sequence' || (e.kind && e.kind.includes('sequência'));
    if (isSeq) {
      const sNode = nodes.get(e.source);
      const tNode = nodes.get(e.target);
      if (!sNode || !tNode) continue;
      const sConn = sNode.data.group === 'conectivos';
      const tConn = tNode.data.group === 'conectivos';
      if (!sConn && tConn) {
        if (!incomingContentToConn.has(e.target)) incomingContentToConn.set(e.target, []);
        incomingContentToConn.get(e.target).push(e.source);
      } else if (sConn && !tConn) {
        if (!outgoingConnToContent.has(e.source)) outgoingConnToContent.set(e.source, []);
        outgoingConnToContent.get(e.source).push(e.target);
      }
    }
  }

  // Gera pontes para cada cadeia Conteúdo -> Conectivo -> Conteúdo
  for (const [connId, sources] of incomingContentToConn.entries()) {
    const targets = outgoingConnToContent.get(connId) || [];
    for (const s of sources) {
      for (const t of targets) {
        if (s !== t) {
          allEdges.push({
            source: s,
            target: t,
            weight: 0.75,
            kind: 'ponte sequencial',
            kind_id: 'bridge_sequence',
            isBridgeEdge: true
          });
        }
      }
    }
  }

  // Criação dos objetos Three.js para todas as arestas
  for (const e of allEdges) {
    const sourceNode = nodes.get(e.source);
    const targetNode = nodes.get(e.target);
    if (!sourceNode || !targetNode) continue;

    const geo = new THREE.BufferGeometry().setFromPoints([
      sourceNode.sprite.position.clone(),
      targetNode.sprite.position.clone()
    ]);
    const lineColorStr = getGroupColor(sourceNode.data.group);
    const baseColor = new THREE.Color(lineColorStr);
    const isSequenceReply = (e.kind_id === 'reply_sequence' || e.kind === 'sequência na resposta');
    const isConnEdge = (sourceNode.data.group === 'conectivos' || targetNode.data.group === 'conectivos');
    const isBridge = !!e.isBridgeEdge;

    const lineMat = new THREE.LineBasicMaterial({
      color: (traceActive && isSequenceReply) ? TRACE_GOLD.clone() : baseColor.clone(),
      transparent: true,
      opacity: (traceActive && isSequenceReply) ? 0.70 : 0.15,
      depthWrite: false
    });
    const line = new THREE.Line(geo, lineMat);
    line.userData = {
      source: e.source,
      target: e.target,
      sourceNode,
      targetNode,
      kind: e.kind || '',
      kind_id: e.kind_id || '',
      baseColor: baseColor,
      isConnectiveEdge: isConnEdge,
      isBridgeEdge: isBridge
    };

    if (!connectivesVisible) {
      if (isConnEdge) line.visible = false;
      if (isBridge) line.visible = true;
    } else {
      if (isBridge) line.visible = false;
    }

    root.add(line);
    edgeObjects.push(line);
  }

  // 5. Atualização de indicadores da UI
  const nodesCount = graphData.nodes.length;
  const edgesCount = edgeObjects.length;
  $('nodes').textContent = `${nodesCount} / ${edgesCount}`;
  $('scene-empty').hidden = nodesCount > 0;

  // 6. Legenda interativa com foco de dimensão por clique
  const groups = Array.isArray(graphData.groups) ? graphData.groups : [];
  $('legend').replaceChildren(...groups.map(g => {
    const s = document.createElement('span');
    s.textContent = g;
    s.style.setProperty('--color', getGroupColor(g));
    s.classList.toggle('active', activeDimension === g);
    s.title = `Clique para isolar a dimensão "${g}"`;
    s.onclick = () => {
      if (activeDimension === g) {
        activeDimension = null;
      } else {
        activeDimension = g;
        // Se clicar na dimensão conectivos e eles estiverem ocultos, reativa-os
        if (g === 'conectivos' && !connectivesVisible) {
          connectivesVisible = true;
          storage.set(STORAGE_KEYS.CONNECTIVES, true);
          updateConnectivesButton();
        }
      }
      for (const chip of $('legend').children) {
        chip.classList.toggle('active', chip.textContent === activeDimension);
      }
    };
    return s;
  }));
}

// Redimensionamento do palco 3D
function resize() {
  if (!renderer) return;
  const w = stage.clientWidth;
  const h = stage.clientHeight;
  if (w === 0 || h === 0) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

new ResizeObserver(resize).observe(stage);
window.addEventListener('resize', resize);
resize();

// Loop de animação contínuo a 60 FPS com lerp suave e efeito sinapse neural
function frame(time = 0) {
  requestAnimationFrame(frame);
  if (!renderer || document.hidden) return;

  // Interpolação suave de rotação orbital e câmera
  root.rotation.y += (yaw - root.rotation.y) * 0.08;
  root.rotation.x += (pitch - root.rotation.x) * 0.08;
  camera.position.z += (zoom - camera.position.z) * 0.1;

  if (!paused && !drag) {
    yaw += 0.0006;
  }

  // Atualização suave das posições e opacidades dos nós
  for (const o of nodes.values()) {
    if (o.data.group === 'conectivos' && !connectivesVisible) {
      o.sprite.visible = false;
      continue;
    }
    o.sprite.visible = true;
    o.sprite.position.lerp(o.target, 0.08);

    let targetOpacity = 1.0;
    if (activeDimension) {
      // Foco isolado na dimensão selecionada na legenda
      targetOpacity = (o.data.group === activeDimension) ? 1.0 : 0.08;
    } else if (focus) {
      targetOpacity = (focus === o.data.id) ? 1.0 : 0.35;
    } else if (traceActive) {
      if (o.data.origin === 'resposta') {
        targetOpacity = 1.0;
      } else if (o.data.origin === 'vocabulário demonstrativo') {
        targetOpacity = 0.30;
      } else {
        targetOpacity = 0.90;
      }
    } else {
      targetOpacity = 1.0;
    }

    o.sprite.material.opacity += (targetOpacity - o.sprite.material.opacity) * 0.15;
  }

  // Atualização direta das arestas sem alocações em tempo real
  const pulseOpacity = 0.70 + 0.30 * Math.sin(time * 0.005);

  for (let i = 0; i < edgeObjects.length; i++) {
    const edge = edgeObjects[i];

    // Adaptação suave para conectivos ligados/desligados
    if (!connectivesVisible) {
      if (edge.userData.isConnectiveEdge) {
        edge.visible = false;
        continue;
      }
      if (edge.userData.isBridgeEdge) {
        edge.visible = true;
      }
    } else {
      if (edge.userData.isBridgeEdge) {
        edge.visible = false;
        continue;
      }
      edge.visible = true;
    }

    const a = edge.userData.sourceNode.sprite.position;
    const b = edge.userData.targetNode.sprite.position;
    const pos = edge.geometry.attributes.position;
    pos.setXYZ(0, a.x, a.y, a.z);
    pos.setXYZ(1, b.x, b.y, b.z);
    pos.needsUpdate = true;

    const isSequenceReply = (edge.userData.kind_id === 'reply_sequence' || edge.userData.kind === 'sequência na resposta');

    if (traceActive) {
      if (isSequenceReply) {
        edge.material.color.copy(TRACE_GOLD);
        edge.material.opacity = pulseOpacity;
      } else {
        edge.material.color.copy(edge.userData.baseColor);
        edge.material.opacity += (0.035 - edge.material.opacity) * 0.15;
      }
    } else if (activeDimension) {
      const matchSource = edge.userData.sourceNode.data.group === activeDimension;
      const matchTarget = edge.userData.targetNode.data.group === activeDimension;
      if (matchSource && matchTarget) {
        edge.material.color.copy(edge.userData.baseColor);
        edge.material.opacity += (0.55 - edge.material.opacity) * 0.15;
      } else {
        edge.material.color.copy(edge.userData.baseColor);
        edge.material.opacity += (0.02 - edge.material.opacity) * 0.15;
      }
    } else {
      edge.material.color.copy(edge.userData.baseColor);
      const targetEdgeOpacity = focus
        ? ((edge.userData.source === focus || edge.userData.target === focus) ? 0.6 : 0.04)
        : 0.15;
      edge.material.opacity += (targetEdgeOpacity - edge.material.opacity) * 0.15;
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
  try {
    stage.releasePointerCapture(e.pointerId);
  } catch (_) {}
  drag = null;
  if (moved) return;

  const rect = stage.getBoundingClientRect();
  const mouse = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1
  );
  const ray = new THREE.Raycaster();
  ray.setFromCamera(mouse, camera);

  const sprites = [];
  for (const n of nodes.values()) {
    sprites.push(n.sprite);
  }
  const found = ray.intersectObjects(sprites);
  focus = found[0]?.object.userData.id || null;
  $('inspector').hidden = !focus;

  if (focus && nodes.has(focus)) {
    const n = nodes.get(focus).data;
    const weightVal = typeof n.weight === 'number' ? n.weight.toFixed(2) : n.weight;
    const weightLabel = n.group === 'probabilidade' ? 'probabilidade' : 'peso lexical';
    $('inspector').textContent = `${n.id} · ${n.group} · origem: ${n.origin} · ${weightLabel}: ${weightVal}`;
  }
});

stage.addEventListener('pointercancel', e => {
  try {
    stage.releasePointerCapture(e.pointerId);
  } catch (_) {}
  drag = null;
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

// Controle de Pausa da Animação
function updatePauseButton() {
  $('pause').textContent = paused ? 'Retomar movimento' : 'Pausar movimento';
  $('pause').setAttribute('aria-pressed', String(paused));
}

$('pause').onclick = () => {
  paused = !paused;
  storage.set(STORAGE_KEYS.PAUSED, paused);
  updatePauseButton();
};

// Controle do Botão Linha da Resposta (Trace)
function updateTraceButton() {
  const btn = $('highlight-trace');
  if (!btn) return;
  btn.setAttribute('aria-pressed', String(traceActive));
  btn.classList.toggle('active', traceActive);
}

$('highlight-trace').onclick = () => {
  traceActive = !traceActive;
  storage.set(STORAGE_KEYS.TRACE, traceActive);
  updateTraceButton();
};

// Controle do Botão Conectivos (Com/Sem Conectivos no Three.js)
function updateConnectivesButton() {
  const btn = $('toggle-connectives');
  if (!btn) return;
  btn.setAttribute('aria-pressed', String(connectivesVisible));
  btn.classList.toggle('active', connectivesVisible);
}

const btnConnectives = $('toggle-connectives');
if (btnConnectives) {
  btnConnectives.onclick = () => {
    connectivesVisible = !connectivesVisible;
    storage.set(STORAGE_KEYS.CONNECTIVES, connectivesVisible);
    updateConnectivesButton();
    if (!connectivesVisible && activeDimension === 'conectivos') {
      activeDimension = null;
      for (const chip of $('legend').children) {
        chip.classList.toggle('active', false);
      }
    }
  };
}

// Tooltip de explicação da proporção e latência (sem ícone)
const tooltipBtn = $('balance-tooltip-btn');
const tooltipCard = $('balance-tooltip-card');
if (tooltipBtn && tooltipCard) {
  tooltipBtn.onclick = (e) => {
    e.stopPropagation();
    tooltipCard.classList.toggle('active');
  };
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.balance-tooltip-container')) {
      tooltipCard.classList.remove('active');
    }
  });
}

// Alternância de Modo: Modelo Local vs Demonstração
function applyModeUI(mode) {
  if (mode === 'local') {
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
}

function setMode(newMode) {
  currentMode = newMode;
  storage.set(STORAGE_KEYS.MODE, currentMode);
  applyModeUI(currentMode);
  health();
  submit();
}

$('btn-mode-local').onclick = () => setMode('local');
$('btn-mode-demo').onclick = () => setMode('demo');

// Gerenciamento da Balança de Tokens e Slider Contínuo
function updateCharCounter() {
  const currentLen = $('prompt').value.length;
  const maxChars = currentPromptTokens * 4;
  $('chars').textContent = `${currentLen} / ${maxChars} (até ~${currentPromptTokens} tokens)`;
}

function calculateBalanceFromSlider(val) {
  const v = Math.max(0, Math.min(100, Number(val)));
  let promptTok, replyTok;
  if (v <= 50) {
    const r = v / 50;
    promptTok = Math.round(1600 - r * 700); // 1600 -> 900
    replyTok = Math.round(30 + r * 110);    // 30 -> 140
  } else {
    const r = (v - 50) / 50;
    promptTok = Math.round(900 - r * 700);  // 900 -> 200
    replyTok = Math.round(140 + r * 140);   // 140 -> 280
  }
  return { promptTok, replyTok };
}

function updateBalanceUI(promptTok, replyTok, sliderVal, activePresetId = null) {
  currentPromptTokens = promptTok;
  currentReplyTokens = replyTok;
  currentSliderVal = sliderVal;

  const maxChars = promptTok * 4;
  $('prompt').maxLength = maxChars;
  updateCharCounter();

  const promptLabel = $('slider-prompt-label');
  if (promptLabel) promptLabel.innerHTML = `Pergunta: <strong>${promptTok}</strong> tokens`;
  const replyLabel = $('slider-reply-label');
  if (replyLabel) replyLabel.innerHTML = `Resposta: <strong>${replyTok}</strong> tokens`;

  const slider = $('balance-slider');
  if (slider && Number(slider.value) !== sliderVal) {
    slider.value = sliderVal;
  }

  $('token-capacity').textContent = `Prévia · até ${replyTok} tokens`;

  for (const btn of document.querySelectorAll('.balance-btn')) {
    const isActive = activePresetId && (btn.dataset.preset === activePresetId);
    btn.classList.toggle('active', !!isActive);
    btn.setAttribute('aria-pressed', String(!!isActive));
  }

  storage.set(STORAGE_KEYS.BALANCE_PROMPT, promptTok);
  storage.set(STORAGE_KEYS.BALANCE_REPLY, replyTok);
  storage.set(STORAGE_KEYS.BALANCE_SLIDER, sliderVal);
  if (activePresetId) {
    storage.set(STORAGE_KEYS.BALANCE, activePresetId);
  }
}

function setBalancePreset(presetId, triggerSubmit = true) {
  const preset = BALANCE_PRESETS[presetId];
  if (!preset) return;
  currentPreset = presetId;
  updateBalanceUI(preset.maxPromptTokens, preset.maxTokens, preset.sliderValue, presetId);
  if (triggerSubmit && $('prompt').value.trim()) {
    submit();
  }
}

function onSliderInput(val) {
  const { promptTok, replyTok } = calculateBalanceFromSlider(val);
  let matchedPreset = null;
  if (Math.abs(val - BALANCE_PRESETS.detailed.sliderValue) <= 2) matchedPreset = 'detailed';
  else if (Math.abs(val - BALANCE_PRESETS.balanced.sliderValue) <= 2) matchedPreset = 'balanced';
  else if (Math.abs(val - BALANCE_PRESETS.expanded.sliderValue) <= 2) matchedPreset = 'expanded';

  currentPreset = matchedPreset || 'custom';
  updateBalanceUI(promptTok, replyTok, Number(val), matchedPreset);
}

for (const btn of document.querySelectorAll('.balance-btn')) {
  btn.onclick = () => setBalancePreset(btn.dataset.preset);
}

const balanceSlider = $('balance-slider');
let sliderSubmitDebounce = null;
if (balanceSlider) {
  balanceSlider.addEventListener('input', (e) => {
    onSliderInput(e.target.value);
  });
  balanceSlider.addEventListener('change', () => {
    if ($('prompt').value.trim()) {
      clearTimeout(sliderSubmitDebounce);
      sliderSubmitDebounce = setTimeout(() => submit(), 150);
    }
  });
}

// Lista de palavras gramaticais/funcionais para classificar candidatos
const functionalTokens = new Set(
  ('a ao aos à às o os as um uma uns umas de do da dos das em no nos na nas por para com sem ' +
  'sobre entre até após antes desde contra perante segundo conforme que se e ou mas porém portanto ' +
  'porque pois como eu tu ele ela nós vocês voce você me te se lhe lhes meu minha seus suas este esta ' +
  'isso isto aquilo aqui aí ali lá não sim já ainda também muito mais menos bem mal sempre nunca talvez').split(' ')
);

// Renderiza a lista de alternativas com barras percentuais proporcionais
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
    const extra = (items || []).slice(0, 12).map(c => ({
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

  if (!items || !items.length) {
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
      const nameMatch = packet.match(/^event:\s*(.+)$/m);
      const rawMatch = packet.match(/^data:\s*(.+)$/m);
      if (nameMatch && rawMatch) {
        try {
          onEvent(nameMatch[1].trim(), JSON.parse(rawMatch[1].trim()));
        } catch (err) {
          console.error('Erro ao processar pacote SSE:', err);
        }
      }
    }
  }
}

// Submissão do texto digitado com parâmetros dinâmicos da balança de tokens
async function submit(text = $('prompt').value) {
  version++;
  const requestVersion = version;
  currentText = text;
  $('input-status').textContent = 'Atualização automática · espaço + 250 ms';

  if (!text.trim()) {
    applyGraph({ nodes: [], edges: [], groups: [] });
    $('answer').textContent = 'Sua resposta aparecerá aqui e será reformulada enquanto você escreve.';
    $('generation-state').textContent = 'Aguardando contexto';
    $('answer-version').textContent = '—';
    $('words').textContent = '0';
    const promptTokElem = $('tokens-prompt') || $('tokens');
    if (promptTokElem) promptTokElem.textContent = '—';
    const replyTokElem = $('tokens-reply');
    if (replyTokElem) replyTokElem.textContent = '—';
    $('speed').textContent = '—';
    $('token-capacity').textContent = `Prévia · até ${currentReplyTokens} tokens`;
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

  const requestStartTime = performance.now();
  let firstTokenTime = null;
  let chunkCount = 0;

  measurement = {
    version: requestVersion,
    mode: currentMode,
    preset: currentPreset,
    slider_value: currentSliderVal,
    max_tokens: currentReplyTokens,
    max_prompt_tokens: currentPromptTokens,
    trace_active: traceActive,
    connectives_visible: connectivesVisible,
    started_at: new Date().toISOString()
  };

  $('answer').textContent = '';
  $('generation-state').textContent = currentMode === 'demo' ? 'Demonstração em andamento…' : 'Processando na CPU…';
  if (currentMode === 'local') {
    $('notice').textContent = 'Inferência com modelo Qwen quantizado em CPU · Totalmente local.';
  } else {
    $('notice').textContent = 'Modo Demonstração ativo. Navegação 3D sem necessidade do modelo em execução.';
  }
  candidates([]);
  const initPromptTok = $('tokens-prompt') || $('tokens');
  if (initPromptTok) initPromptTok.textContent = '—';
  const initReplyTok = $('tokens-reply');
  if (initReplyTok) initReplyTok.textContent = '—';
  $('speed').textContent = '—';

  try {
    await streamPost(
      '/api/generate',
      {
        text,
        mode: currentMode,
        max_tokens: currentReplyTokens,
        max_prompt_tokens: currentPromptTokens
      },
      requestAbort.signal,
      (name, result) => {
        if (requestVersion !== version) return;

        if (name === 'chunk') {
          if (firstTokenTime === null) {
            firstTokenTime = performance.now();
          }
          chunkCount++;
          $('answer').textContent += result.text || '';
          $('generation-state').textContent = currentMode === 'demo' ? 'Exibindo demonstração…' : 'Gerando resposta…';
          $('token-capacity').textContent = `Gerando · ${chunkCount} / ${currentReplyTokens} tokens…`;
          candidates(result.candidates || []);
          return;
        }

        if (name === 'error') {
          throw new Error(result.message);
        }

        if (name === 'done') {
          const endTime = performance.now();
          const ttft_ms = firstTokenTime !== null ? Math.round(firstTokenTime - requestStartTime) : null;
          const totalDurationSec = Math.max(0.001, (endTime - requestStartTime) / 1000);
          const outTokens = result.output_tokens != null
            ? result.output_tokens
            : (result.answer ? result.answer.trim().split(/\s+/).length : chunkCount);
          const tokens_s = (outTokens && totalDurationSec > 0)
            ? Math.round((outTokens / totalDurationSec) * 10) / 10
            : null;

          $('answer').textContent = result.answer || $('answer').textContent;
          $('answer-version').textContent = `v${requestVersion} · atual`;
          $('generation-state').textContent = 'Prévia concluída · continue escrevendo';
          $('token-capacity').textContent = `Concluída · ${outTokens} de ${currentReplyTokens} tokens utilizados`;

          const promptTokElem = $('tokens-prompt') || $('tokens');
          if (promptTokElem) promptTokElem.textContent = result.text_tokens != null ? result.text_tokens : '—';
          const replyTokElem = $('tokens-reply');
          if (replyTokElem) replyTokElem.textContent = outTokens;

          $('speed').textContent = result.words_s != null
            ? `${result.words_s} palavras/s`
            : (tokens_s ? `${tokens_s} tokens/s` : '—');
          candidates(result.candidates || []);
          if (result.graph) {
            applyGraph(result.graph);
          }
          $('graph-version').textContent = '';

          const recordEntry = {
            ...measurement,
            preset: currentPreset,
            slider_value: currentSliderVal,
            max_tokens: currentReplyTokens,
            max_prompt_tokens: currentPromptTokens,
            trace_active: traceActive,
            connectives_visible: connectivesVisible,
            ttft_ms,
            tokens_s,
            ...result
          };
          records.push(recordEntry);
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
  updateCharCounter();
  clearTimeout(pauseTimer);
  if (e.isComposing) return;

  if (/\s/.test(e.data || '') || e.inputType === 'insertFromPaste' || e.inputType?.startsWith('delete')) {
    clearTimeout(inputTimer);
    const snapshot = e.target.value;
    inputTimer = setTimeout(() => submit(snapshot), 250);
  }

  pauseTimer = setTimeout(() => {
    if (e.target.value !== currentText) {
      clearTimeout(inputTimer);
      submit();
    }
  }, 850);
});

$('prompt').addEventListener('compositionend', () => {
  clearTimeout(inputTimer);
  inputTimer = setTimeout(() => submit(), 250);
});

// Exemplos rápidos
for (const b of document.querySelectorAll('[data-example]')) {
  b.onclick = () => {
    $('prompt').value = b.dataset.example;
    updateCharCounter();
    clearTimeout(inputTimer);
    clearTimeout(pauseTimer);
    submit();
    $('prompt').focus();
  };
}

// Exportação de medições JSON com telemetria detalhada
$('export').onclick = () => {
  const exportPayload = {
    prototype: '0.1',
    exported_at: new Date().toISOString(),
    session_config: {
      mode: currentMode,
      preset: currentPreset,
      trace_active: traceActive,
      connectives_visible: connectivesVisible,
      paused: paused
    },
    records
  };
  const blob = new Blob(
    [JSON.stringify(exportPayload, null, 2)],
    { type: 'application/json' }
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'universo-medicoes.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

// Polling de conectividade com o modelo local
async function health() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (data.ready) {
      $('connection').textContent = 'Modelo CPU conectado';
      $('connection').style.color = '#81e1d0';
    } else {
      if (currentMode === 'demo') {
        $('connection').textContent = 'Modo Demonstração';
        $('connection').style.color = '#81e1d0';
      } else {
        $('connection').textContent = 'Modelo desconectado';
        $('connection').style.color = '#8f9eaf';
      }
    }
  } catch (_) {
    if (currentMode === 'demo') {
      $('connection').textContent = 'Modo Demonstração';
      $('connection').style.color = '#81e1d0';
    } else {
      $('connection').textContent = 'Aplicação offline';
      $('connection').style.color = '#8f9eaf';
    }
  }
}

// Execução inicial com restauração de preferências salvas
applyModeUI(currentMode);
updateBalanceUI(currentPromptTokens, currentReplyTokens, currentSliderVal, currentPreset !== 'custom' ? currentPreset : null);
updateTraceButton();
updateConnectivesButton();
updatePauseButton();
health();
setInterval(health, 15000);

// Disparo inicial se houver texto prévio no carregamento
setTimeout(() => {
  if ($('prompt').value && $('prompt').value !== currentText) {
    submit();
  }
}, 350);
