# Diretrizes de Contribuição - Universo IA

Agradecemos o interesse em contribuir com o **Universo IA**. Este projeto tem como missão tornar a mecânica interna de modelos de linguagem compreensível, visual e acessível em qualquer computador comum sem exigir placas de vídeo dedicadas.

---

## Princípios de Desenvolvimento

1. **Eficiência em CPU e 60 FPS**: Qualquer alteração na renderização Three.js ou no processamento lexical deve manter o consumo de CPU baixo e a taxa de quadros estável em 60 quadros por segundo.
2. **Privacidade e Modo Offline**: O projeto opera estritamente de forma local. Nenhuma dependência externa com envio de dados ou telemetria em nuvem é permitida no fluxo principal.
3. **Didática e Transparência Técnica**: Recursos visuais devem refletir com precisão os conceitos de processamento de linguagem natural (tokens, probabilidades, massas de top-k, taxonomia e sequências de geração).

---

## Fluxo de Trabalho de Contribuição

### 1. Criar uma Branch
Crie uma branch descritiva a partir da branch principal (`main`):
```bash
git checkout -b feature/nome-da-funcionalidade
# ou
git checkout -b fix/descricao-do-problema
```

### 2. Configurar o Ambiente de Testes
Certifique-se de que o ambiente virtual está ativo e as dependências instaladas:
```bash
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### 3. Executar a Suíte de Testes
Antes de enviar qualquer alteração, todos os testes unitários do protocolo devem ser validados e passar sem falhas:
```bash
python -m unittest tests/test_protocol.py
```

### 4. Commits Estruturados
Adote o padrão Conventional Commits para mensagens claras e rastreáveis:
- `feat: adiciona novo agrupamento dinâmico na legenda`
- `fix: corrige posicionamento do inspetor lexical em telas ultrawide`
- `docs: atualiza instruções de execução no Linux`
- `perf: otimiza alocação de buffers no loop de animação Three.js`

Recomenda-se a assinatura de commits com chave GPG para garantia de autoria e verificação de integridade no GitHub.

### 5. Submissão do Pull Request
Abra o Pull Request detalhando:
- O propósito da alteração (o que foi resolvido ou adicionado).
- Como testar manualmente na interface.
- Confirmação de que os testes automatizados passaram com sucesso.

---

## Código de Conduta e Direitos Autorais

Ao contribuir com código para este repositório, você concorda que suas contribuições serão disponibilizadas sob os termos dos direitos autorais e licença do projeto especificados no arquivo `LICENSE`.
