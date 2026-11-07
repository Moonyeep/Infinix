# Protocolo de estudo e autoaperfeiçoamento

## Comportamento e limites de segurança

O seletor de início oferece **Estudo e autoaperfeiçoamento** separadamente dos perfis de permissão. Esse modo usa sempre o perfil Básico; `agent.self_improve.run` executa sem aprovação por ciclo, mas fica confinado ao pipeline isolado. Também é possível pedir `execute o protocolo de autoaperfeiçoamento` em qualquer conversa suportada. Isso não libera terminal, navegador, edição da instalação ativa ou promoção automática.

`mode=audit` executa os testes da versão atual, sem enviar arquivos. `mode=propose` pode gerar um diff e um ZIP de candidato numa cópia/worktree descartável. Para propostas não interativas, configure uma vez `ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1` no ambiente do usuário; sem essa variável, nada é enviado. A solicitação de proposta e a configuração válida do endpoint também são necessárias. Não são incluídos `config.json` local do bridge, arquivos `.env`, arquivos de chave privada nem diretórios secretos conhecidos; padrões comuns de tokens/segredos são redigidos. A variável é consentimento persistente para futuras execuções automáticas; use apenas um endpoint em que confia.

A ferramenta nunca modifica, instala, publica, faz merge ou promove o candidato à versão ativa. Ela não executa código gerado no host: valida sintaxe Python, sintaxe JavaScript quando Node está disponível e JSON. A suíte completa é executada na versão de origem como baseline; testes comportamentais do candidato ficam pendentes para revisão/sandbox isolada. Portanto, `review_required` significa que há uma proposta estática, não que sua correção foi provada.

Relatórios ficam em `.zeroscript/improvement-reports/`; diffs e ZIPs em `.zeroscript/improvement-candidates/<execução>/`. Uma instalação sem Git é suportada por meio de uma cópia temporária. Em uma worktree Git, a execução é bloqueada se houver alterações staged, unstaged ou arquivos não rastreados.

## Configurar o provedor de modelo

Para uma proposta autônoma, configure no ambiente do usuário (não em argumentos de linha de comando nem em arquivo versionado):

- `ZS_IMPROVE_API_BASE`: endpoint compatível com OpenAI Chat Completions, por exemplo `https://<provedor-confiável>/v1`; HTTP só é aceito para `localhost`.
- `ZS_IMPROVE_MODEL`: nome do modelo atendido pelo endpoint.
- `ZS_IMPROVE_API_KEY`: chave do provedor remoto. Não é necessária para um endpoint local.

Se essas variáveis não estiverem configuradas, o protocolo não inventa uma proposta: registra `driver_unconfigured` e termina sem transferir código. O script não usa nem registra a chave em relatórios. Os relatórios registram o host/modelo e a situação da execução.

## Execução manual

Auditoria local, sem transferência de fonte:

```text
python self_improve.py --repo C:\caminho\Infinix-Agent-General --mode audit
```

Para criar uma proposta usando o endpoint configurado, a opção abaixo autoriza o envio do snapshot sanitizado:

```text
python self_improve.py --repo C:\caminho\Infinix-Agent-General --mode propose --allow-source-upload
```

O comando legado `--command` não é executado pelo protocolo seguro; o agente não roda drivers arbitrários fornecidos por variáveis de ambiente.

## Agendamento semanal no Windows

Com Python 3.10 ou mais recente instalado, abra PowerShell **sem elevação** no diretório extraído e execute:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\schedules\install_weekly_task.ps1
```

O bypass vale somente para esse processo; a política global do PowerShell não é alterada. O script registra, para o usuário atual e sem privilégios elevados, uma tarefa semanal aos domingos às 03:00 (hora local), com limite de quatro horas e sem instâncias concorrentes. A tarefa usa `--allow-source-upload`, mas o envio só ocorre se `ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1` também estiver configurado no ambiente do usuário. Defina essa variável somente se autorizar transferências automáticas ao endpoint configurado. Para uma auditoria semanal sem envio, edite a ação da tarefa e remova `--allow-source-upload` (ou execute `self_improve.py --mode audit`).

A tarefa roda quando o usuário estiver conectado. O Task Scheduler inicia a próxima execução disponível se o horário agendado passar enquanto o computador estiver desligado; não há execução instantânea durante a instalação.

## Agendamento semanal no Linux com systemd de usuário

1. Copie `zeroscript-self-improve.service` e `zeroscript-self-improve.timer` para `~/.config/systemd/user/`.
2. Edite `WorkingDirectory` e o caminho de `ExecStart` para a pasta real do projeto.
3. Se usar provedor remoto, crie `~/.config/zeroscript/improve.env` com `ZS_IMPROVE_API_BASE`, `ZS_IMPROVE_MODEL`, `ZS_IMPROVE_API_KEY` e, apenas se autorizar transferências automáticas, `ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1`; não versione o arquivo e restrinja com `chmod 600 ~/.config/zeroscript/improve.env`. O unit usa `EnvironmentFile` opcional.
4. Revise a presença de `--allow-source-upload` na linha `ExecStart`; remova essa opção para auditoria local sem transferência.
5. Execute:

```sh
systemctl --user daemon-reload
systemctl --user enable --now zeroscript-self-improve.timer
systemctl --user list-timers zeroscript-self-improve.timer
```

A agenda usa domingo às 03:00, atraso aleatório de até 30 minutos e recuperação de uma execução perdida. É um serviço do usuário: não usa `User=`, não requer root e limita a duração a quatro horas.

## macOS

Use `launchd` com `StartCalendarInterval` semanal, `WorkingDirectory` apontando para o projeto e `ProgramArguments` como lista (não como string de shell). Aponte para `python3 self_improve.py --repo <caminho> --mode propose --allow-source-upload` e defina `ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1` no ambiente do processo somente se autorizar transferências automatizadas. Sem a variável, a fonte não será enviada. Armazene as variáveis do provedor em um wrapper local com permissão `700` ou mecanismo de segredos do sistema; não grave a chave no plist, no repositório ou nos logs. O usuário deve carregar/ativar o LaunchAgent.

## Revisão de candidatos

Verifique o `report.json` e `proposal.diff`; confirme que a mudança trata um problema demonstrável, que não enfraquece permissões e que os testes de comportamento são executados numa sandbox apropriada. Não aplique o ZIP a uma instalação em uso sem revisão independente, testes e um plano de rollback. Uma geração semanal não é uma atualização automática da instalação ativa.
