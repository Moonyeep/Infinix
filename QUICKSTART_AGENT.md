# Infinix Agent — tutorial rápido

Este pacote contém a extensão do Infinix, o bridge local, o núcleo de agente geral com permissões e o ciclo de autoaperfeiçoamento. O modo padrão não inicia nem exige Roblox Studio. Extraia o ZIP inteiro antes de iniciar; não execute scripts diretamente dentro da visualização do ZIP.

## 1. Requisitos

Use Chrome ou Edge e Python 3.9 ou mais recente. No Windows, `Start_Agent.bat` procura `py`, `python`, `python3` e locais comuns de instalação; se não encontrar Python, pode pedir confirmação para instalá-lo com winget. Sem winget, o launcher mostra o link de instalação e a opção Add Python to PATH. A primeira execução instala automaticamente a biblioteca Python `websockets`. O agente não precisa de API key para usar os providers de chat que o Infinix já suporta.

## 2. Carregar a extensão

1. Extraia o ZIP para uma pasta permanente.
2. Abra `chrome://extensions` no Chrome ou `edge://extensions` no Edge.
3. Ative **Developer mode / Modo do desenvolvedor**.
4. Clique em **Load unpacked / Carregar sem compactação**.
5. Selecione a pasta `zeroscript-extension` dentro da pasta extraída.
6. Depois de qualquer atualização, clique no botão de recarregar da extensão e recarregue a aba do chat.

## 3. Iniciar o bridge e o agente

No Windows, execute `Start_Agent.bat`.

No macOS, execute `Start_Agent.command`. Se o macOS bloquear o arquivo, permita-o em **System Settings → Privacy & Security → Open Anyway**.

No Linux, abra um terminal na pasta extraída e execute:

```bash
chmod +x Start_Agent.command start_agent.sh
./start_agent.sh
```

Mantenha a janela aberta. O bridge usa `127.0.0.1:17613`. O popup da extensão deve mostrar o bridge conectado e o agente local habilitado. A tela deve indicar `General Agent`, não Roblox Studio.

## 4. Usar pelo chat

Abra uma página suportada, como DeepSeek, ChatGPT, Gemini, Kimi, GLM, Qwen, Arena ou Meta AI. Inicie uma nova conversa e use o botão de sessão do Infinix.

Antes de iniciar, escolha um perfil: **Básico** (leitura automática; edições e comandos pedem aprovação), **Desenvolvimento** (edições nas raízes configuradas; comandos pedem aprovação) ou **Amplo**. Amplo exige duas confirmações separadas no início; depois delas, ferramentas locais e ações do navegador executam sem aprovações por ação, incluindo comandos arbitrários de terminal. Há também **Estudo e autoaperfeiçoamento**, um modo operacional separado que mantém o perfil Básico e executa o ciclo isolado sem aprovação por chamada. Isso não dá ao protocolo acesso arbitrário ao terminal/navegador nem altera arquivos ativos. O envio remoto de fonte só fica habilitado após configurar uma única vez `ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1`. O candidato nunca é instalado automaticamente. O botão **Parar** interrompe o loop do agente.

O catálogo de ferramentas locais aparece com o prefixo `agent.`. Exemplos de capacidades:

- `agent.file.read`: ler arquivo dentro das raízes permitidas.
- `agent.file.create`: criar arquivo UTF-8 novo; falha se o destino já existir, evitando sobrescrita acidental.
- `agent.file.write`: criar ou substituir arquivo UTF-8 atomicamente; ao substituir, salva backup e retorna diff. Ambas usam a política `workspace.write` e ficam confinadas às raízes autorizadas.
- `agent.file.patch`: aplicar uma alteração exata com backup automático; aprovação em Básico, automática em Desenvolvimento/Amplo dentro das raízes configuradas. O launcher inclui a pasta do agente, `Downloads`, `Desktop` e `Documents`.
- `agent.process.test`: executar um teste allowlisted; em Amplo não mostra aprovação por ação.
- `agent.terminal.run` (bridge no Windows): executar um comando em `cmd`, Windows PowerShell ou `pwsh` se instalado. Escolha o shell e passe um comando; `cwd` e timeout são opcionais. Em Amplo executa sem prompt por comando, sob a conta Windows que iniciou o bridge, e pode acessar caminhos fora do workspace. O timeout máximo é 120 segundos.
- `agent.browser.tabs.list`: listar abas abertas, incluindo `id`, `windowId`, título e URL.
- `agent.browser.snapshot`: ler elementos visíveis e texto da página. `deep: true` percorre Shadow DOM aberto; `wait_ms` aguarda estabilidade e `selector_hint` espera um seletor CSS aparecer. A aba-alvo é ativada por padrão.
- `agent.browser.click`: clicar em um ID; em Amplo todas as ações de clique são automáticas. Passe o mesmo `tabId` usado no snapshot.
- `agent.browser.type`: digitar em um ID; em Amplo a digitação é automática. Passe o mesmo `tabId` usado no snapshot.
- `agent.browser.wait`: aguardar texto ou seletor visível, com timeout limitado.
- `agent.browser.scroll`: rolar a página ou container em passos e então tirar outro snapshot; útil para listas virtualizadas que só montam itens próximos à viewport.
- `agent.browser.press_key`: enviar eventos de teclado sintéticos, incluindo Enter, Tab, Escape e setas; em Amplo não há aprovação por tecla.
- `agent.browser.screenshot`: ferramenta opcional mostrada apenas quando o modelo atual aceita imagens; use como fallback visual quando DOM/texto não bastarem.
- `agent.browser.click_at`: clique por coordenadas após screenshot; informe `coordinate_space: "image"` para coordenadas em pixels da imagem. Em Amplo não há aprovação por clique.

Em **Básico** e **Desenvolvimento**, ações que exigem aprovação mostram um modal sobre a própria conversa da IA. Em **Amplo**, a autorização é dada uma vez por sessão nas duas confirmações iniciais para as ferramentas normais. `agent.self_improve.run` é limitado ao pipeline isolado e não pede aprovação por ciclo; uma regra `DENY` explícita ainda pode bloqueá-lo. Os resultados continuam retornando à IA.

O agente ativa e carrega a aba indicada antes de snapshot/interação e volta à conversa da IA para continuar o raciocínio. Use `active: false` somente quando o site funcionar corretamente em segundo plano. Listas virtualizadas expõem apenas os itens montados naquele momento: role em passos e faça novo snapshot antes de escolher um item. `deep:true` alcança apenas Shadow DOM aberto (roots fechados não são acessíveis por scripts de conteúdo). `press_key` envia eventos DOM sintéticos, não teclas confiáveis do sistema operacional; alguns sites podem ignorá-los, então confirme o resultado com novo snapshot. `click_at` usa CSS pixels ou escala pixels da imagem por `devicePixelRatio`. Em Amplo, opere estritamente dentro da tarefa solicitada; não procure ou revele senhas, tokens, cookies ou chaves, e não tente contornar permissões do Windows. A saída bruta do terminal e o comando não são gravados no log de eventos local.

## 5. Roblox Studio (opcional)

O agente geral não precisa de Roblox Studio. Para usar também as ferramentas Roblox, execute `Start_Roblox.bat`; nesse modo opcional, abra um Place e habilite **Assistant → Manage MCP Servers → Enable Studio as MCP Server**. O canal Roblox continua separado das ferramentas `agent.*`.

## 6. Limites atuais do browser

O snapshot DOM e as ações de browser são carregados nas páginas permitidas pelo manifesto atual. Para trabalhar em uma aba de outra janela, chame `agent.browser.tabs.list`, escolha o `id` numérico da aba alvo e informe `tabId` em `agent.browser.snapshot`; use esse mesmo `tabId` nas ações `click`/`type`. Sem `tabId`, a chamada usa a aba do chat que a originou (ou a aba atual como fallback), não necessariamente a janela que você pretendia. O controle universal de todas as páginas não é ativado automaticamente. Senhas, códigos, pagamentos, uploads, exclusões e envios devem permanecer sob takeover/aprovação humana.

Páginas internas do navegador, como `chrome://extensions` e `chrome-extension://...`, são protegidas pelo próprio Chrome/Edge e não são destinos navegáveis pela automação. Para instalar/atualizar Infinix ou configurar Tampermonkey, use a interface do navegador manualmente. No modo padrão, Tampermonkey não é necessário: carregue `zeroscript-extension` por **Load unpacked / Carregar sem compactação**.

## 7. Testar a instalação

Na pasta do projeto:

```bash
python3 -m unittest -q test_agent_core.py test_agent_team_bridge.py test_improvement.py test_session.py test_browser.py test_browser_permissions.py test_loop.py
node --check zeroscript-extension/background.js
node --check zeroscript-extension/core/main.js
node zeroscript-extension/test-background-reconnect.js
node zeroscript-extension/test-agent-team.js
node --check zeroscript-extension/popup.js
node zeroscript-extension/test-parser.js
```

Para listar ferramentas:

```bash
python3 infinix_agent.py --workspace . tools
```

## 8. Autoaperfeiçoamento semanal

Na UI, selecione **Estudo e autoaperfeiçoamento**; em qualquer conversa suportada também é possível pedir `execute o protocolo de autoaperfeiçoamento`. O ciclo não pede aprovação por chamada. A auditoria não envia código. Para propostas remotas sem prompts recorrentes, configure uma vez `ZS_IMPROVE_API_BASE`, `ZS_IMPROVE_MODEL`, `ZS_IMPROVE_API_KEY` e `ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1` no ambiente do usuário, após decidir que aceita enviar snapshots sanitizados ao provedor. Sem a última variável, nenhum código sai da máquina. Avalie a política de privacidade do endpoint antes de ativá-la.

Auditoria local, sem envio:

```bash
python3 self_improve.py --repo . --mode audit
```

Para gerar um candidato isolado, use `python3 self_improve.py --repo . --mode propose --allow-source-upload`. O pipeline não executa código gerado, não altera a instalação ativa e deixa diff/ZIP em `.zeroscript/improvement-candidates/`; a execução de testes comportamentais da proposta e a revisão continuam necessárias. Para configurar a tarefa nativa semanal, consulte `schedules/README.md`.

## 9. Solução de problemas

**Bridge offline:** mantenha o launcher aberto, confirme Python e execute novamente. Se a porta 17613 estiver ocupada, encerre o processo antigo ou defina `ZS_BRIDGE_PORT` nos launchers.

O background da extensão tenta reconectar com espera crescente quando o bridge volta a responder. O launcher Windows também tenta reiniciar o processo após encerramentos inesperados; depois de várias falhas, pare para evitar loop infinito. Consulte `logs/bridge_debug.log` e o console do service worker da extensão. Uma chamada que já começou antes da queda pode ter concluído no bridge mesmo se a resposta não chegou; verifique o resultado antes de repeti-la.

**Ferramentas locais não aparecem:** confirme que o launcher usado é `Start_Agent.bat`, `Start_Agent.command` ou `start_agent.sh`, recarregue a extensão e recarregue a página do chat.

**Popup mostra aprovação antiga:** feche e reabra o popup; aprovações pendentes são descartadas quando a conexão com o bridge cai.

**Browser snapshot vazio:** a extensão só observa elementos visíveis e interativos da página atual. Recarregue a aba e tente novamente.

**Não execute dentro do ZIP:** extraia todo o conteúdo primeiro, pois a extensão e o bridge precisam dos arquivos vizinhos.

**OpenJarvis / uv / MSVC:** não são dependências deste pacote e não são instalados pelo Infinix. Se estiver configurando OpenJarvis separadamente, use um ambiente virtual com uma versão Python suportada pelo OpenJarvis (3.10–3.13, conforme a distribuição usada), feche processos que estejam usando `uv.exe` antes de atualizá-lo e valide a instalação do Visual Studio Build Tools em um Developer Command Prompt. Não é necessário alterar a política de execução do PowerShell para iniciar o Infinix; evite mudanças globais de política.

## Segurança

O agente lê páginas como dados, não como ordens. Ainda assim, revise ações importantes. Nunca coloque tokens, cookies, senhas ou códigos no arquivo `.env` ou em mensagens. O `PolicyBroker`, o workspace confinado, a aprovação da extensão, o log de eventos e o rollback devem permanecer ativos.
