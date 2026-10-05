"""
Testes automatizados da API do Universo Local.
Utiliza fixtures determinísticas e simulação HTTP (MockTransport) sem depender de GPU ou execução real de modelo.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi.testclient import TestClient
import server

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


def parse_sse_events(lines):
    """Auxiliar para converter linhas brutas de SSE em lista de eventos estruturados."""
    events = []
    current_event = None
    for line in lines:
        if line.startswith('event: '):
            current_event = line[7:].strip()
        elif line.startswith('data: ') and current_event:
            data = json.loads(line[6:].strip())
            events.append((current_event, data))
            current_event = None
    return events


def mock_llama_reply(request: httpx.Request):
    """Simulador do servidor llama.cpp na porta 8081."""
    path = request.url.path
    if path == '/health':
        return httpx.Response(200, json={'status': 'ok'})
    if path == '/apply-template':
        return httpx.Response(200, json={'prompt': 'rendered chat prompt'})
    if path == '/tokenize':
        return httpx.Response(200, json={'tokens': list(range(20))})
    if path == '/v1/chat/completions':
        content = []
        tokens = ['A ', 'linguagem ', 'conecta ', 'ideias.']
        for token in tokens:
            event = {
                'choices': [{
                    'delta': {'content': token},
                    'logprobs': {
                        'content': [{
                            'token': token,
                            'logprob': -0.4,
                            'top_logprobs': [{'token': token, 'logprob': -0.4}]
                        }]
                    }
                }]
            }
            content.append('data: ' + json.dumps(event) + '\n\n')
        content.append('data: [DONE]\n\n')
        return httpx.Response(200, text=''.join(content))
    return httpx.Response(404)


class ProtocolTests(unittest.TestCase):

    def test_status_endpoint_ready(self):
        """Verifica /api/status quando o modelo local responde."""
        def client_factory(*args, **kwargs):
            kwargs['transport'] = httpx.MockTransport(mock_llama_reply)
            return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

        with patch.object(server.httpx, 'AsyncClient', client_factory), TestClient(server.app) as client:
            resp = client.get('/api/status')
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data['ready'])
            self.assertIn('llama.cpp', data['engine'])

    def test_status_endpoint_offline(self):
        """Verifica /api/status quando o modelo local está desconectado."""
        def handler(req):
            raise httpx.ConnectError('offline', request=req)

        def client_factory(*args, **kwargs):
            kwargs['transport'] = httpx.MockTransport(handler)
            return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

        with patch.object(server.httpx, 'AsyncClient', client_factory), TestClient(server.app) as client:
            resp = client.get('/api/status')
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertFalse(data['ready'])
            self.assertEqual(data['model'], 'não conectado')

    def test_graph_endpoint(self):
        """Valida a heurística determinística de nós e arestas."""
        with TestClient(server.app) as client:
            resp = client.post('/api/graph', json={'text': 'inteligência artificial e redes neurais'})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn('graph', data)
            self.assertIn('words', data)
            nodes = data['graph']['nodes']
            node_ids = [n['id'] for n in nodes]
            self.assertIn('inteligência', node_ids)
            self.assertIn('artificial', node_ids)

    def test_generate_stream_local_mode(self):
        """Valida o streaming SSE em modo local com chunks, candidatos e finalização."""
        def client_factory(*args, **kwargs):
            kwargs['transport'] = httpx.MockTransport(mock_llama_reply)
            return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

        with patch.object(server.httpx, 'AsyncClient', client_factory), TestClient(server.app) as client:
            with client.stream('POST', '/api/generate', json={'text': 'Como funciona a linguagem?', 'mode': 'local'}) as resp:
                self.assertEqual(resp.status_code, 200)
                lines = [line for line in resp.iter_lines() if line]
                events = parse_sse_events(lines)

                chunk_events = [e for e in events if e[0] == 'chunk']
                done_events = [e for e in events if e[0] == 'done']

                self.assertTrue(len(chunk_events) > 0)
                self.assertEqual(len(done_events), 1)

                full_answer = ''.join(c[1]['text'] for c in chunk_events)
                self.assertEqual(full_answer, 'A linguagem conecta ideias.')

                done_data = done_events[0][1]
                self.assertEqual(done_data['answer'], 'A linguagem conecta ideias.')
                self.assertIn('nodes', done_data['graph'])
                self.assertIn('edges', done_data['graph'])
                self.assertEqual(done_data['output_tokens'], 4)

    def test_generate_stream_demo_mode(self):
        """Valida o streaming em modo demonstração (não requer modelo conectado)."""
        with TestClient(server.app) as client:
            with client.stream('POST', '/api/generate', json={'text': 'viagem para o Japão', 'mode': 'demo'}) as resp:
                self.assertEqual(resp.status_code, 200)
                lines = [line for line in resp.iter_lines() if line]
                events = parse_sse_events(lines)

                chunk_events = [e for e in events if e[0] == 'chunk']
                done_events = [e for e in events if e[0] == 'done']

                self.assertTrue(len(chunk_events) > 0)
                self.assertEqual(len(done_events), 1)
                self.assertIn('Demonstração visual', done_events[0][1]['answer'])

    def test_model_unavailable_handles_gracefully(self):
        """Valida se erro de conexão com o modelo emite evento SSE de erro informativo."""
        def handler(req):
            raise httpx.ConnectError('offline', request=req)

        def client_factory(*args, **kwargs):
            kwargs['transport'] = httpx.MockTransport(handler)
            return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

        with patch.object(server.httpx, 'AsyncClient', client_factory), TestClient(server.app) as client:
            with client.stream('POST', '/api/generate', json={'text': 'teste', 'mode': 'local'}) as resp:
                lines = [line for line in resp.iter_lines() if line]
                events = parse_sse_events(lines)
                error_events = [e for e in events if e[0] == 'error']
                self.assertEqual(len(error_events), 1)
                self.assertIn('indisponível', error_events[0][1]['message'])


    def test_balanca_tokens_limit_exceeded(self):
        """Valida que texto excedendo max_prompt_tokens emite evento SSE de erro formatado."""
        def client_factory(*args, **kwargs):
            kwargs['transport'] = httpx.MockTransport(mock_llama_reply)
            return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

        with patch.object(server.httpx, 'AsyncClient', client_factory), TestClient(server.app) as client:
            # mock_llama_reply retorna 20 tokens no /tokenize. Com max_prompt_tokens=15, deve estourar.
            payload = {'text': 'Pergunta teste', 'mode': 'local', 'max_prompt_tokens': 15}
            with client.stream('POST', '/api/generate', json=payload) as resp:
                lines = [line for line in resp.iter_lines() if line]
                events = parse_sse_events(lines)
                error_events = [e for e in events if e[0] == 'error']
                self.assertEqual(len(error_events), 1)
                self.assertIn('Texto excede o limite configurado de 15 tokens', error_events[0][1]['message'])
                self.assertIn('Ajuste na balança ou reduza a pergunta', error_events[0][1]['message'])

    def test_balanca_tokens_custom_preset_and_telemetry(self):
        """Valida que max_tokens dinâmico é aceito e telemetria (ttft_ms, max_tokens_config) é emitida."""
        captured_payloads = []

        def tracking_mock_llama_reply(request: httpx.Request):
            if request.url.path == '/v1/chat/completions':
                captured_payloads.append(json.loads(request.read()))
            return mock_llama_reply(request)

        def client_factory(*args, **kwargs):
            kwargs['transport'] = httpx.MockTransport(tracking_mock_llama_reply)
            return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)

        with patch.object(server.httpx, 'AsyncClient', client_factory), TestClient(server.app) as client:
            payload = {'text': 'Explique redes neurais', 'mode': 'local', 'max_tokens': 60, 'max_prompt_tokens': 400}
            with client.stream('POST', '/api/generate', json=payload) as resp:
                lines = [line for line in resp.iter_lines() if line]
                events = parse_sse_events(lines)
                done_events = [e for e in events if e[0] == 'done']
                self.assertEqual(len(done_events), 1)
                done_data = done_events[0][1]

                # Telemetria no evento done
                self.assertEqual(done_data['max_tokens_config'], 60)
                self.assertIsNotNone(done_data['ttft_ms'])
                self.assertGreaterEqual(done_data['ttft_ms'], 0)
                self.assertEqual(done_data['output_tokens'], 4)
                self.assertEqual(done_data['text_tokens'], 20)
                self.assertIsNotNone(done_data['words_s'])

                # Validação do payload repassado ao llama.cpp
                self.assertEqual(len(captured_payloads), 1)
                self.assertEqual(captured_payloads[0]['max_tokens'], 60)

    def test_connectives_in_graph(self):
        """Valida que conectivos não são descartados e recebem atributos visuais adequados."""
        res = server.graph('A inteligência artificial e as redes neurais sobre o cérebro')
        nodes_by_id = {n['id']: n for n in res['nodes']}

        # Conectivos presentes na frase
        for conn in ['e', 'sobre']:
            self.assertIn(conn, nodes_by_id)
            self.assertEqual(nodes_by_id[conn]['group'], 'conectivos')
            self.assertEqual(nodes_by_id[conn]['weight'], 0.22)
            self.assertEqual(nodes_by_id[conn]['origin'], 'conectivo')

        # Conceitos continuam preservados com grupos semânticos
        self.assertIn('inteligência', nodes_by_id)
        self.assertEqual(nodes_by_id['inteligência']['group'], 'tecnologia')

    def test_16_groups_and_dynamic_clusters(self):
        """Valida existência das 16 famílias universais e formação de cluster dinâmico para termos desconhecidos."""
        expected_families = [
            'tecnologia', 'linguagem', 'ciência', 'mente', 'natureza',
            'sociedade', 'economia', 'filosofia', 'arte', 'saúde',
            'viagem', 'cotidiano', 'esporte', 'direito', 'espaço', 'comunicação'
        ]
        for family in expected_families:
            self.assertIn(family, server.GROUPS)
        self.assertEqual(len(server.GROUPS), 16)

        # Termos desconhecidos que coocorrem na mesma oração
        res = server.graph('O axolote mexicano habita lagos peculiares.')
        nodes_by_id = {n['id']: n for n in res['nodes']}

        self.assertIn('axolote', nodes_by_id)
        self.assertIn('mexicano', nodes_by_id)

    def test_reply_sequence_continuity(self):
        """Valida que a linha da resposta possui precedência máxima e conecta todas as palavras da resposta de forma contínua."""
        res = server.graph('Qual é a capital do Brasil?', 'A capital do Brasil é Brasília.')
        nodes_by_id = {n['id']: n for n in res['nodes']}
        edges = res['edges']

        # Todas as palavras da resposta devem estar presentes nos nós
        answer_words = ['a', 'capital', 'do', 'brasil', 'é', 'brasília']
        for w in answer_words:
            self.assertIn(w, nodes_by_id)

        # Mapeia arestas por par ordenado
        edges_map = {}
        for e in edges:
            pair = tuple(sorted([e['source'], e['target']]))
            edges_map[pair] = e

        # Pares sequenciais da resposta
        expected_reply_pairs = [
            tuple(sorted(['a', 'capital'])),
            tuple(sorted(['capital', 'do'])),
            tuple(sorted(['do', 'brasil'])),
            tuple(sorted(['brasil', 'é'])),
            tuple(sorted(['é', 'brasília'])),
        ]

        for pair in expected_reply_pairs:
            self.assertIn(pair, edges_map, f"Aresta esperada {pair} ausente no grafo")
            edge = edges_map[pair]
            self.assertEqual(edge['kind'], 'sequência na resposta')
            self.assertEqual(edge['kind_id'], 'reply_sequence')


if __name__ == '__main__':
    unittest.main()

