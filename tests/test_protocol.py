"""Protocol tests use deterministic HTTP fixtures, not actual model inference."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
import server


def reply(request):
    path=request.url.path
    if path=='/apply-template':return httpx.Response(200,json={'prompt':'rendered prompt'})
    if path=='/tokenize':return httpx.Response(200,json={'tokens':list(range(25))})
    if path=='/v1/chat/completions':
        content=[]
        for token in ['Uma ', 'resposta ', 'curta.']:
            event={'choices':[{'delta':{'content':token},'logprobs':{'content':[{'token':token,'logprob':-.5,'top_logprobs':[{'token':token,'logprob':-.5}]}]}}]}
            content.append('data: '+json.dumps(event)+'\n\n')
        content.append('data: '+json.dumps({'choices':[],'usage':{'prompt_tokens':25,'completion_tokens':3}})+'\n\ndata: [DONE]\n\n')
        return httpx.Response(200,text=''.join(content))
    return httpx.Response(200,json={'status':'ok'})


class ProtocolTests(unittest.TestCase):
    def test_real_mode_stream_and_probabilities(self):
        original=httpx.AsyncClient
        def client(**kwargs):return original(transport=httpx.MockTransport(reply),**kwargs)
        with patch.object(server.httpx,'AsyncClient',client), TestClient(server.app) as app:
            with app.websocket_connect('/ws') as ws:
                ws.send_json({'text':'Como funciona a linguagem?','version':1,'mode':'local'})
                events=[]
                while True:
                    event=ws.receive_json();events.append(event)
                    if event['event'] in ('done','error'):break
                self.assertEqual(events[-1]['event'],'done',events)
                self.assertEqual(events[-1]['input_tokens'],25)
                chunks=[e for e in events if e['event']=='chunk']
                self.assertEqual(''.join(c['text'] for c in chunks),'Uma resposta curta.')
                self.assertAlmostEqual(chunks[0]['candidates'][0]['probability'],.60653066)

    def test_latest_version_wins_in_demo(self):
        with TestClient(server.app) as app:
            with app.websocket_connect('/ws') as ws:
                ws.send_json({'text':'inteligência artificial','version':1,'mode':'demo'})
                while ws.receive_json()['event']!='chunk':pass
                ws.send_json({'text':'viagem','version':2,'mode':'demo'})
                ws.send_json({'text':'viagem para o Japão','version':3,'mode':'demo'})
                for _ in range(180):
                    e=ws.receive_json()
                    if e['event']=='chunk':self.assertEqual(e['candidates'],[])
                    if e['event']=='done' and e['version']==3:break
                else:self.fail('Latest version did not finish')

    def test_unavailable_model_is_explicit(self):
        original=httpx.AsyncClient
        def fail(request):raise httpx.ConnectError('offline',request=request)
        def client(**kwargs):return original(transport=httpx.MockTransport(fail),**kwargs)
        with patch.object(server.httpx,'AsyncClient',client), TestClient(server.app) as app:
            with app.websocket_connect('/ws') as ws:
                ws.send_json({'text':'teste','version':7,'mode':'local'})
                for _ in range(10):
                    e=ws.receive_json()
                    if e['event']=='error':break
                self.assertEqual(e['event'],'error')
                self.assertIn('INICIAR_MODELO',e['message'])

    def test_external_origin_rejected(self):
        with TestClient(server.app) as app:
            from starlette.websockets import WebSocketDisconnect
            with self.assertRaises(WebSocketDisconnect):
                with app.websocket_connect('/ws',headers={'origin':'https://example.com'}):pass


if __name__=='__main__':unittest.main()
