# Validação desta entrega

Verificado no ambiente de desenvolvimento Linux:

- Sintaxe Python do backend e instalador.
- Sintaxe JavaScript do cliente.
- Entrega HTTP do HTML, CSS, JavaScript e Three.js local.
- Quatro testes automatizados: streaming e probabilidades com runtime simulado; última versão prevalecendo durante atualizações; modelo indisponível; rejeição de origem WebSocket externa.

Não validado neste ambiente:

- Execução do modelo real Qwen no llama.cpp (os testes de protocolo usam respostas simuladas).
- Instalador e binários no Windows.
- Latência, memória, temperatura e fluidez no i7-4500U.
- Inspeção visual em navegador: a obtenção do navegador de teste falhou por timeout de rede. A sintaxe do cliente foi verificada, mas isso não substitui a validação visual.

O modo Demonstração é identificado na interface e não produz probabilidades fictícias. O backend real está implementado, mas a primeira execução no notebook continua necessária para validar a integração completa e o desempenho.
