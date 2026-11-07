# Referências de agentes

Os repositórios em `reference-agents/` são cópias rasas usadas para estudo e compatibilidade. Cada um mantém seu próprio arquivo de licença e commit fixado no ambiente de trabalho.

- OpenManus — MIT — loop ReAct/tool-calling, schemas e operadores de arquivo.
- OpenClaw — MIT — gateway local, sessões, approvals, memória e self-learning limitado a skills versionadas.
- OpenHands — MIT — separação agent/server/workspace e execução local/Docker/remota.
- BrowserGym — Apache-2.0 — contrato reset/step/close, observações DOM/AXTree/screenshot e avaliação.
- WebArena — Apache-2.0 — ambientes web reproduzíveis e validadores de estado.
- SWE-agent — MIT — ACI reduzida, parser, editor, feedback e trajetórias.

O Infinix não incorpora código de Claude Code nem do OpenAI Computer-Using Agent: são referências proprietárias/documentais, não dependências de código aberto deste projeto.

A integração inicial é uma implementação própria, compatível conceitualmente com esses padrões, para evitar copiar componentes inteiros sem revisão de dependências, licença e segurança. O núcleo P0 está em `agent_core/` e mantém o bridge Roblox existente separado.
