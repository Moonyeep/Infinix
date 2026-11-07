# Infinix v1.6.18 — Speed Optimized

## Diagnóstico do log

A mensagem `JSON object never closed` é produzida pelo parser da extensão em `zeroscript-extension/core/config.js` quando a resposta da IA contém um comando JSON incompleto ou que não pôde ser interpretado. Ela não é uma mensagem gerada por `Workspace.create`, `Workspace.write` ou `ProcessRunner`.

A implementação atual não possui um limite de 3–5 caracteres para conteúdo. O bridge usa WebSocket com limite de 16 MiB, e os testes ponta a ponta executados nesta cópia criaram corretamente arquivos contendo `bug`, `print(1)`, aspas, barra invertida e quebra de linha. `process.test` também executou `python3 -c "print(1)"` e retornou código 0.

O log fornecido mostra ainda uma inconsistência de versão: o arquivo se chama 1.6.18, mas o bridge e o manifesto declaravam 1.6.17. Isso foi alinhado para 1.6.18.

## Correções e otimizações

- O parser da extensão agora decodifica também o formato legado em que `arguments` ou `params` chegam como uma string contendo JSON. Isso evita que provedores que usam function-calling percam os argumentos antes do bridge.
- O bridge normaliza argumentos JSON-string antes de registrar as chaves da chamada. Envelopes inválidos não derrubam mais o handler WebSocket: recebem uma resposta estruturada com `kind: invalid_arguments`.
- Mensagens WebSocket que não são objetos JSON são ignoradas com diagnóstico no log, em vez de causarem uma exceção silenciosa no loop.
- Nomes de ferramenta vazios e timeouts não numéricos recebem resposta de erro determinística; timeouts válidos são limitados a uma faixa segura.
- A montagem do catálogo de ferramentas foi otimizada de uma busca repetida no índice de colisões para uma tabela reversa, reduzindo o custo de broadcasts em instalações com vários servidores MCP.
- O conteúdo de runtime (`.zeroscript`, `__pycache__` e logs transitórios) não é incluído no ZIP final para reduzir o tamanho e evitar carregar estado antigo.

## Validação realizada

- 41 testes Python passaram.
- Todos os testes JavaScript existentes passaram, incluindo o parser, aprovação, reconexão, URLs do navegador, ChatGPT e UI de perfil.
- Teste WebSocket ponta a ponta passou com criação de arquivos por argumentos normais e JSON-string, conteúdo com aspas/barra/quebra de linha, execução de teste e recuperação após argumentos inválidos.

## Limite da conclusão

A validação foi feita no sandbox Linux e não reproduziu a camada DOM de cada provedor de IA no navegador Windows do usuário. Portanto, não é correto afirmar que toda origem possível de truncamento visual do provedor foi eliminada. Se o erro continuar depois da instalação, o próximo artefato necessário é o texto exato da resposta da IA que recebeu o rótulo `bad JSON`/`cut off`, junto com o provedor e o console da extensão. O bridge corrigido agora mantém chamadas válidas e falhas de envelope separadas no log.

## Instalação no Windows

1. Faça backup da pasta atual.
2. Extraia a pasta do ZIP em `C:\Users\arthur\Downloads\Infinix-v1.6.18-SPEED-OPTIMIZED`.
3. Em `chrome://extensions`, ative o modo de desenvolvedor e use **Recarregar** na extensão descompactada.
4. Feche o bridge anterior e execute `Start_Agent.bat` a partir da nova pasta.
5. Confirme no terminal que aparece `Infinix Bridge v1.6.18`.
6. Recarregue a página da IA antes de iniciar uma nova sessão.

Não copie `.zeroscript` ou `logs` da instalação antiga para a nova durante o primeiro teste; esses diretórios podem conter estado e diagnósticos de uma execução anterior.
