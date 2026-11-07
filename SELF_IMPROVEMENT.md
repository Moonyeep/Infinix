# Protocolo de estudo e autoaperfeiçoamento

O protocolo é separado dos perfis de capacidade e pode ser iniciado pela opção **Estudo e autoaperfeiçoamento** no seletor da sessão ou por solicitação do usuário em uma conversa suportada. O modo de estudo usa o perfil Básico. `agent.self_improve.run` executa sem aprovação por ciclo, com limite de quatro horas por chamada; a extensão e o bridge mantêm a requisição aberta nesse prazo. A permissão vale apenas para este pipeline isolado, não para terminal, navegador ou edição da instalação ativa. Regras `DENY` continuam prevalecendo.

## Ciclo de auditoria

`mode=audit` executa a suíte de baseline da versão atual, sem envio de código, e grava um relatório JSON em `.zeroscript/improvement-reports/`. Instalações extraídas de ZIP são aceitas. Para worktrees Git, o ciclo recusa qualquer estado staged, unstaged ou não rastreado, evitando ocultar mudanças locais.

## Ciclo de proposta

`mode=propose` requer as variáveis `ZS_IMPROVE_API_BASE`, `ZS_IMPROVE_MODEL` e, para provedores remotos, `ZS_IMPROVE_API_KEY`. Para autorizar o envio não interativo, configure uma vez `ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1` no ambiente do usuário. Sem essa variável, nenhum código é transferido. O endpoint precisa ser HTTPS; HTTP só é aceito para loopback. Arquivos `.env`, `config.json` local, caminhos de chave privada e diretórios secretos conhecidos são excluídos; padrões comuns de segredos são redigidos.

O diff é aplicado apenas em worktree ou cópia descartável. Alterações a `PolicyBroker`, workspace, executores, ferramentas do registry, bridge, aprovação, browser background, manifest, scheduler ou ao próprio protocolo são rejeitadas pelo modelo. Depois, o pipeline atualiza apenas os campos de versão da cópia candidata (manifest da extensão e `BRIDGE_VERSION`) em conjunto. A versão ativa nunca é editada. Se a análise justificar uma mudança de baixo risco, o ciclo produz `proposal.diff`, `model-proposal.diff`, `review-notes.md`, `report.json` e um ZIP com a próxima versão candidata em `.zeroscript/improvement-candidates/<execução>/`. O `config.json` local do bridge, arquivos `.env` e credenciais conhecidas são excluídos do snapshot e do ZIP.

O candidato não é executado no host: somente AST/sintaxe Python, sintaxe JavaScript se Node estiver disponível e JSON são verificados. Testes de comportamento da proposta ficam explicitamente pendentes para revisão e execução numa sandbox apropriada. `review_required` não significa que a proposta foi provada correta. Não existe merge, publicação, atualização automática ou rollback implícito.

Se não há endpoint configurado, a execução não simula uma melhoria: grava `driver_unconfigured`. Se o usuário não autorizou o envio, grava `source_upload_not_authorized`. Saídas de baseline são limitadas e passam por redaction; a chave da API não é gravada no relatório.

## Execução manual e agendamento

```text
python self_improve.py --repo <pasta-do-projeto> --mode audit
python self_improve.py --repo <pasta-do-projeto> --mode propose --allow-source-upload
```

Para ativar o ciclo semanal nativo, instale a tarefa do Windows ou configure os units do Linux conforme `schedules/README.md`. O agendador executa como usuário sem privilégios elevados, aos domingos às 03:00, com limite de quatro horas. A instalação da tarefa exige uma ação explícita no computador; este pacote não ativa um agendamento remoto.

## Invariantes rígidos

1. `DENY` prevalece sobre qualquer perfil; `self_improve.run` não pede aprovação por ciclo, mas fica confinado ao pipeline isolado.
2. Nenhuma saída de modelo é uma instrução confiável; patch inválido, caminho perigoso ou arquivo protegido bloqueia a proposta.
3. Nenhum arquivo ativo é substituído, nenhum candidato é automaticamente executado e nenhum resultado é publicado.
4. Segredos, cookies, credenciais e chaves não devem ser solicitados ou gravados em prompt, relatório, repositório ou argumento de processo.
5. Se baseline falhar, endpoint estiver indisponível, validação estática for incompleta ou o diff não se aplicar, a execução registra o estado e não promove nada.
6. A evolução é limitada por evidência, testes e revisão. “Sempre melhor” ou “perfeição” não pode ser garantido por um ciclo automático.
