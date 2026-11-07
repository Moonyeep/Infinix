# Roadmap executável

A primeira etapa criou o núcleo local com registro de ferramentas, política, workspace, diff, backup, rollback e eventos. A segunda conectou o núcleo ao bridge com `agent_list_tools` e `agent_call_tool`, mantendo o canal Roblox separado. A terceira adiciona sessões SQLite, checkpoints e um provider de navegador isolado e opcional, com allowlist de hosts e navegação desativada por padrão.

A validação contínua deve tratar cada capacidade como adaptador independente. O bridge não deve entregar acesso de navegador pessoal, desktop ou credenciais apenas porque uma ferramenta está registrada. O provider de browser precisa de Playwright instalado, perfil dedicado e uma policy explícita.

A próxima sequência é: integrar a UI de aprovação ao popup e ao painel do agente; registrar checkpoints em cada mutação; adicionar executor de testes com adapters Bash/PowerShell/cmd e timeouts; adicionar MCP manifestado; criar replay/validators; configurar scheduler nativo por sistema operacional; e só então ativar computer use opt-in.

Nenhuma etapa deve autoalterar política, credenciais, sandbox ou hooks de segurança. O ciclo semanal pode propor mudanças nessas áreas para revisão, mas deve rejeitá-las automaticamente como publicação.
