# Arquitetura de agente para evolução do Infinix

## Resultado da pesquisa

Foram analisados OpenManus, OpenClaw, OpenHands, BrowserGym, WebArena e SWE-agent. Os cinco primeiros repositórios de referência abertos foram baixados em `reference-agents/`, com seus commits e licenças preservados. Claude Code e OpenAI Computer-Using Agent foram usados apenas como referências documentais: não são dependências de código aberto que possam ser incorporadas diretamente.

A convergência entre as implementações é: o modelo decide em turnos; um runtime normaliza e executa ferramentas tipadas; um broker externo aplica permissões; o workspace ou navegador é isolado; e eventos persistidos permitem retomar, auditar, testar e reverter. Essa separação é mais importante que copiar um prompt ou uma implementação específica.

OpenManus contribui com o ciclo ReAct/tool-calling, schemas e operadores de arquivos. OpenClaw contribui com daemon local, sessões, eventos, approvals, memória em camadas e melhoria limitada a skills versionadas. OpenHands contribui com a separação entre agente, servidor, conversa e workspace. BrowserGym e WebArena contribuem com o contrato `reset/step/close`, observações DOM/AXTree/screenshot e validadores de estado. SWE-agent contribui com uma superfície de ferramentas pequena, parser estrito, editor, feedback determinístico e trajetórias reproduzíveis.

## Implementação iniciada

O pacote `agent_core/` é uma primeira fatia funcional e independente do bridge Roblox atual. Ele já fornece:

- `ToolRegistry` com schemas, capacidades e riscos declarados;
- `PolicyBroker` com precedência `deny > ask > allow`;
- workspace com raiz confinada e rejeição de traversal;
- edição atômica com backup e possibilidade de rollback;
- log JSONL correlacionado com redaction de chaves e tokens;
- CLI `infinix_agent.py` com `tools`, `read` e `patch`;
- testes de segurança executáveis apenas com a biblioteca padrão do Python.

A ferramenta de leitura é permitida por padrão. A ferramenta de alteração exige aprovação explícita (`--approve`) e gera diff/backup. Não existe fallback silencioso para escrever fora do workspace.

## Próximas integrações de código

A próxima camada deve conectar o registry ao bridge por um protocolo de sessão local, preservando o transporte atual. Depois entram SQLite/checkpoints, cancelamento e deadlines, executor de testes por plataforma, diff/rollback por execução, MCP com manifestos e discovery tardio, e um browser Playwright com perfil dedicado. Controle de desktop deve permanecer opt-in até haver readiness, gravação de ações e testes por sistema operacional.

## Autoaperfeiçoamento

O agente pode propor melhorias de skills, prompts, heurísticas, parsers, adapters e casos de teste a partir de traces sanitizados. Cada proposta deve ter evidência, diff, testes, revisão, canário, hash de versão e rollback. O agente não deve alterar silenciosamente o PolicyBroker, credenciais, sandbox, executores, hooks de segurança ou regras de autorização. Isso preserva a qualidade sem permitir autoelevação irreversível.

## Referências verificadas

[1]: https://github.com/FoundationAgents/OpenManus "OpenManus"
[2]: https://docs.openclaw.ai/concepts/architecture "OpenClaw architecture"
[3]: https://docs.openclaw.ai/tools/self-learning "OpenClaw self-learning"
[4]: https://docs.anthropic.com/en/docs/claude-code "Claude Code documentation"
[5]: https://code.claude.com/docs/en/permissions "Claude Code permissions"
[6]: https://developers.openai.com/api/docs/guides/tools-computer-use "OpenAI computer use guide"
[7]: https://openai.github.io/openai-agents-python/human_in_the_loop/ "OpenAI Agents SDK human in the loop"
[8]: https://github.com/ServiceNow/BrowserGym "BrowserGym"
[9]: https://github.com/web-arena-x/webarena "WebArena"
[10]: https://github.com/ServiceNow/AgentLab "AgentLab"
[11]: https://docs.openhands.dev/overview/introduction "OpenHands"
[12]: https://swe-agent.com/latest/background/architecture/ "SWE-agent architecture"
[13]: https://swe-agent.com/latest/background/aci/ "SWE-agent ACI"
