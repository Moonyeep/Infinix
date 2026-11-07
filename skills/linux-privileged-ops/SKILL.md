---
name: infinix-linux-privileged-ops
description: Operações Linux que realmente exigem root usando o fluxo local sudo/askpass. Use quando a ferramenta terminal.run_as_admin estiver listada e a tarefa autorizada exigir privilégio administrativo.
---

# Operações Linux com privilégio

1. Confirme que a tarefa exige root; prefira ferramenta não elevada para leitura e mudanças restritas ao workspace.
2. Use `agent.terminal.run_as_admin` somente se estiver no inventário da sessão. Ele solicita a autenticação pelo diálogo askpass do desktop quando necessário e envia a senha diretamente ao `sudo`.
3. Nunca peça, receba, repita, inclua em comando, leia, armazene ou registre a senha no chat, prompt, arquivo, variável de ambiente ou log. Nunca use `sudo -S`, `echo senha | sudo` ou prompts interativos no terminal comum.
4. No perfil Amplo, as duas confirmações iniciais autorizam as ferramentas habilitadas sem prompt por ação; execute a solicitação delimitada de ponta a ponta. Em outros perfis, respeite a aprovação existente. O usuário pode cancelar o diálogo do sistema.
5. Não contorne políticas de sudo, políticas corporativas ou bloqueios fixos. Não deixe processos elevados em segundo plano nem amplie o escopo para “limpar” o sistema.
6. Verifique o código de retorno e o estado final. Se não houver sessão gráfica, `sudo` ou app askpass suportado, relate o bloqueio; não solicite a senha no chat como alternativa.
