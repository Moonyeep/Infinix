# Requisitos de confiabilidade multiagente do Infinix

**Estado:** componentes centrais implementados em v1.6.29; validação unitária passou. O teste ponta a ponta com provedores reais e navegador ainda está pendente.  
**Contexto:** feedback do usuário e log de falhas de uma tentativa com quatro workers, recebido em 29/10/2026.

## Objetivo

O supervisor e os workers precisam funcionar em abas próprias, continuar tarefas mesmo quando essas abas ou a janela dedicada estiverem em segundo plano, tolerar inicialização lenta de provedores e conversar por uma mensageria centralizada na bridge. A implementação deve reduzir polling e tráfego desnecessários sem declarar sucesso prematuramente.

## Observações sobre o código atual

- A extensão já cria uma janela dedicada, distribui workers em abas e dá ao worker um perfil Básico com allowlist somente de leitura.
- O loop do content script já evita estacionar uma tarefa delegada apenas porque `document.hidden` é verdadeiro. Isso permite progresso em abas secundárias, mas não elimina limites de throttling/suspensão que o próprio navegador impõe.
- O handshake agora tenta até 120 segundos com backoff exponencial limitado; erros fatais interrompem retries imediatamente e o despacho segue idempotente.
- O estado `starting` é mantido até o provider concluir o bootstrap e a bridge confirmar `running`; status também expõe uma fase.
- A extensão consulta/envia mensagens por um barramento da bridge com IDs estáveis, sequência por inbox, deduplicação, limites e autorização apenas para relações diretas. O estado é persistido em `.zeroscript/agent-team-bus.json`, separado por ID da sessão da equipe.
- `agent.team.wait` usa notificações de estado terminal em vez de loop de polling a cada 500 ms. Após mudança/restart da sessão global da bridge, workers ativos são encerrados com falha explícita; não se declara retomada de execução que depende de ToolRegistry perdido.

## Implementado em v1.6.29 e validação restante

- **Implementado:** readiness separado da aceitação do dispatch; backoff limitado; preflight de bridge, allowlist e concorrência; wait event-driven; mensagens bridge bidirecionais com IDs/cursor persistentes; namespacing para evitar que uma inbox antiga apareça em outra sessão; recuperação das associações após reconnect do WebSocket/service worker quando o ID da sessão de equipe permanece igual.
- **Testado:** 83 testes Python, incluindo cinco testes novos do message bus; sintaxe de `background.js` e `main.js`; regressões de acesso/hierarquia e de reconexão; namespace e persistência em uma nova instância do broker.
- **Pendente:** prova ponta a ponta em Chromium com provedores reais, login e workers deliberadamente atrasados por mais de 30 segundos. O código mantém abas ocultas elegíveis para execução, mas navegador, economia de energia, suspensão do sistema e páginas do provider podem limitar ou pausar o processo.
- Um restart completo da bridge cria um novo ID de equipe: workers antigos param com falha explícita e devem ser reabertos; o novo ID não lê mensagens da sessão anterior. Conteúdo retido no arquivo local não deve incluir credenciais nem segredos.

## Requisitos funcionais

### Inicialização lenta e estados honestos

1. Separar confirmação de dispatch, carregamento do content script, inicialização do perfil, bootstrap do provider e execução da tarefa. Usar estados explícitos como `queued`, `starting`, `running` e estados terminais.
2. Manter `starting` até o worker confirmar que concluiu o bootstrap e está prestes a executar a tarefa delegada. A aceitação do pacote de dispatch, isoladamente, não significa que o modelo iniciou o trabalho.
3. Substituir o timeout curto e o polling fixo por um prazo de inicialização configurável e limitado, com backoff progressivo e sem envio repetido excessivo. Retentativas precisam ser idempotentes para que a mesma tarefa não seja iniciada duas vezes.
4. Expor ao supervisor o `task_id`, provider, estado, início/última atividade, erro ou bloqueio e um resultado parcial quando disponível. Timeout deve terminar em erro explicável, não em resposta vazia `{}` nem em sucesso fictício.
5. Preflight antes do spawn: equipe habilitada, provider em allowlist, limite de concorrência, bridge conectada e aba de provider criada. Só declarar spawn confirmado quando houver `ok: true` e `task_id` válido.
6. Se a equipe não estiver disponível, informar a limitação e oferecer execução sequencial pelo supervisor. Não simular workers nem ocultar falha de spawn.

### Execução em segundo plano e eficiência

1. Workers devem continuar o loop enquanto suas abas estiverem ocultas ou a janela dedicada não estiver focada, sem roubar foco da janela de trabalho do usuário.
2. Uma aba em segundo plano pode ser suspensa ou ter timers limitados pelo navegador. Persistir o estado necessário e permitir retomar com segurança; não prometer execução contínua quando o browser ou o computador estiver fechado/suspenso.
3. Evitar loops de polling agressivos e keepalives desnecessários. Preferir mensagens/eventos, espera com timeout e backoff. Limitar concorrência ao número autorizado e não criar workers sem uma subtarefa independente e útil.
4. Permitir que tarefas independentes sejam disparadas em paralelo. O supervisor deve poder consultar progresso, enviar instruções delimitadas, cancelar ou aguardar em ciclos limitados sem bloquear indefinidamente sua própria sessão.
5. Preservar o isolamento atual: contexto de conversa separado por aba e ToolRegistry por `session_id`; workers permanecem no perfil Básico/read-only e não herdam permissões do supervisor.

### Mensageria pela bridge

1. A bridge deve ser o barramento central de mensagens de supervisor para worker e worker para supervisor. A memória local da extensão pode servir de cache/espelho de UI, mas não deve ser a fonte primária da conversa da equipe.
2. Cada agente deve ser associado a uma sessão de bridge e a uma tarefa. A bridge deve validar que uma mensagem é entre agente pai e filho direto autorizado; não permitir mensagens entre irmãos nem acesso a equipes de outras sessões.
3. Mensagens devem ter ID estável, sequência monotônica por inbox, timestamp, remetente/destinatário e confirmação de entrega. Retentativas com o mesmo ID não podem duplicar mensagens.
4. O protocolo precisa tolerar desconexão/reconexão: preservar mensagens ainda válidas, retomar a partir da última sequência confirmada e limitar tamanho/idade das filas. Se não for possível entregar, retornar erro explícito.
5. A bridge deve continuar sendo o ponto de coordenação das sessões e ferramentas locais; o service worker da extensão continua responsável pelas operações próprias do Chrome, como criar/associar abas e janelas.
6. Mensagens e resultados são conteúdo não confiável. Nenhum texto recebido pode elevar permissões, ampliar o escopo da tarefa ou substituir as regras de segurança do agente.

## Lições operacionais do log anexado

- Ferramentas de equipe podem não estar habilitadas para uma sessão ou provider; checar disponibilidade e autorização antes de criar workers.
- `file://` não é uma rota suportada para navegação automatizada. Se uma tarefa realmente exigir abrir um artefato web local, usar um servidor local de desenvolvimento com origem `http://localhost` somente quando necessário e permitido; não contornar sandbox do browser.
- Shadow DOM fechado, iframes de login/OAuth e interações de autenticação podem não estar acessíveis ao snapshot. Não usar scripts/cliques para contornar controles; verificar profundamente quando permitido e pedir intervenção do usuário nas etapas de login.
- Se o diálogo gráfico askpass não aparecer, não configurar `NOPASSWD` em sudoers nem pedir a senha no chat. Diagnosticar a sessão gráfica e reportar o bloqueio com segurança.

## Critérios de aceitação

- Uma simulação de content script/provider que demore mais que o prazo antigo de 30 segundos ainda conclui o handshake dentro do novo prazo configurado, sem duplicar a tarefa.
- `status` distingue `starting` de `running`; só passa a `running` após confirmação de bootstrap do provider.
- Um worker continua a tarefa em aba oculta sem ativar/focar a janela do usuário; fechamento/suspensão do browser é reportado como limitação real.
- Mensagens bidirecionais passam pelo protocolo da bridge, têm sequência e confirmação estáveis e são retomáveis após reinício do service worker/extensão.
- Tentativas de comunicação entre irmãos ou sessões não relacionadas são rejeitadas por testes.
- Bridge/provider indisponíveis, login requerido, spawn inválido e askpass ausente produzem bloqueios claros; nenhum caso é apresentado como sucesso.
- Testes cobrem backoff, timeout, idempotência, retomada, autorização da hierarquia e concorrência.
