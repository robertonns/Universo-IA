"""Universo Local: all inference stays on loopback. No API key or cloud calls."""
import asyncio
import json
import math
import os
import re
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

ROOT = Path(__file__).parent
LLAMA = 'http://127.0.0.1:8081'
app = FastAPI()
INFERENCE_LOCK = asyncio.Lock()
STOP = set('a o as os um uma de do da dos das em no na nos nas e ou que para por com como se eu você voce quero qual quais sobre é são ao me meu minha isso esse essa'.split())
GROUPS = {
    'tecnologia': ['inteligência', 'artificial', 'modelo', 'token', 'tokens', 'rede', 'neural', 'dados', 'algoritmo', 'computador', 'ia', 'llm', 'código', 'software', 'aprendizado', 'máquina', 'treinamento', 'padrão', 'probabilidade', 'informação'],
    'linguagem': ['linguagem', 'palavra', 'palavras', 'texto', 'leitura', 'escrita', 'fala', 'significado', 'contexto', 'português', 'inglês', 'comunicação', 'semântica', 'frase', 'pergunta', 'resposta', 'interpretação', 'vocabulário', 'gramática', 'sentido'],
    'ciência': ['ciência', 'cérebro', 'memória', 'neurônio', 'energia', 'universo', 'física', 'pesquisa', 'hipótese', 'atenção', 'aprendizagem', 'conhecimento', 'processo', 'análise', 'raciocínio', 'resultado'],
    'viagem': ['viagem', 'viajar', 'japão', 'primavera', 'cerejeiras', 'roteiro', 'cultura', 'cidade', 'clima', 'tóquio', 'paris', 'hotel', 'passagem', 'destino', 'turismo'],
    'cotidiano': ['trabalho', 'vida', 'pessoa', 'pessoas', 'tempo', 'dia', 'casa', 'saúde', 'alimentação', 'sono', 'rotina', 'família', 'receita', 'bolo', 'chocolate', 'cozinha', 'ingrediente'],
}


def words(text):
    return re.findall(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", text.lower(), re.UNICODE)


def readable_candidates(items):
    """Keep only token alternatives that look like readable word fragments."""
    clean = []
    seen = set()
    for item in items:
        token = str(item.get('token', '')).strip()
        if not re.search(r'[A-Za-zÀ-ÿ]{2,}', token) or token in seen:
            continue
        seen.add(token)
        clean.append(dict(token=token, probability=math.exp(item['logprob'])))
    return clean


def graph(text, answer=''):
    """Transparent lexical heuristic, NOT an embedding or a model activation."""
    source = [w for w in words(text) if w not in STOP and len(w) > 2]
    reply = [w for w in words(answer) if w not in STOP and len(w) > 3]
    keys = list(dict.fromkeys(source + reply))[-70:]
    active = [g for g, vocabulary in GROUPS.items() if any(w in vocabulary for w in source + reply)]
    expanded = []
    for g in active:
        expanded.extend([(w, g) for w in GROUPS[g][:8] if w not in keys])
    nodes = []
    for w in keys:
        g = next((g for g, vocabulary in GROUPS.items() if w in vocabulary), 'contexto')
        nodes.append(dict(id=w, group=g, weight=min(1, .50 + .12*source.count(w)) if w in source else .38,
                          origin='entrada' if w in source else 'resposta'))
    for w, g in expanded[:48]:
        nodes.append(dict(id=w, group=g, weight=.25, origin='vocabulário demonstrativo'))
    edges = []
    for i, node in enumerate(nodes):
        peers = [n for n in nodes[:i] if n['group'] == node['group']][-4:]
        for peer in peers:
            edges.append(dict(source=peer['id'], target=node['id'], weight=.5, kind='grupo lexical'))
    for a, b in zip(source, source[1:]):
        if a != b and a in keys and b in keys:
            edges.append(dict(source=a, target=b, weight=.8, kind='sequência no texto'))
    for a, b in zip(reply, reply[1:]):
        if a != b and a in keys and b in keys:
            edges.append(dict(source=a, target=b, weight=.65, kind='sequência na resposta'))
    return dict(nodes=nodes, edges=edges, groups=list(dict.fromkeys(n['group'] for n in nodes)),
                method='Heurística lexical: grupos explícitos e sequência no texto; sem embeddings.')


@app.get('/api/status')
async def status():
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(LLAMA + '/health')
            response.raise_for_status()
        return {'ready': True, 'engine': 'llama.cpp · CPU', 'model': 'Qwen2.5-0.5B-Instruct Q4_K_M'}
    except (httpx.HTTPError, ValueError):
        return {'ready': False, 'engine': 'llama.cpp · CPU', 'model': 'não conectado'}


@app.post('/api/graph')
async def api_graph(data: dict):
    """Small, immediate request used by the browser while the CPU generates."""
    text = str(data.get('text', ''))[:4000]
    return {'graph': graph(text), 'words': len(words(text))}


@app.post('/api/generate')
async def api_generate(data: dict):
    """Stream updates through ordinary HTTP; avoids browser WebSocket instability."""
    text = str(data.get('text', ''))[:4000]
    mode = 'demo' if data.get('mode') == 'demo' else 'local'
    async def event(name, **payload):
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def stream():
        if not text.strip():
            yield await event('done', answer='', graph=graph(''), candidates=[])
            return
        started = time.perf_counter()
        if mode == 'demo':
            terms = [n['id'] for n in graph(text)['nodes'] if n['origin'] == 'entrada']
            answer = ('Demonstração visual, sem modelo: o texto destaca ' + ', '.join(terms[:5]) +
                      '. Ao continuar escrevendo, os termos e as conexões serão reorganizados.')
            for fragment in re.findall(r'\S+\s*', answer):
                yield await event('chunk', text=fragment, candidates=[])
                await asyncio.sleep(.025)
            yield await event('done', answer=answer, graph=graph(text, answer), candidates=[], text_tokens=None, words_s=None)
            return
        answer = ''
        latest_candidates = []
        output_tokens = 0
        try:
            system = ('Responda em português, de modo breve e direto, em até duas frases. '
                      'O usuário ainda está escrevendo; responda apenas ao que já está claro. '
                      'Se faltar informação, faça uma pergunta curta. Não invente fatos.')
            messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': text}]
            async with INFERENCE_LOCK, httpx.AsyncClient(timeout=httpx.Timeout(120, connect=3)) as client:
                count_response = await client.post(LLAMA + '/tokenize', json={'content': text})
                count_response.raise_for_status()
                text_tokens = len(count_response.json().get('tokens', []))
                payload = dict(model='local', messages=messages, stream=True, max_tokens=48,
                               temperature=.7, top_p=1, top_k=0, logprobs=True, top_logprobs=50)
                async with client.stream('POST', LLAMA + '/v1/chat/completions', json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data: '):
                            continue
                        raw = line[6:]
                        if raw == '[DONE]':
                            break
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
                            yield await event('chunk', text=fragment, candidates=latest_candidates)
            elapsed = max(.01, time.perf_counter() - started)
            yield await event('done', answer=answer, graph=graph(text, answer), candidates=latest_candidates,
                              text_tokens=text_tokens, output_tokens=output_tokens,
                              words_s=round(len(words(answer)) / elapsed, 1) if answer else None)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            yield await event('error', message='Modelo local indisponível ou incompatível. ' + str(exc)[:350])

    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})


@app.websocket('/ws')
async def websocket(ws: WebSocket):
    # Restrict browser access to this local application's origins.
    origin = ws.headers.get('origin', '')
    if origin and origin not in {'http://127.0.0.1:8765', 'http://localhost:8765'}:
        await ws.close(code=1008)
        return
    await ws.accept()
    latest = {'data': None}
    wake = asyncio.Event()
    send_lock = asyncio.Lock()

    async def send(event, **data):
        async with send_lock:
            await ws.send_json({'event': event, **data})

    async def receive():
        while True:
            data = await ws.receive_json()
            if not isinstance(data, dict) or not isinstance(data.get('text'), str):
                continue
            text = data['text'][:4000]
            version = int(data.get('version', 0))
            data = dict(text=text, version=version, mode='demo' if data.get('mode') == 'demo' else 'local')
            latest['data'] = data
            wake.set()
            await send('graph', version=version, graph=graph(text), words=len(words(text)))

    async def worker():
        while True:
            await wake.wait()
            wake.clear()
            data = latest['data']
            text, version, mode = data['text'], data['version'], data['mode']
            if not text.strip():
                await send('clear', version=version)
                continue
            await send('start', version=version, mode=mode)
            started = time.perf_counter()
            answer = ''
            count = 0
            first = None
            try:
                if mode == 'demo':
                    terms = [n['id'] for n in graph(text)['nodes'] if n['origin'] == 'entrada']
                    preview = ('Demonstração visual, sem modelo: o texto destaca ' + ', '.join(terms[:5]) +
                               '. Ao continuar escrevendo, os termos e as conexões deste exemplo serão reorganizados. Ative o modo local para obter uma resposta gerada pela IA.')
                    for token in preview.split(' '):
                        await asyncio.sleep(.035)
                        answer += token + ' '
                        count += 1
                        await send('chunk', version=version, text=token+' ', candidates=[], ttft_ms=None, output_tokens=None)
                        if count >= 12 and latest['data']['version'] != version:
                            break
                    await send('done', version=version, graph=graph(text, answer), elapsed_ms=round((time.perf_counter()-started)*1000), output_tokens=None, tokens_s=None, input_tokens=None)
                    continue

                async with INFERENCE_LOCK, httpx.AsyncClient(timeout=httpx.Timeout(120, connect=3)) as client:
                    system = 'Responda em português, de modo breve e direto, em até duas frases. O usuário ainda está escrevendo; responda apenas ao que já está claro. Se faltar informação, faça uma pergunta curta. Não invente fatos.'
                    messages = [{'role':'system','content':system}, {'role':'user','content':text}]
                    # Count the actual rendered prompt before inference and reject oversize input.
                    template = await client.post(LLAMA+'/apply-template', json={'messages':messages, 'add_generation_prompt':True})
                    template.raise_for_status()
                    rendered = template.json()['prompt']
                    tokenized = await client.post(LLAMA+'/tokenize', json={'content':rendered, 'add_special':True, 'parse_special':True})
                    tokenized.raise_for_status()
                    prompt_count = len(tokenized.json()['tokens'])
                    if prompt_count > 1850:
                        raise ValueError('Texto longo para este protótipo. Reduza o texto para caber no contexto de 2.048 tokens.')
                    payload = dict(model='local', messages=messages, stream=True, max_tokens=60,
                                   temperature=.7, top_p=1, top_k=0, logprobs=True, top_logprobs=8,
                                   stream_options={'include_usage':True}, cache_prompt=True)
                    usage = {}
                    await send('prompt', version=version, input_tokens=prompt_count)
                    async with client.stream('POST', LLAMA+'/v1/chat/completions', json=payload) as response:
                        if response.status_code != 200:
                            detail = (await response.aread()).decode(errors='replace')[:350]
                            raise ValueError('O servidor recusou a geração: '+detail)
                        async for line in response.aiter_lines():
                            if not line.startswith('data: '):
                                continue
                            raw = line[6:]
                            if raw == '[DONE]':
                                break
                            event = json.loads(raw)
                            usage = event.get('usage') or usage
                            choices = event.get('choices') or []
                            if not choices:
                                continue
                            choice = choices[0]
                            fragment = choice.get('delta', {}).get('content') or ''
                            logs = (choice.get('logprobs') or {}).get('content') or []
                            count += len(logs)
                            if fragment:
                                answer += fragment
                                if first is None:
                                    first = time.perf_counter()
                                candidates = []
                                if logs:
                                    candidates = [dict(token=c['token'], probability=math.exp(c['logprob']))
                                                  for c in logs[-1].get('top_logprobs', [])]
                                await send('chunk', version=version, text=fragment, candidates=candidates,
                                           ttft_ms=round((first-started)*1000), output_tokens=count if logs else None)
                            # Minimum visible output prevents starvation while the user types.
                            if latest['data']['version'] != version and (count >= 12 or (answer and time.perf_counter()-started > 3)):
                                break
                    elapsed = time.perf_counter()-started
                    total = usage.get('completion_tokens', count) or None
                    await send('done', version=version, graph=graph(text, answer), elapsed_ms=round(elapsed*1000),
                               output_tokens=total, input_tokens=usage.get('prompt_tokens', prompt_count),
                               tokens_s=round((max(0,total-1))/(time.perf_counter()-first), 1) if total and first and time.perf_counter()-first > .01 else None)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                await send('error', version=version, message='Modelo local indisponível ou incompatível. Execute INICIAR_MODELO.bat. '+str(exc)[:400])

    tasks = [asyncio.create_task(receive()), asyncio.create_task(worker())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app.mount('/', StaticFiles(directory=ROOT/'static', html=True), name='static')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning')
