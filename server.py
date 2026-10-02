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

STOP = set(
    'a o as os um uma uns umas de do da dos das em no na nos nas e ou que para por com como se '
    'eu você voce ele ela nós nos eles elas quero qual quais sobre é são ao me meu minha seu sua '
    'isso esse essa este esta aquele aquela aqui ali lá muito mais menos bem mal sempre nunca'.split()
)

GROUPS = {
    'tecnologia': [
        'inteligência', 'artificial', 'modelo', 'token', 'tokens', 'rede', 'neural', 'dados',
        'algoritmo', 'computador', 'ia', 'llm', 'código', 'software', 'aprendizado', 'máquina',
        'treinamento', 'padrão', 'probabilidade', 'informação', 'parâmetros', 'atenção', 'vetor'
    ],
    'linguagem': [
        'linguagem', 'palavra', 'palavras', 'texto', 'leitura', 'escrita', 'fala', 'significado',
        'contexto', 'português', 'inglês', 'comunicação', 'semântica', 'frase', 'pergunta',
        'resposta', 'interpretação', 'vocabulário', 'gramática', 'sentido', 'expressão', 'sintaxe'
    ],
    'ciência': [
        'ciência', 'cérebro', 'memória', 'neurônio', 'energia', 'universo', 'física', 'pesquisa',
        'hipótese', 'atenção', 'aprendizagem', 'conhecimento', 'processo', 'análise', 'raciocínio',
        'resultado', 'teoria', 'evolução', 'complexidade', 'descoberta'
    ],
    'viagem': [
        'viagem', 'viajar', 'japão', 'primavera', 'cerejeiras', 'roteiro', 'cultura', 'cidade',
        'clima', 'tóquio', 'paris', 'hotel', 'passagem', 'destino', 'turismo', 'paisagem',
        'tradição', 'estação', 'mundo'
    ],
    'cotidiano': [
        'trabalho', 'vida', 'pessoa', 'pessoas', 'tempo', 'dia', 'casa', 'saúde', 'alimentação',
        'sono', 'rotina', 'família', 'receita', 'bolo', 'chocolate', 'cozinha', 'ingrediente',
        'hábito', 'bem-estar', 'experiência'
    ],
}

WORDS_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)
CANDIDATE_RE = re.compile(r'[A-Za-zÀ-ÿ]{2,}')
GROUPS_SET = {g: set(words_list) for g, words_list in GROUPS.items()}


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


def graph(text: str, answer: str = ''):
    """
    Heurística lexical determinística e rápida para alimentar o Three.js.
    Destaca termos do texto de entrada e da resposta gerada, organizando conexões por
    grupos conceituais e sequências de frases sem sobrecarregar a CPU.
    """
    source = [w for w in words(text) if w not in STOP and len(w) > 2]
    reply = [w for w in words(answer) if w not in STOP and len(w) > 3]

    # Ampla cobertura de termos da resposta para enriquecer a exploração visual
    keys = list(dict.fromkeys(source + reply))[-110:]
    active = [g for g, vocab_set in GROUPS_SET.items() if any(w in vocab_set for w in source + reply)]

    expanded = []
    for g in active:
        expanded.extend([(w, g) for w in GROUPS[g][:10] if w not in keys])

    nodes = []
    for w in keys:
        g = next((g for g, vocab_set in GROUPS_SET.items() if w in vocab_set), 'contexto')
        if w in source:
            weight = min(1.0, 0.50 + 0.12 * source.count(w))
            origin = 'entrada'
        else:
            weight = min(0.95, 0.42 + 0.08 * reply.count(w))
            origin = 'resposta'
        nodes.append(dict(id=w, group=g, weight=round(weight, 2), origin=origin))

    for w, g in expanded[:50]:
        nodes.append(dict(id=w, group=g, weight=0.25, origin='vocabulário demonstrativo'))

    edges = []
    # Conexões por proximidade de grupo conceitual
    for i, node in enumerate(nodes):
        peers = [n for n in nodes[:i] if n['group'] == node['group']][-4:]
        for peer in peers:
            edges.append(dict(source=peer['id'], target=node['id'], weight=0.5, kind='grupo lexical'))

    # Conexões por sequência natural das frases digitadas
    for a, b in zip(source, source[1:]):
        if a != b and a in keys and b in keys:
            edges.append(dict(source=a, target=b, weight=0.8, kind='sequência no texto'))

    for a, b in zip(reply, reply[1:]):
        if a != b and a in keys and b in keys:
            edges.append(dict(source=a, target=b, weight=0.65, kind='sequência na resposta'))

    return dict(
        nodes=nodes,
        edges=edges,
        groups=list(dict.fromkeys(n['group'] for n in nodes)),
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
    Distribuição rebalanceada: prioriza respostas mais ricas em conceitos e nós (até 140 tokens),
    com tolerância adequada para prompts de estudo.
    """
    text = str(data.get('text', ''))[:4000]
    mode = 'demo' if data.get('mode') == 'demo' else 'local'

    def event(name, **payload) -> str:
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def stream():
        if not text.strip():
            yield event('done', answer='', graph=graph(''), candidates=[])
            return

        started = time.perf_counter()

        if mode == 'demo':
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

            yield event(
                'done',
                answer=answer,
                graph=graph(text, answer),
                candidates=[],
                text_tokens=None,
                words_s=None
            )
            return

        answer = ''
        latest_candidates = []
        output_tokens = 0
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

            if prompt_count > 1000:
                yield event(
                    'error',
                    message='Texto muito longo para este protótipo. Mantenha a pergunta em até 1.000 tokens.'
                )
                return

            # Limite de tokens de saída balanceado: 140 tokens (rico em nós para o 3D)
            payload = dict(
                model='local',
                messages=messages,
                stream=True,
                max_tokens=140,
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
                        if fragment:
                            answer += fragment
                            yield event('chunk', text=fragment, candidates=latest_candidates)

            elapsed = max(0.01, time.perf_counter() - started)
            yield event(
                'done',
                answer=answer,
                graph=graph(text, answer),
                candidates=latest_candidates,
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
