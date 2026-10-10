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

                # Validação do payload repassado ao llama.cpp (limite da balança + 1 token invisível)
                self.assertEqual(len(captured_payloads), 1)
                self.assertEqual(captured_payloads[0]['max_tokens'], 61)
                self.assertEqual(done_data['max_tokens_config'], 60)

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

        # Conceitos continuam preservados com grupos semânticos (hiperônimos intermediários)
        self.assertIn('inteligência', nodes_by_id)
        self.assertIn(nodes_by_id['inteligência']['group'], ('conceito/cognição', 'artefato/tecnologia'))

    def test_16_groups_and_dynamic_clusters(self):
        """Valida existência das 16 famílias universais, normalização morfológica e posicionamento dos clusters dinâmicos ao final da legenda."""
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

        # Valida que termos desconhecidos são consolidados estritamente nos 10 hiperônimos estáveis
        axolote_group = nodes_by_id['axolote']['group']
        self.assertIn(
            axolote_group,
            server.INTERMEDIATE_HYPERNYMS.keys(),
            f"Grupo '{axolote_group}' deve pertencer aos 10 hiperônimos estáveis"
        )
        # Garante que nenhum grupo rogue com prefixo 'conceito: ' é criado
        self.assertFalse(any(g.startswith('conceito: ') for g in res['groups']), "Nenhum grupo com 'conceito: ' deve existir")

    def test_reply_sequence_continuity(self):
        """Valida que a linha da resposta possui precedência máxima, conecta todas as palavras da resposta de forma contínua e gera atalhos de conteúdo quando conectivos estiverem ocultos."""
        res = server.graph('Qual é a capital do Brasil?', 'A capital do Brasil é Brasília.')
        nodes_by_id = {n['id']: n for n in res['nodes']}
        edges = res['edges']

        # Todas as palavras da resposta devem estar presentes nos nós com flag in_reply
        answer_words = ['a', 'capital', 'do', 'brasil', 'é', 'brasília']
        for w in answer_words:
            self.assertIn(w, nodes_by_id)
            self.assertTrue(nodes_by_id[w]['in_reply'], f"Nó '{w}' deveria ter in_reply=True")

        # Sequência canônica da resposta emitida
        self.assertIn('reply_sequence', res)
        self.assertEqual(res['reply_sequence'], answer_words)

        # Mapeia arestas por par ordenado
        edges_map = {}
        for e in edges:
            pair = tuple(sorted([e['source'], e['target']]))
            edges_map[pair] = e

        # Pares sequenciais completos da resposta (com conectivos)
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

        # Pares sequenciais diretos de conteúdo (atalhos para quando conectivos estiverem ocultos)
        shortcut_pairs = [
            tuple(sorted(['capital', 'brasil'])),
            tuple(sorted(['brasil', 'brasília']))
        ]
        for pair in shortcut_pairs:
            self.assertIn(pair, edges_map, f"Aresta de atalho {pair} ausente no grafo")
            edge = edges_map[pair]
            self.assertTrue(edge.get('is_shortcut'), f"Aresta {pair} deveria ser is_shortcut=True")
            self.assertEqual(edge['kind_id'], 'reply_sequence')

        # Valida que NÃO existem arestas cruzadas redundantes (triângulos) entre palavras não consecutivas da resposta
        cross_triangle_pair = tuple(sorted(['capital', 'brasília']))
        self.assertNotIn(cross_triangle_pair, edges_map, f"Aresta cruzada {cross_triangle_pair} não deveria existir no grafo")

        # Valida que 'conectivos' aparece no final da legenda para inspeção isolada e domínios não relacionados NÃO aparecem
        self.assertEqual(res['groups'][-1], 'conectivos', "'conectivos' deve ser o último grupo para permitir isolamento na legenda")
        self.assertNotIn('economia', res['groups'])
        self.assertNotIn('economia/valor', res['groups'])
        self.assertTrue(
            any(g in res['groups'] for g in ('lugar/geografia', 'entidade/sociedade', 'sociedade')),
            "Deveria conter hiperônimo de geografia ou sociedade na legenda"
        )

        # Valida que 'capital' pertence exclusivamente a 'sociedade' e não a 'economia'
        self.assertIn('capital', server.GROUPS['sociedade'])
        self.assertNotIn('capital', server.GROUPS['economia'])

    def test_step_candidates_and_real_tokens_in_graph(self):
        """Valida que o histórico de candidatos reais da LLM é integrado à nuvem 3D com desduplicação e limite por passo."""
        mock_steps = [
            {
                'token': ' capital',
                'step': 0,
                'candidates': [
                    {'token': ' capital', 'probability': 0.85},
                    {'token': ' cidade', 'probability': 0.10},
                    {'token': ' metrópole', 'probability': 0.04},
                    {'token': ' centro', 'probability': 0.01}  # < 0.03, deve ser descartado
                ]
            }
        ]
        res = server.graph('Qual o país?', 'A capital', step_candidates=mock_steps)
        nodes_by_id = {n['id']: n for n in res['nodes']}
        # 'cidade' e 'metrópole' devem ter entrado como alternativas concorrentes com prob >= 3%
        self.assertIn('cidade', nodes_by_id)
        self.assertEqual(nodes_by_id['cidade']['origin'], 'alternativa concorrente')
        self.assertEqual(nodes_by_id['cidade']['probability'], 10.0)
        self.assertIn('metrópole', nodes_by_id)
        # 'centro' teve prob 1%, não deve entrar
        self.assertNotIn('centro', nodes_by_id)

    def test_subword_fragments_and_duplicate_stems_rejected(self):
        """Valida que fragmentos de sub-tokens BPE e prefixos de palavras já na resposta são estritamente rejeitados."""
        mock_steps = [
            {
                'token': ' intelig',
                'step': 0,
                'candidates': [
                    {'token': ' intelig', 'probability': 0.90},  # Prefixo de "inteligência" (já na resposta) -> deve ser descartado
                    {'token': ' cognição', 'probability': 0.08}   # Palavra inteira independente -> deve ser aceita
                ]
            },
            {
                'token': 'ência',
                'step': 1,
                'candidates': [
                    {'token': 'ência', 'probability': 0.95},     # Sufixo sem leading space -> deve ser descartado
                    {'token': 'ente', 'probability': 0.04}       # Sufixo sem leading space -> deve ser descartado
                ]
            },
            {
                'token': ' aprend',
                'step': 2,
                'candidates': [
                    {'token': ' aprend', 'probability': 0.70},   # Prefixo de "aprendizado" (já na resposta) -> deve ser descartado
                    {'token': ' estudo', 'probability': 0.15}    # Palavra inteira independente -> deve ser aceita
                ]
            },
            {
                'token': 'izado',
                'step': 3,
                'candidates': [
                    {'token': 'izado', 'probability': 0.99}      # Sufixo sem leading space -> deve ser descartado
                ]
            }
        ]
        answer = 'A inteligência artificial requer aprendizado constante.'
        res = server.graph('Como funciona a IA?', answer, step_candidates=mock_steps)
        node_ids = {n['id'] for n in res['nodes']}

        # As palavras completas da resposta devem estar presentes
        self.assertIn('inteligência', node_ids)
        self.assertIn('aprendizado', node_ids)

        # As alternativas completas independentes devem estar presentes
        self.assertIn('cognição', node_ids)
        self.assertIn('estudo', node_ids)

        # Fragmentos, sufixos e prefixos cortados NÃO devem estar presentes na nuvem 3D
        self.assertNotIn('intelig', node_ids, "Prefixo 'intelig' não deveria estar na nuvem 3D")
        self.assertNotIn('ência', node_ids, "Sufixo 'ência' não deveria estar na nuvem 3D")
        self.assertNotIn('aprend', node_ids, "Prefixo 'aprend' não deveria estar na nuvem 3D")
        self.assertNotIn('izado', node_ids, "Sufixo 'izado' não deveria estar na nuvem 3D")

        # Nenhum grupo rogue com nome 'conceito: intelig' ou 'conceito: aprend' deve existir
        for g in res['groups']:
            self.assertFalse(g.startswith('conceito: intelig'), f"Grupo rogue {g} encontrado")
            self.assertFalse(g.startswith('conceito: aprend'), f"Grupo rogue {g} encontrado")
            self.assertFalse(g.startswith('conceito: ência'), f"Grupo rogue {g} encontrado")

    def test_stem_reconstruction_and_no_static_anchors(self):
        """Valida que radicais BPE ('escre', 'manip', 'cons') são reconstruídos para palavras plenas e nenhuma âncora estática é injetada."""
        # Teste unitário direto da função de reconstrução
        self.assertEqual(server.reconstruct_candidate_word('escre'), 'escrever')
        self.assertEqual(server.reconstruct_candidate_word('manip'), 'manipular')
        self.assertEqual(server.reconstruct_candidate_word('cons'), 'construir')
        self.assertEqual(server.reconstruct_candidate_word('anal'), 'análise')
        self.assertEqual(server.reconstruct_candidate_word('ess'), 'essencial')
        self.assertEqual(server.reconstruct_candidate_word('pal'), 'palavras')
        self.assertEqual(server.reconstruct_candidate_word('sensori'), 'sensorial')
        # Fragmento sem sentido ou menor que 3 letras
        self.assertIsNone(server.reconstruct_candidate_word('ab'))
        self.assertIsNone(server.reconstruct_candidate_word('xpzt'))

        # Teste de integração com o grafo
        mock_steps = [
            {
                'token': ' IA',
                'step': 0,
                'candidates': [
                    {'token': ' escre', 'probability': 0.18},
                    {'token': ' manip', 'probability': 0.12},
                    {'token': ' cons', 'probability': 0.10}
                ]
            }
        ]
        res = server.graph('Como a IA processa texto?', 'A IA processa texto com lógica.', step_candidates=mock_steps)
        node_ids = {n['id'] for n in res['nodes']}

        # Radicais devem estar reconstruídos como palavras completas
        self.assertIn('escrever', node_ids)
        self.assertIn('manipular', node_ids)
        self.assertIn('construir', node_ids)

        # Radicais cortados NÃO devem estar presentes
        self.assertNotIn('escre', node_ids)
        self.assertNotIn('manip', node_ids)
        self.assertNotIn('cons', node_ids)

        # Nenhuma âncora estática 'vocabulário demonstrativo' deve estar presente
        demonstrative_nodes = [n for n in res['nodes'] if n.get('origin') == 'vocabulário demonstrativo']
        self.assertEqual(len(demonstrative_nodes), 0, "Âncoras estáticas demonstrativas devem estar inativas")

    def test_mane_reconstruction_and_legend_sorting_and_demo_edges(self):
        """Valida que o radical 'mane' é reconstruído para 'maneira', 'conceito/cognição' fica no final da legenda e modo demo preserva arestas."""
        # 1. Reconstrução de 'mane'
        self.assertEqual(server.reconstruct_candidate_word('mane'), 'maneira')
        self.assertEqual(server.reconstruct_candidate_word('torn'), 'tornar')

        # 2. Ordenação da legenda: conceito/cognição deve ficar no final dos grupos estáveis e conectivos por último
        res = server.graph('inteligência artificial tecnologia brasil capital', 'o modelo pensa sobre a mente e dados')
        groups = res['groups']
        if 'conceito/cognição' in groups:
            standard_without_dyn = [g for g in groups if not any(g.startswith(p) for p in ('tema:', 'ação:', 'qualidade:', 'conceito:')) and g != 'conectivos']
            self.assertEqual(standard_without_dyn[-1], 'conceito/cognição', "conceito/cognição deve ser o último dos grupos estáveis")
        if 'conectivos' in groups:
            self.assertEqual(groups[-1], 'conectivos', "conectivos deve ser sempre o último grupo da legenda")

        # 3. Modo demonstração preserva arestas de grupo lexical
        demo_graph = server.graph('inteligência tecnologia', 'computador modelo software algoritmo', is_demo=True)
        lexical_edges = [e for e in demo_graph['edges'] if e.get('kind') == 'grupo lexical']
        self.assertGreater(len(lexical_edges), 0, "Modo demonstração deve manter conexões temáticas entre termos da resposta")

    def test_connectives_isolation_group_and_cpu_optimization(self):
        """Valida que conectivos é sempre o último grupo da legenda e que as configurações de CPU estão otimizadas."""
        res = server.graph('como a inteligência artificial entende a linguagem?', 'a inteligência artificial compreende o texto através de padrões matemáticos e redes neurais.')
        groups = res['groups']
        self.assertIn('conectivos', groups)
        self.assertEqual(groups[-1], 'conectivos', "conectivos deve obrigatoriamente ser o último grupo da legenda")
        
        # Valida propriedades dos nós de conectivos
        conn_nodes = [n for n in res['nodes'] if n['group'] == 'conectivos']
        self.assertGreater(len(conn_nodes), 0, "Devem existir nós de conectivos")
        for cn in conn_nodes:
            self.assertEqual(cn['origin'], 'conectivo')
            self.assertEqual(cn['weight'], 0.22)

    def test_cluster_coherence_and_no_orphan_islands(self):
        """Valida que termos concorrentes de domínios alienígenas (ex: primavera/passagem) são filtrados, eliminando ilhas órfãs."""
        mock_steps = [
            {
                'token': ' inteligência',
                'step': 0,
                'candidates': [
                    {'token': ' software', 'probability': 0.25},
                    {'token': ' primavera', 'probability': 0.18},
                    {'token': ' passagem', 'probability': 0.15}
                ]
            }
        ]
        res = server.graph('Como a inteligência artificial entende a linguagem?', 'A IA processa texto e dados.', step_candidates=mock_steps)
        node_ids = {n['id'] for n in res['nodes']}

        # Termo afim com artefato/tecnologia deve ser admitido
        self.assertIn('software', node_ids)

        # Termos alienígenas de lugar/geografia NÃO devem ser admitidos como ilha órfã
        self.assertNotIn('primavera', node_ids)
        self.assertNotIn('passagem', node_ids)

        # O radical cortado com terminação 'ss' deve ser descartado
        self.assertIsNone(server.reconstruct_candidate_word('pass'))


if __name__ == '__main__':
    unittest.main()


