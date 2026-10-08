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


@app.middleware('http')
async def add_no_cache_headers(request, call_next):
    """Garante que arquivos estáticos e respostas nunca fiquem retidos no cache do navegador."""
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


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
        'finanças', 'capitalismo', 'comércio', 'empresa', 'produção', 'consumo', 'crédito',
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

# Ontologia Semântica Estruturada: Hiperônimos de Nível Intermediário
# Mapeia conceitos específicos para ~10 a 12 grandes pilares estáveis, reduzindo fragmentação da legenda
INTERMEDIATE_HYPERNYMS = {
    'lugar/geografia': {
        'brasil', 'brasília', 'país', 'cidade', 'capital', 'estado', 'nação', 'terra', 'planeta',
        'região', 'distrito', 'federal', 'continente', 'território', 'mundo', 'espaço', 'órbita',
        'rio', 'mar', 'oceano', 'floresta', 'planalto', 'metrópole', 'sul', 'norte', 'leste', 'oeste',
        'tóquio', 'paris', 'japão', 'frança', 'hotel', 'destino', 'paisagem'
    },
    'entidade/sociedade': {
        'sociedade', 'comunidade', 'povo', 'humano', 'humanidade', 'cidadão', 'cidadania',
        'população', 'governo', 'democracia', 'civilização', 'público', 'presidente', 'autoridade',
        'ministério', 'instituição', 'empresa', 'indústria', 'coletivo', 'família', 'grupo', 'pessoa',
        'pessoas', 'tribunal', 'juiz', 'advogado', 'paciente'
    },
    'artefato/tecnologia': {
        'computador', 'modelo', 'algoritmo', 'software', 'hardware', 'servidor', 'dispositivo',
        'máquina', 'rede', 'código', 'sistema', 'automação', 'ferramenta', 'veículo', 'instrumento',
        'computação', 'digital', 'telescópio', 'satélite', 'foguete'
    },
    'processo/ação': {
        'processamento', 'aprendizado', 'treinamento', 'desenvolvimento', 'construção', 'fundação',
        'movimento', 'transformação', 'criação', 'produção', 'operação', 'transmissão', 'pesquisa',
        'exercício', 'competição', 'partida', 'treino', 'corrida', 'jogo',
        'precisa', 'precisar', 'gerencia', 'gerenciar', 'utiliza', 'utilizar', 'opera', 'operar',
        'interpreta', 'interpretar', 'executa', 'executar', 'construir', 'manipular'
    },
    'propriedade/estado': {
        'complexidade', 'capacidade', 'potencial', 'qualidade', 'dimensão', 'velocidade', 'tamanho',
        'estrutura', 'forma', 'padrão', 'estabilidade', 'condição', 'localizada', 'central', 'maior',
        'vitalidade', 'bem-estar', 'legal', 'jurídico', 'essencial', 'sensorial'
    },
    'conceito/cognição': {
        'mente', 'cérebro', 'pensamento', 'consciência', 'memória', 'neurônio', 'cognição', 'ideia',
        'inteligência', 'raciocínio', 'sabedoria', 'verdade', 'lógica', 'teoria', 'hipótese',
        'compreensão', 'entendimento', 'filosofia', 'ética', 'moral', 'justiça', 'arte', 'beleza',
        'estética', 'harmonia', 'música', 'criatividade', 'poesia'
    },
    'linguagem/comunicação': {
        'linguagem', 'palavra', 'palavras', 'texto', 'frase', 'leitura', 'escrita', 'fala', 'significado',
        'contexto', 'semântica', 'gramática', 'sintaxe', 'discurso', 'mensagem', 'diálogo', 'notícia',
        'comunicação', 'mídia', 'jornalismo', 'relato', 'voz', 'canal', 'escrever'
    },
    'economia/valor': {
        'economia', 'mercado', 'dinheiro', 'moeda', 'preço', 'valor', 'custo', 'investimento',
        'finanças', 'banco', 'crédito', 'renda', 'trabalho', 'capitalismo', 'comércio', 'inflação',
        'negócio'
    },
    'ciência/natureza': {
        'ciência', 'física', 'química', 'biologia', 'evolução', 'energia', 'átomo', 'molécula',
        'natureza', 'ambiente', 'vida', 'animal', 'planta', 'ecologia', 'clima', 'biodiversidade',
        'saúde', 'medicina', 'médico', 'doença', 'cura', 'tratamento', 'astronomia', 'astro',
        'estrela', 'galáxia', 'sol', 'lua', 'análise', 'analisar'
    },
    'tempo/medida': {
        'tempo', 'ano', 'anos', 'século', 'década', 'período', 'época', 'história', 'número',
        'taxa', 'medida', 'grau', 'escala', 'dia', 'manhã', 'noite', 'horário'
    }
}

GROUP_TO_HYPERNYM = {
    'tecnologia': 'artefato/tecnologia',
    'linguagem': 'linguagem/comunicação',
    'comunicação': 'linguagem/comunicação',
    'ciência': 'ciência/natureza',
    'natureza': 'ciência/natureza',
    'espaço': 'ciência/natureza',
    'saúde': 'ciência/natureza',
    'mente': 'conceito/cognição',
    'filosofia': 'conceito/cognição',
    'arte': 'conceito/cognição',
    'sociedade': 'entidade/sociedade',
    'direito': 'entidade/sociedade',
    'cotidiano': 'entidade/sociedade',
    'economia': 'economia/valor',
    'viagem': 'lugar/geografia',
    'esporte': 'processo/ação'
}

# Tabela de reconstrução morfológica de sub-tokens e radicais BPE para palavras plenas em português
STEM_RECONSTRUCTION = {
    'escre': 'escrever',
    'cons': 'construir',
    'manip': 'manipular',
    'anal': 'análise',
    'ess': 'essencial',
    'pal': 'palavras',
    'sensori': 'sensorial',
    'intelig': 'inteligência',
    'aprend': 'aprendizado',
    'comput': 'computação',
    'racioc': 'raciocínio',
    'gerenc': 'gerenciar',
    'estrut': 'estrutura',
    'func': 'função',
    'conhec': 'conhecimento',
    'entender': 'entendimento',
    'interp': 'interpretação',
    'sistem': 'sistema',
    'inform': 'informação',
    'signif': 'significado',
    'ling': 'linguagem',
    'mod': 'modelo',
    'proc': 'processo'
}


def reconstruct_candidate_word(raw_stem: str) -> str:
    """
    Reconstrói um radical ou sub-token BPE em sua palavra lexical completa em português.
    Garante que 100% dos nós exibidos na nuvem 3D sejam palavras inteiras e com significado pleno.
    """
    w = raw_stem.lower().strip()
    if len(w) < 3:
        return None

    # 1. Radical catalogado diretamente na tabela de alta precisão
    if w in STEM_RECONSTRUCTION:
        return STEM_RECONSTRUCTION[w]

    # 2. Já é uma palavra completa catalogada na taxonomia ou nos hiperônimos
    if w in ALL_GROUP_WORDS or any(w in terms for terms in INTERMEDIATE_HYPERNYMS.values()):
        return w

    # 3. Busca por prefixo no vocabulário oficial (quando w tem pelo menos 4 caracteres)
    if len(w) >= 4:
        matches = [full_w for full_w in ALL_GROUP_WORDS if full_w.startswith(w) and len(full_w) > len(w)]
        if matches:
            return min(matches, key=len)

    # 4. Descarte imediato de terminações impossíveis na língua portuguesa
    # (consoantes oclusivas/fricativas mudas ou encontros consonantais que caracterizam radicais cortados)
    if w.endswith(('b', 'c', 'd', 'f', 'g', 'h', 'j', 'k', 'p', 'q', 't', 'v', 'w',
                   'nd', 'nt', 'ss', 'rr', 'mp', 'mb', 'st', 'ct', 'pt', 'ft', 'lt', 'rt')):
        return None

    # 5. Palavras morfologicamente completas com terminações válidas em português
    if len(w) >= 4 and w.endswith((
        'a', 'e', 'o', 'as', 'es', 'os', 'am', 'em', 'im', 'om', 'um',
        'ar', 'er', 'ir', 'or', 'ur', 'al', 'el', 'il', 'ol', 'ul',
        'ão', 'ões', 'ães', 'ado', 'ada', 'ados', 'adas',
        'mento', 'mentos', 'dade', 'dades', 'ção', 'ções',
        'nte', 'ntes', 'vel', 'veis', 'oso', 'osa', 'osos', 'osas',
        'ico', 'ica', 'icos', 'icas', 'ura', 'uras',
        'ismo', 'ista', 'istas', 'eiro', 'eira'
    )):
        return w

    return None



def resolve_word_group(word: str) -> str:
    """Classifica a palavra pelo hiperônimo intermediário estruturado ou taxonomia correlata."""
    w = word.lower().strip()
    if w in CONNECTIVES:
        return 'conectivos'
    for hyper, terms in INTERMEDIATE_HYPERNYMS.items():
        if w in terms:
            return hyper
    for grp, terms in GROUPS_SET.items():
        if w in terms:
            return GROUP_TO_HYPERNYM.get(grp, grp)
    return None


def words(text: str):
    """Extrai palavras limpas com suporte a caracteres acentuados da língua portuguesa."""
    return WORDS_RE.findall(text.lower())


def readable_candidates(items):
    """Filtra e preserva alternativas de tokens que formam fragmentos legíveis de palavras."""
    clean = []
    seen = set()
    for item in items:
        raw_token = str(item.get('token', ''))
        token = raw_token.strip()
        if not CANDIDATE_RE.search(token) or token in seen:
            continue
        seen.add(token)
        has_space = raw_token.startswith((' ', ' ', 'Ġ', '\t', '\n')) or (len(raw_token) > len(raw_token.lstrip()))
        clean.append(dict(
            token=token,
            raw_token=raw_token,
            probability=math.exp(item['logprob']),
            is_word_start=has_space
        ))
    return clean


def fallback_hypernym(word: str) -> str:
    """Enquadra termos de conteúdo não mapeados diretamente nos 10 hiperônimos estáveis."""
    w = word.lower().strip()
    if w.endswith(('nte', 'vel', 'oso', 'osa', 'az', 'il', 'ivo', 'iva', 'al', 'ico', 'ica')):
        return 'propriedade/estado'
    if w.endswith(('ar', 'er', 'ir', 'ando', 'endo', 'indo', 'ou', 'eu', 'iu', 'aria', 'eria', 'iria', 'asse', 'esse', 'isse', 'am', 'em')):
        return 'processo/ação'
    return 'conceito/cognição'


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


def graph(text: str, answer: str = '', step_candidates: list = None):
    """
    Heurística lexical e probabilística para alimentar a cena Three.js.
    Destaca termos do texto de entrada, resposta formulada e alternativas concorrentes
    ponderadas pela LLM, agrupadas por hiperônimos intermediários estáveis.
    """
    source = [w for w in words(text) if (w in CONNECTIVES or (w not in STOP and (len(w) > 2 or w in ALL_GROUP_WORDS)))]
    reply = [w for w in words(answer) if (w in CONNECTIVES or (w not in STOP and (len(w) > 2 or w in ALL_GROUP_WORDS)))]

    # 1. Extração de palavras de conteúdo reais concorrentes (piso >= 3%, máx 3 por passo, sem sufixos cortados)
    real_candidates_list = []
    existing_content_words = {ew for ew in (source + reply) if ew not in CONNECTIVES and len(ew) >= 3}
    seen_cand_words = set(source + reply)

    if step_candidates:
        for step in step_candidates:
            cands = step.get('candidates') or []
            step_valid = []
            for c in cands:
                p = c.get('probability', 0.0)
                if p < 0.03:
                    continue

                # Exige que seja início de palavra (descarte estrito de sufixos/miolos como "ência", "izado", "ados", "agem")
                raw_tok = str(c.get('raw_token') or c.get('token') or '')
                is_start = c.get('is_word_start')
                if is_start is None:
                    is_start = raw_tok.startswith((' ', ' ', 'Ġ', '\t', '\n')) or (len(raw_tok) > len(raw_tok.lstrip()))
                if not is_start:
                    continue

                tok = raw_tok.strip().lower()
                clean_toks = words(tok)
                if not clean_toks:
                    continue
                raw_stem = clean_toks[0]

                # Reconstrói sub-tokens e radicais BPE para palavras lexicais completas em português
                full_w = reconstruct_candidate_word(raw_stem)
                if not full_w:
                    continue

                if len(full_w) < 3 or full_w in CONNECTIVES or full_w in STOP or full_w in seen_cand_words:
                    continue

                # Evita duplicar palavras já existentes na pergunta ou na resposta
                if any(
                    (full_w == ew or full_w.startswith(ew) or ew.startswith(full_w))
                    for ew in existing_content_words
                    if len(ew) >= 3 and len(full_w) >= 3
                ):
                    continue

                seen_cand_words.add(full_w)
                step_valid.append((full_w, p))
                if len(step_valid) >= 3:
                    break
            real_candidates_list.extend(step_valid)

    # Limite saudável de alternativas concorrentes na nuvem para manter 60 FPS
    cand_nodes_data = real_candidates_list[:30]
    cand_words = [w for w, _ in cand_nodes_data]
    cand_prob_map = dict(cand_nodes_data)

    keys = list(dict.fromkeys(source + reply + cand_words))[-110:]

    # Acomodação estrita de termos não mapeados diretamente nos 10 hiperônimos intermediários
    unknown_keys = [w for w in keys if w not in CONNECTIVES and resolve_word_group(w) is None]
    dynamic_group_map = {w: fallback_hypernym(w) for w in unknown_keys}

    # Âncoras discretas de apoio da taxonomia (desativadas para testes conforme alinhamento)
    expanded = []

    nodes = []
    for w in keys:
        if w in CONNECTIVES:
            g = 'conectivos'
            weight = 0.22
            origin = 'conectivo'
            prob = None
        else:
            g = resolve_word_group(w)
            if g is None:
                g = dynamic_group_map.get(w, fallback_hypernym(w))
            if w in source:
                weight = min(1.0, 0.50 + 0.12 * source.count(w))
                origin = 'entrada'
                prob = None
            elif w in reply:
                weight = min(0.95, 0.42 + 0.08 * reply.count(w))
                origin = 'resposta'
                prob = None
            else:
                prob = cand_prob_map.get(w, 0.05)
                weight = min(0.85, max(0.30, round(prob * 1.5, 2)))
                origin = 'alternativa concorrente'
        node_dict = dict(
            id=w,
            group=g,
            weight=round(weight, 2),
            origin=origin,
            in_reply=(w in reply),
            in_source=(w in source)
        )
        if prob is not None:
            node_dict['probability'] = round(prob * 100, 1)
        nodes.append(node_dict)

    for w, g in expanded[:30]:
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
            # Evita criar arestas lexicais secundárias entre termos que já pertencem à mesma resposta formulada,
            # mantendo o traçado da resposta estritamente linear e sem triângulos redundantes
            if (peer['id'] in reply) and (node['id'] in reply):
                continue
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

    # Ordenação da legenda: grupos semânticos estáveis no meio,
    # e grupos dinâmicos ('conceito:', 'ação:', 'qualidade:', 'tema:') obrigatoriamente por último (à direita).
    # Conectivos são excluídos da legenda (possuem controle exclusivo no botão dedicado).
    all_groups = list(dict.fromkeys(n['group'] for n in nodes))
    standard_groups = [
        g for g in all_groups
        if not any(g.startswith(p) for p in ('tema:', 'ação:', 'qualidade:', 'conceito:')) and g != 'conectivos'
    ]
    dynamic_groups = [
        g for g in all_groups
        if any(g.startswith(p) for p in ('tema:', 'ação:', 'qualidade:', 'conceito:'))
    ]
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
            demo_tokens = re.findall(r'\S+\s*', answer)
            demo_history = []
            for d_idx, fragment in enumerate(demo_tokens):
                cands = [
                    dict(token=' ' + fragment.strip(), probability=0.88),
                    dict(token=' conceito', probability=0.06),
                    dict(token=' universo', probability=0.04)
                ]
                demo_history.append(dict(token=fragment, step=d_idx, candidates=cands))
                yield event('chunk', text=fragment, candidates=cands, step_index=d_idx)
                await asyncio.sleep(0.025)

            elapsed = max(0.01, time.perf_counter() - started)
            yield event(
                'done',
                answer=answer,
                graph=graph(text, answer, step_candidates=demo_history),
                candidates=demo_history[-1]['candidates'] if demo_history else [],
                step_candidates=demo_history,
                max_tokens_config=max_tokens,
                ttft_ms=None,
                output_tokens=len(demo_tokens),
                text_tokens=prompt_words_count,
                words_s=round(len(words(answer)) / elapsed, 1)
            )
            return

        answer = ''
        latest_candidates = []
        step_history = []
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
                temperature=0.0,
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
                                step_history.append(dict(
                                    token=fragment,
                                    step=len(step_history),
                                    candidates=latest_candidates
                                ))
                        elif fragment:
                            step_history.append(dict(
                                token=fragment,
                                step=len(step_history),
                                candidates=latest_candidates
                            ))
                        if fragment or logs:
                            if ttft_ms is None:
                                ttft_ms = round((time.perf_counter() - started) * 1000, 1)
                        if fragment:
                            answer += fragment
                            yield event(
                                'chunk',
                                text=fragment,
                                candidates=latest_candidates,
                                step_index=len(step_history) - 1
                            )

            elapsed = max(0.01, time.perf_counter() - started)
            yield event(
                'done',
                answer=answer,
                graph=graph(text, answer, step_candidates=step_history),
                candidates=latest_candidates,
                step_candidates=step_history,
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
