"""Universo Local: inferência e grafo 3D em loopback. 100% privado e local."""
import asyncio
import json
import math
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

ROOT = Path(__file__).parent
LLAMA = 'http://127.0.0.1:8081'

# Configuração de pooling HTTP persistente para máxima performance e baixa latência
CLIENT_LIMITS = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0)
CLIENT_TIMEOUT = httpx.Timeout(120.0, connect=3.0)
_HTTP_CLIENT: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Retorna cliente HTTP persistente com reaproveitamento de conexões TCP (Keep-Alive)."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(
            limits=CLIENT_LIMITS,
            timeout=CLIENT_TIMEOUT
        )
    return _HTTP_CLIENT


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida do cliente HTTP para conexões com llama.cpp."""
    get_client()
    yield
    global _HTTP_CLIENT
    if _HTTP_CLIENT and not _HTTP_CLIENT.is_closed:
        await _HTTP_CLIENT.aclose()


app = FastAPI(
    title='Universo Local',
    description='Navegação tridimensional em modelo de linguagem',
    lifespan=lifespan
)
INFERENCE_LOCK = asyncio.Lock()

STOP = set()

CONNECTIVES = {
    # Preposições e contrações
    'de', 'do', 'da', 'dos', 'das', 'em', 'no', 'na', 'nos', 'nas',
    'por', 'pelo', 'pela', 'pelos', 'pelas', 'para', 'pra', 'com', 'sem',
    'sob', 'sobre', 'entre', 'até', 'após', 'desde', 'contra', 'perante',
    'ao', 'aos', 'à', 'às', 'dum', 'duma', 'num', 'numa',
    # Artigos
    'a', 'o', 'as', 'os', 'um', 'uma', 'uns', 'umas',
    # Conjunções
    'que', 'se', 'e', 'ou', 'mas', 'porque', 'porquê', 'pois', 'como',
    'embora', 'portanto', 'contudo', 'todavia', 'entretanto', 'logo',
    'assim', 'caso', 'quando', 'enquanto', 'conforme', 'segundo',
    # Pronomes estruturais e demonstrativos
    'eu', 'tu', 'ele', 'ela', 'nós', 'vós', 'eles', 'elas', 'você', 'vocês', 'voce',
    'me', 'te', 'se', 'lhe', 'lhes', 'nos', 'vos', 'mim', 'ti', 'si',
    'este', 'esta', 'estes', 'estas', 'esse', 'essa', 'esses', 'essas',
    'aquele', 'aquela', 'aqueles', 'aquelas', 'isto', 'isso', 'aquilo',
    'meu', 'minha', 'meus', 'minhas', 'teu', 'tua', 'teus', 'tuas',
    'seu', 'sua', 'seus', 'suas', 'nosso', 'nossa', 'nossos', 'nossas',
    'qual', 'quais', 'quem', 'cujo', 'cuja', 'cujos', 'cujas', 'onde',
    # Advérbios estruturais e de ligação
    'não', 'sim', 'já', 'muito', 'mais', 'menos', 'bem', 'mal',
    'sempre', 'nunca', 'ainda', 'também', 'talvez', 'aqui', 'ali', 'lá',
    # Verbos de ligação e auxiliares comuns
    'é', 'são', 'era', 'eram', 'foi', 'foram', 'ser', 'sendo', 'seja', 'sejam', 'será', 'serão',
    'está', 'estão', 'estava', 'estavam', 'esteve', 'estar', 'estando', 'esteja', 'estejam',
    'tem', 'têm', 'tinha', 'tinham', 'teve', 'ter', 'tendo', 'tenha', 'tenham',
    'há', 'havia', 'houve', 'haver', 'havendo'
}

GROUPS = {
    'tecnologia': [
        'inteligência', 'artificial', 'modelo', 'token', 'tokens', 'rede', 'neural', 'dados',
        'algoritmo', 'computador', 'ia', 'llm', 'código', 'software', 'aprendizado', 'máquina',
        'treinamento', 'padrão', 'probabilidade', 'informação', 'parâmetros', 'atenção', 'vetor',
        'hardware', 'servidor', 'digital', 'automação', 'sistema',
        'processamento', 'computação', 'dispositivo'
    ],
    'linguagem': [
        'linguagem', 'palavra', 'palavras', 'texto', 'leitura', 'escrita', 'fala', 'significado',
        'contexto', 'português', 'inglês', 'semântica', 'frase', 'pergunta', 'resposta',
        'interpretação', 'vocabulário', 'gramática', 'sentido', 'expressão', 'sintaxe', 'discurso',
        'linguístico', 'linguísticos', 'expressões', 'comunicação'
    ],
    'ciência': [
        'ciência', 'pesquisa', 'hipótese', 'teoria', 'experimento', 'método', 'física', 'química',
        'biologia', 'evolução', 'energia', 'átomo', 'molécula', 'laboratório', 'descoberta',
        'análise', 'evidência', 'matemática', 'cálculo', 'complexidade'
    ],
    'mente': [
        'mente', 'cérebro', 'pensamento', 'consciência', 'memória', 'neurônio', 'cognição',
        'psicologia', 'percepção', 'raciocínio', 'ideia', 'emoção', 'sentimento', 'inteligência',
        'aprendizagem', 'imaginação', 'intuição', 'compreensão',
        'entende', 'entender', 'compreende', 'compreender', 'entendimento', 'capaz', 'capacidade',
        'potencial', 'cognitivo', 'pensar', 'aprender', 'interpreta', 'interpretar'
    ],
    'natureza': [
        'natureza', 'ambiente', 'planeta', 'terra', 'vida', 'animal', 'planta', 'floresta',
        'ecologia', 'clima', 'água', 'rio', 'mar', 'oceano', 'fauna', 'flora', 'ecossistema',
        'sustentabilidade', 'árvore', 'bioma', 'biodiversidade'
    ],
    'sociedade': [
        'sociedade', 'cultura', 'comunidade', 'povo', 'humano', 'humanidade', 'cidadão',
        'cidadania', 'história', 'tradição', 'política', 'população', 'governo', 'democracia',
        'social', 'civilização', 'coletivo', 'identidade', 'público',
        'brasil', 'brasília', 'país', 'nação', 'estado', 'cidade', 'capital'
    ],
    'economia': [
        'economia', 'mercado', 'dinheiro', 'moeda', 'preço', 'valor', 'custo', 'investimento',
        'finanças', 'capital', 'comércio', 'empresa', 'produção', 'consumo', 'crédito',
        'banco', 'inflação', 'renda', 'trabalho', 'negócio'
    ],
    'filosofia': [
        'filosofia', 'ética', 'moral', 'existência', 'verdade', 'razão', 'lógica', 'epistemologia',
        'ontologia', 'conhecimento', 'sabedoria', 'justiça', 'ser', 'metafísica', 'crítica',
        'virtude', 'reflexão', 'princípio', 'pensador'
    ],
    'arte': [
        'arte', 'música', 'pintura', 'escultura', 'design', 'estética', 'beleza', 'criatividade',
        'poesia', 'cinema', 'teatro', 'dança', 'literatura', 'artista', 'harmonia', 'ritmo',
        'cor', 'obra', 'expressão', 'estilo'
    ],
    'saúde': [
        'saúde', 'corpo', 'medicina', 'médico', 'doença', 'cura', 'tratamento', 'bem-estar',
        'exercício', 'alimentação', 'nutrição', 'imunidade', 'terapia', 'sono', 'hospital',
        'prevenção', 'diagnóstico', 'paciente', 'vitalidade'
    ],
    'viagem': [
        'viagem', 'viajar', 'japão', 'primavera', 'cerejeiras', 'roteiro', 'cultura', 'cidade',
        'clima', 'tóquio', 'paris', 'hotel', 'passagem', 'destino', 'turismo', 'paisagem',
        'tradição', 'estação', 'mundo', 'bagagem', 'voo', 'aventura'
    ],
    'cotidiano': [
        'cotidiano', 'rotina', 'vida', 'pessoa', 'pessoas', 'tempo', 'dia', 'casa', 'família',
        'bolo', 'chocolate', 'cozinha', 'ingrediente', 'hábito', 'experiência', 'manhã',
        'noite', 'tarefa', 'horário', 'descanso'
    ],
    'esporte': [
        'esporte', 'futebol', 'jogo', 'atleta', 'treino', 'competição', 'partida', 'campeonato',
        'vitória', 'corrida', 'natação', 'físico', 'ginástica', 'time', 'bola', 'quadra',
        'estádio', 'desempenho', 'modalidade'
    ],
    'direito': [
        'direito', 'lei', 'justiça', 'norma', 'tribunal', 'juiz', 'advogado', 'constituição',
        'processo', 'crime', 'pena', 'dever', 'legal', 'jurídico', 'regra', 'contrato',
        'legislação', 'código', 'ordem'
    ],
    'espaço': [
        'espaço', 'universo', 'astro', 'astronomia', 'estrela', 'galáxia', 'planeta', 'lua',
        'sol', 'órbita', 'gravidade', 'foguete', 'telescópio', 'cosmo', 'satélite',
        'solar', 'interestelar', 'constelação'
    ],
    'comunicação': [
        'comunicação', 'mídia', 'mensagem', 'conversa', 'diálogo', 'notícia', 'jornalismo',
        'informação', 'rede', 'internet', 'transmissão', 'contato', 'relato', 'compartilhar',
        'voz', 'canal', 'interação', 'emissor', 'receptor'
    ],
}

WORDS_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)
CANDIDATE_RE = re.compile(r'[A-Za-zÀ-ÿ]{2,}')
GROUPS_SET = {g: set(words_list) for g, words_list in GROUPS.items()}
ALL_GROUP_WORDS = set().union(*GROUPS_SET.values())


def words(text: str):
    """Extrai palavras limpas com suporte a caracteres acentuados da língua portuguesa."""
    return WORDS_RE.findall(text.lower())


def readable_candidates(items):
    """Filtra e preserva alternativas de tokens que formam fragmentos legíveis de palavras."""
    clean = []
    seen = set()
    for item in items:
        token = str(item.get('token', '')).strip()
        if not CANDIDATE_RE.search(token) or token in seen:
            continue
        seen.add(token)
        clean.append(dict(token=token, probability=math.exp(item['logprob'])))
    return clean


def normalize_dynamic_group(word: str) -> str:
    """
    Normaliza morfologicamente termos desconhecidos para agrupamento semântico conceitual.
    Garante nomes descritivos padronizados (ação/efeito, qualidade/estado ou conceito).
    """
    w = word.lower().strip()
    # Adjetivos / Qualidades / Estados (sufixos típicos em português)
    if w.endswith(('nte', 'vel', 'oso', 'osa', 'az', 'il', 'ivo', 'iva', 'al', 'ico', 'ica')):
        return f'qualidade: {w}'
    # Verbos / Ações / Efeitos (terminações verbais comuns em português)
    if w.endswith(('ar', 'er', 'ir', 'ando', 'endo', 'indo', 'ou', 'eu', 'iu', 'aria', 'eria', 'iria', 'asse', 'esse', 'isse', 'am', 'em')):
        return f'ação: {w}'
    # Substantivos e termos conceituais gerais
    return f'conceito: {w}'


def graph(text: str, answer: str = ''):
    """
    Heurística lexical determinística e rápida para alimentar o Three.js.
    Destaca termos do texto de entrada e da resposta gerada, organizando conexões por
    grupos conceituais, sequências de frases e clusters dinâmicos com conectivos estruturais.
    """
    source = [w for w in words(text) if (w in CONNECTIVES or (w not in STOP and (len(w) > 2 or w in ALL_GROUP_WORDS)))]
    reply = [w for w in words(answer) if (w in CONNECTIVES or (w not in STOP and (len(w) > 2 or w in ALL_GROUP_WORDS)))]

    # Ampla cobertura de termos da resposta para enriquecer a exploração visual
    keys = list(dict.fromkeys(source + reply))[-110:]

    # Identificação de termos desconhecidos para formação de cluster dinâmico emergente por oração
    unknown_keys = [w for w in keys if w not in CONNECTIVES and not any(w in s for s in GROUPS_SET.values())]
    dynamic_group_map = {}
    if unknown_keys:
        full_text = f"{text}\n{answer}"
        clauses = [c.strip() for c in re.split(r'[.!?;:\n]+', full_text) if c.strip()]
        adj = {w: set() for w in unknown_keys}
        for clause in clauses:
            clause_words = set(words(clause))
            found = [w for w in unknown_keys if w in clause_words]
            for i, w1 in enumerate(found):
                for w2 in found[i + 1:]:
                    adj[w1].add(w2)
                    adj[w2].add(w1)

        visited = set()
        for w in unknown_keys:
            if w not in visited:
                comp = []
                queue = [w]
                visited.add(w)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                root = min(comp, key=lambda x: keys.index(x))
                group_name = normalize_dynamic_group(root)
                for member in comp:
                    dynamic_group_map[member] = group_name

    active = [g for g, vocab_set in GROUPS_SET.items() if any(w in vocab_set for w in source + reply)]

    expanded = []
    for g in active:
        expanded.extend([(w, g) for w in GROUPS[g][:10] if w not in keys])

    nodes = []
    for w in keys:
        if w in CONNECTIVES:
            g = 'conectivos'
            weight = 0.22
            origin = 'conectivo'
        else:
            g = next((group_name for group_name, vocab_set in GROUPS_SET.items() if w in vocab_set), None)
            if g is None:
                g = dynamic_group_map.get(w, normalize_dynamic_group(w))
            if w in source:
                weight = min(1.0, 0.50 + 0.12 * source.count(w))
                origin = 'entrada'
            else:
                weight = min(0.95, 0.42 + 0.08 * reply.count(w))
                origin = 'resposta'
        nodes.append(dict(
            id=w,
            group=g,
            weight=round(weight, 2),
            origin=origin,
            in_reply=(w in reply),
            in_source=(w in source)
        ))

    for w, g in expanded[:50]:
        nodes.append(dict(
            id=w,
            group=g,
            weight=0.25,
            origin='vocabulário demonstrativo',
            in_reply=False,
            in_source=False
        ))

    edges = []
    edges_dict = {}

    def add_edge(s: str, t: str, weight: float, kind: str, is_shortcut: bool = False):
        if s == t:
            return
        pair = (s, t) if s < t else (t, s)
        # Se a aresta já existe com menor prioridade, 'sequência na resposta' tem precedência
        # para que o caminho cronológico da resposta formulada seja 100% contínuo
        kind_id = 'reply_sequence' if 'resposta' in kind else ('prompt_sequence' if 'texto' in kind else 'lexical_group')
        if pair in edges_dict:
            existing = edges_dict[pair]
            old_kind_id = existing.get('kind_id')
            old_is_shortcut = existing.get('is_shortcut', False)
            if kind == 'sequência na resposta':
                existing['kind'] = 'sequência na resposta'
                existing['kind_id'] = 'reply_sequence'
                existing['weight'] = max(existing['weight'], weight)
                if not (old_kind_id == 'reply_sequence' and not old_is_shortcut):
                    existing['is_shortcut'] = is_shortcut
            elif kind == 'sequência no texto' and old_kind_id != 'reply_sequence':
                existing['kind'] = 'sequência no texto'
                existing['kind_id'] = 'prompt_sequence'
                existing['weight'] = max(existing['weight'], weight)
                if not (old_kind_id == 'prompt_sequence' and not old_is_shortcut):
                    existing['is_shortcut'] = is_shortcut
            return
        edge_obj = dict(source=s, target=t, weight=weight, kind=kind, kind_id=kind_id, is_shortcut=is_shortcut)
        edges_dict[pair] = edge_obj
        edges.append(edge_obj)

    # Conexões por proximidade de grupo conceitual (ignora conectivos para não poluir os conceitos)
    for i, node in enumerate(nodes):
        if node['group'] == 'conectivos':
            continue
        peers = [n for n in nodes[:i] if n['group'] == node['group']][-4:]
        for peer in peers:
            add_edge(peer['id'], node['id'], 0.5, 'grupo lexical')

    # Conexões por sequência natural das frases digitadas na pergunta
    for a, b in zip(source, source[1:]):
        if a in keys and b in keys:
            add_edge(a, b, 0.8, 'sequência no texto')

    # Atalhos sequenciais entre palavras de conteúdo na pergunta (quando conectivos estiverem ocultos)
    source_content = [w for w in source if w not in CONNECTIVES]
    for a, b in zip(source_content, source_content[1:]):
        if a in keys and b in keys:
            add_edge(a, b, 0.78, 'sequência no texto', is_shortcut=True)

    # Conexões por sequência cronológica contínua da resposta da IA (precedência máxima na linha de resposta)
    for a, b in zip(reply, reply[1:]):
        if a in keys and b in keys:
            add_edge(a, b, 0.9, 'sequência na resposta')

    # Atalhos sequenciais entre palavras de conteúdo na resposta (quando conectivos estiverem ocultos)
    reply_content = [w for w in reply if w not in CONNECTIVES]
    for a, b in zip(reply_content, reply_content[1:]):
        if a in keys and b in keys:
            add_edge(a, b, 0.88, 'sequência na resposta', is_shortcut=True)

    # Ordenação da legenda: conectivos primeiro (ou padrão), grupos semânticos estáveis no meio,
    # e grupos dinâmicos ('conceito:', 'ação:', 'qualidade:', 'tema:') obrigatoriamente por último (à direita)
    all_groups = list(dict.fromkeys(n['group'] for n in nodes))
    standard_groups = [g for g in all_groups if not any(g.startswith(p) for p in ('tema:', 'ação:', 'qualidade:', 'conceito:'))]
    dynamic_groups = [g for g in all_groups if any(g.startswith(p) for p in ('tema:', 'ação:', 'qualidade:', 'conceito:'))]
    sorted_groups = standard_groups + dynamic_groups

    return dict(
        nodes=nodes,
        edges=edges,
        groups=sorted_groups,
        reply_sequence=[w for w in reply if w in keys],
        method='Heurística lexical: grupos explícitos e sequência no texto; sem embeddings.'
    )


@app.get('/api/status')
async def status():
    """Verifica a disponibilidade do runtime llama.cpp na porta local 8081."""
    try:
        client = get_client()
        response = await client.get(LLAMA + '/health', timeout=1.5)
        response.raise_for_status()
        return {'ready': True, 'engine': 'llama.cpp · CPU', 'model': 'Qwen2.5-0.5B-Instruct Q4_K_M'}
    except (httpx.HTTPError, ValueError):
        return {'ready': False, 'engine': 'llama.cpp · CPU', 'model': 'não conectado'}


@app.post('/api/graph')
async def api_graph(data: dict):
    """Gera instantaneamente o mapa de nós e arestas para renderização preliminar no Three.js."""
    text = str(data.get('text', ''))[:4000]
    return {'graph': graph(text), 'words': len(words(text))}


@app.post('/api/generate')
async def api_generate(data: dict):
    """
    Geração em streaming HTTP Server-Sent Events (SSE).
    Suporta balança dinâmica de tokens (max_tokens e max_prompt_tokens) e telemetria de inferência.
    """
    text = str(data.get('text', ''))[:4000]
    mode = 'demo' if data.get('mode') == 'demo' else 'local'

    try:
        max_tokens = int(data.get('max_tokens') or 140)
        if max_tokens <= 0:
            max_tokens = 140
    except (ValueError, TypeError):
        max_tokens = 140

    try:
        max_prompt_tokens = int(data.get('max_prompt_tokens') or 900)
        if max_prompt_tokens <= 0:
            max_prompt_tokens = 900
    except (ValueError, TypeError):
        max_prompt_tokens = 900

    def event(name, **payload) -> str:
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def stream():
        if not text.strip():
            yield event(
                'done',
                answer='',
                graph=graph(''),
                candidates=[],
                max_tokens_config=max_tokens,
                ttft_ms=None,
                output_tokens=0,
                text_tokens=0,
                words_s=None
            )
            return

        started = time.perf_counter()

        if mode == 'demo':
            prompt_words_count = len(words(text))
            if prompt_words_count > max_prompt_tokens:
                yield event(
                    'error',
                    message=f'Texto excede o limite configurado de {max_prompt_tokens} tokens. Ajuste na balança ou reduza a pergunta.'
                )
                return

            terms = [n['id'] for n in graph(text)['nodes'] if n['origin'] == 'entrada']
            destaque = ', '.join(terms[:6]) if terms else 'as palavras digitadas'
            answer = (
                f'Demonstração visual (sem modelo ativo): o texto destaca {destaque}. '
                'O mapa 3D organiza os conceitos por afinidade e sequência. '
                'Para gerar respostas reais e ver probabilidades ao vivo, ative o Modo Modelo Local.'
            )
            for fragment in re.findall(r'\S+\s*', answer):
                yield event('chunk', text=fragment, candidates=[])
                await asyncio.sleep(0.025)

            elapsed = max(0.01, time.perf_counter() - started)
            yield event(
                'done',
                answer=answer,
                graph=graph(text, answer),
                candidates=[],
                max_tokens_config=max_tokens,
                ttft_ms=None,
                output_tokens=len(re.findall(r'\S+\s*', answer)),
                text_tokens=prompt_words_count,
                words_s=round(len(words(answer)) / elapsed, 1)
            )
            return

        answer = ''
        latest_candidates = []
        output_tokens = 0
        ttft_ms = None
        client = get_client()

        try:
            # System prompt balanceado para enriquecer o vocabulário e a cena 3D
            system = (
                'Responda em português com clareza e precisão didática, explicando o conceito em um parágrafo '
                'fluido e rico em termos relevantes. O usuário está explorando as palavras e conexões deste tema; '
                'seja informativo, natural e não invente fatos.'
            )
            messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': text}]

            # Contagem prévia ágil e resiliente sem atrasar o TTFT (Time To First Token)
            prompt_count = 0
            try:
                # Timeout ultrarrápido (0.25s) para não prender o início da inferência
                template_resp = await client.post(
                    LLAMA + '/apply-template',
                    json={'messages': messages, 'add_generation_prompt': True},
                    timeout=httpx.Timeout(0.25, connect=0.1)
                )
                if template_resp.status_code == 200:
                    rendered = template_resp.json().get('prompt', '')
                    tok_resp = await client.post(
                        LLAMA + '/tokenize',
                        json={'content': rendered},
                        timeout=httpx.Timeout(0.15, connect=0.1)
                    )
                    if tok_resp.status_code == 200:
                        prompt_count = len(tok_resp.json().get('tokens', []))
            except Exception:
                # Fallback imediato: tenta tokenize direto com timeout ultracurto ou estimação lexical
                try:
                    tok_resp = await client.post(
                        LLAMA + '/tokenize',
                        json={'content': text},
                        timeout=httpx.Timeout(0.15, connect=0.1)
                    )
                    if tok_resp.status_code == 200:
                        prompt_count = len(tok_resp.json().get('tokens', [])) + 55
                except Exception:
                    prompt_count = len(words(text)) + 55

            if not prompt_count:
                prompt_count = len(words(text)) + 55

            if prompt_count > max_prompt_tokens:
                yield event(
                    'error',
                    message=f'Texto excede o limite configurado de {max_prompt_tokens} tokens. Ajuste na balança ou reduza a pergunta.'
                )
                return

            # Limite de tokens de saída dinâmico configurado pela balança
            payload = dict(
                model='local',
                messages=messages,
                stream=True,
                max_tokens=max_tokens,
                temperature=0.7,
                top_p=1.0,
                top_k=0,
                logprobs=True,
                top_logprobs=50,
                cache_prompt=True
            )

            async with INFERENCE_LOCK:
                async with client.stream('POST', LLAMA + '/v1/chat/completions', json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data: '):
                            continue
                        raw = line[6:].strip()
                        if raw == '[DONE]':
                            break
                        if not raw:
                            continue
                        packet = json.loads(raw)
                        choices = packet.get('choices') or []
                        if not choices:
                            continue
                        choice = choices[0]
                        fragment = choice.get('delta', {}).get('content') or ''
                        logs = (choice.get('logprobs') or {}).get('content') or []
                        if logs:
                            output_tokens += len(logs)
                            latest_candidates = readable_candidates(logs[-1].get('top_logprobs', []))
                        if fragment or logs:
                            if ttft_ms is None:
                                ttft_ms = round((time.perf_counter() - started) * 1000, 1)
                        if fragment:
                            answer += fragment
                            yield event('chunk', text=fragment, candidates=latest_candidates)

            elapsed = max(0.01, time.perf_counter() - started)
            yield event(
                'done',
                answer=answer,
                graph=graph(text, answer),
                candidates=latest_candidates,
                max_tokens_config=max_tokens,
                ttft_ms=ttft_ms,
                text_tokens=prompt_count or len(words(text)),
                output_tokens=output_tokens,
                words_s=round(len(words(answer)) / elapsed, 1) if answer else None
            )

        except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            yield event(
                'error',
                message='Modelo local indisponível ou em inicialização. Verifique se o INICIAR_APP.bat está aberto. Detalhe: ' + str(exc)[:300]
            )

    return StreamingResponse(
        stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


app.mount('/', StaticFiles(directory=ROOT / 'static', html=True), name='static')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning')
