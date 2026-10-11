# Registro de Alterações (Changelog) - Universo IA

Todas as alterações notáveis deste projeto são documentadas neste arquivo.
O formato é baseado no padrão [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/) e este projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [0.5.8] - 2026-10-10

### Adicionado
- Documentação executiva completa no `README.md` com demonstração animada em GIF de alta fluidez (`docs/demo.gif`), vídeo WebM nativo e screenshot de capa.
- Suporte a automação de gravação de tela e testes de integração via Playwright com aceleração WebGL.
- Arquivo de configuração de variáveis de ambiente `.env.example`.
- Guia de contribuição com boas práticas e convenções de commit em `CONTRIBUTING.md`.
- Modelos estruturados de relato de erro e requisição de recursos para o GitHub (`.github/ISSUE_TEMPLATE/`).
- Especificação de empacotamento em contêiner com `Dockerfile` e `.dockerignore`.

---

## [0.5.7] - 2026-10-10

### Adicionado
- Marca d'água esteganográfica matemática determinística (`RN_TOPOLOGICAL_CONSTANT`) em `server.py` derivada do hash SHA-256 do autor Roberto Nunes, comprovando autoria e integridade de forma invisível no frontend.
- Relatório técnico executivo de arquitetura, levantamento de diretórios e matriz de conformidade jurídica de licenças (`RELATORIO_TECNICO_ARQUITETURA_E_LICENCAS.pdf`).
- Arquivo formal de licença jurídica (`LICENSE`) com reserva de direitos autorais de exploração comercial e concessão acadêmica/educacional.
- Arquivo de atribuição de licença de terceiros (`runtime/LICENSE-LLAMA.txt`) para o binário do llama.cpp sob licença MIT.

---

## [0.5.6] - 2026-10-10

### Modificado
- Interface de inspeção lexical (`#inspector`): remoção total de caixa/background delimitador para transparência visual completa, mantendo a nuvem 3D visível ao fundo.
- Ajuste do sublinhado da palavra selecionada para limitar-se estritamente à extensão gráfica do termo inspecionado (`fit-content`).
- Suporte a metadados de alternativa vencedora nas palavras concorrentes (`competing_winner`), identificando explicitamente o termo vitorioso no HUD.
- Sincronização do painel de próximos tokens para corresponder por padrão ao último passo de geração concluído pelo modelo.

---

## [0.5.5] - 2026-10-09

### Adicionado
- Modo Trajetória dinâmica (Cometa neural) com destaque estroboscópico suave em feixe dourado percorrendo a ordem cronológica dos tokens gerados na resposta.
- Suporte a visualização imersiva em tela cheia (⛶ Tela cheia) com redimensionamento automático de viewport WebGL e preservação da posição de rolagem original ao fechar.
- Filtro interativo para ligar e desligar conectivos estruturais (`#toggle-connectives`) preservando atalhos semânticos entre termos conceituais.

---

## [0.5.0] - 2026-10-07

### Adicionado
- Balança dinâmica de tokens com presets de proporção (`Pergunta Detalhada`, `Equilibrado`, `Resposta Expandida`) e slider contínuo de ajuste fino.
- Modo Investigativo na resposta: capacidade de clicar em qualquer token gerado no texto para inspecionar retrospectivamente as opções concorrentes avaliadas naquele ponto exato.
- Divisão didática em colunas independentes para próximos tokens diretos (artigos, preposições e conectivos) e indiretos (substantivos, verbos e qualificadores).

---

## [0.1.0] - 2026-09-22

### Adicionado
- Versão inicial do protótipo Universo Local com inferência local de LLM em CPU via servidor llama.cpp (Qwen 2.5 0.5B Instruct quantizado em Q4_K_M).
- Renderização inicial de cena 3D com Three.js mapeando palavras em nuvem heurística lexical.
- Suporte a Server-Sent Events (SSE) para streaming assíncrono de tokens.
- Scripts de instalação e inicialização automatizada para Windows (`INSTALAR.bat`, `INICIAR_APP.bat`).
