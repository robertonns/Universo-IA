# Universo Local — protótipo 0.1

Chat explorável com mapa tridimensional, resposta provisória automática e candidatos a próximos tokens. Projetado para uma pessoa, em Windows x64, 12 GB de RAM, com inferência somente em CPU (benchmark de referência testado em processador Intel Core i7 dual-core).

## Começar no Windows

1. Extraia **todo** o ZIP para uma pasta, por exemplo `Documentos\Universo`. Não execute de dentro do ZIP.
2. Instale Python 3.11 ou 3.12 de https://www.python.org/downloads/windows/ com o **Python Launcher**. Não precisa instalar Node.js.
3. Dê dois cliques em **INSTALAR.bat**. Requer internet nesta etapa: instala dependências em `.venv`, baixa o runtime CPU do llama.cpp e o Qwen Q4_K_M (aproximadamente 491 MB, além do runtime). Não requer chave de API, cadastro ou pagamento. O instalador registra as versões e verifica hashes quando fornecidos pelos distribuidores.
4. Abra apenas **INICIAR_APP.bat**. Na primeira vez, ele instala o modelo automaticamente; nas próximas, apenas o inicia se necessário. A janela do modelo ficará minimizada; mantenha a janela do aplicativo aberta.
5. Escreva ou selecione um exemplo. Para apenas apresentar o visual, selecione **Demonstração · sem IA**; esse modo não precisa do modelo em execução, mas ainda precisa da aplicação Python instalada.

Após a instalação, o aplicativo usa apenas arquivos locais. Three.js já está incluído. Não há fontes, scripts ou APIs remotos no uso normal. A aceleração gráfica do navegador é usada no 3D; o LLM usa CPU (`-ngl 0`). Para encerrar, feche as duas janelas ou pressione Ctrl+C.

## Como funciona

- Espaço: captura uma versão e dispara após 250 ms. Outro espaço substitui o disparo pendente; digitar a palavra seguinte não cancela a captura anterior.
- Colagem e exclusão também disparam. Uma pausa de 850 ms captura a última palavra sem exigir espaço ou Enter.
- Uma geração por vez, fila de tamanho um (a versão mais recente). Não são executadas todas as versões intermediárias.
- Uma geração antiga pode emitir até cerca de 12 tokens antes de ceder à nova. O painel identifica a versão; uma resposta antiga nunca é apresentada como atual.
- A resposta tem até 60 tokens, não uma conversa persistente. Cada edição reinterpreta o texto integral no campo. Não há memória entre sessões.
- Contexto de 2.048 tokens, com rejeição explícita acima de 1.850 tokens de prompt para reservar espaço. Entrada limitada a 4.000 caracteres.

## O que é real, aproximado e demonstrativo

**Real quando o modelo está conectado:** texto gerado, contagem dos tokens do texto escrito, alternativas legíveis e probabilidades de saída retornadas pelo llama.cpp e velocidade observada da resposta. A interface não mostra os tokens adicionais das instruções internas e da formatação do chat.

**Nuvem heurística nesta versão:** termos da entrada e da resposta; grupos de um vocabulário explícito para tecnologia, linguagem, ciência, viagem e cotidiano; expansão por esse vocabulário; conexões de sequência e de grupo. Cor = grupo; tamanho = peso de origem/frequência; distância = layout espacial ilustrativo estável. **Não usa embeddings, não mede atenção, não inspeciona estados ocultos nem mostra o raciocínio interno.** Para assuntos fora do vocabulário, os termos aparecem no grupo contexto. Essa limitação fica visível no produto.

**Demonstração:** resposta roteirizada e nenhuma probabilidade inventada. Serve para navegar e apresentar a interação, não para avaliar o modelo.

Os candidatos exibidos correspondem à última posição gerada da **resposta do assistente**. Não são previsões do que você vai digitar. A massa de probabilidade pode ser inferior a 100%; não renormalizamos o top-k. A configuração do servidor e a quantização afetam as probabilidades. Total de parâmetros nominal não é “parâmetros consultados”.

## Teste de desempenho no notebook

1. Feche programas pesados, conecte o notebook à tomada e inicie o modelo.
2. Abra o exemplo “Inteligência & linguagem” e espere a resposta terminar.
3. Repita três vezes: o primeiro teste inclui aquecimento.
4. Digite duas frases continuamente: confira se o campo permanece responsivo e se o indicador distingue a versão antiga da atual.
5. Use **Exportar medições JSON** no painel técnico. O arquivo contém tempos, contagens e termos do mapa; revise antes de compartilhar.

Não há previsão garantida de tokens/s. Ajustes: mudar `-t 2` para `-t 3` no iniciador e comparar; fechar abas; diminuir a janela; reduzir o limite `max_tokens=60` no backend. Mais threads não garantem melhor desempenho e podem piorar a interface.

## Solução de problemas

- **Modelo desconectado:** mantenha INICIAR_MODELO.bat aberto; veja erros nessa janela. As portas são 8081 (modelo) e 8765 (aplicação).
- **DLL ausente:** instale o Microsoft Visual C++ Redistributable x64 oficial, conforme exigido pelo runtime do llama.cpp.
- **Falha no download:** execute INSTALAR.bat novamente. Arquivos parciais não são tratados como modelos concluídos. O instalador usa o release estável mais recente do llama.cpp; mudanças futuras na distribuição podem exigir ajuste.
- **Instalação manual do runtime:** obtenha o ZIP CPU x64 em https://github.com/ggml-org/llama.cpp/releases e extraia, com suas DLLs, para `runtime`. O iniciador procura `llama-server.exe` nessa árvore.
- **Modelo manual:** baixe `qwen2.5-0.5b-instruct-q4_k_m.gguf` de https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF e coloque em `models`.
- **Mapa não aparece:** habilite aceleração gráfica no navegador e recarregue. Sem WebGL, o chat ainda pode funcionar, mas a cena não.
- **Texto incompleto:** o limite de 60 tokens é intencional; o modelo pequeno também pode falhar em português e tarefas complexas.
- **Sem probabilidades:** versões incompatíveis do servidor não devem ser interpretadas como probabilidade zero. A interface mostra indisponibilidade; confirme o endpoint de chat do runtime.

## Organização e evolução

`server.py`: backend e heurística lexical. `static/app.js`: eventos, streaming e Three.js. `static/style.css`: aparência. `preparar_modelo.py`: instalação dos arquivos externos. `tests/test_protocol.py`: testes da política de versões, streaming e falhas usando servidor simulado.

Próxima evolução: benchmark no notebook, embeddings multilíngues pequenos em CPU com cache, proximidades por similaridade, projeção 3D estável e comparação de modelos. Essas funções não são simuladas como existentes nesta versão.

Para outros sistemas: instale `requirements.txt` num ambiente virtual; execute um llama-server compatível em 127.0.0.1:8081 com os argumentos do BAT; rode `python server.py`. O instalador de binários deste pacote é específico para Windows.

## Fontes e licenças

- Three.js 0.170.0, MIT; licença incluída em `static/vendor/THREE-LICENSE.txt`.
- llama.cpp: https://github.com/ggml-org/llama.cpp — distribuído separadamente pelo instalador.
- Qwen2.5-0.5B-Instruct-GGUF, Apache 2.0: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF — pesos e licença baixados pelo instalador.

Sem chamadas de API pagas. Energia, equipamento e rede de instalação não estão incluídos nesse “custo zero por token”.
