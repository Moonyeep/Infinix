# Instalação no Linux

Infinix funciona no Linux usando a extensão em um navegador baseado em Chromium (Chrome, Chromium ou Edge) e a bridge local em Python. Roblox Studio é opcional; o General Agent não depende dele.

## Instalar e iniciar

1. Baixe o ZIP oficial do projeto e extraia-o.
2. No Chrome/Chromium, abra `chrome://extensions`; no Edge, abra `edge://extensions`.
3. Ative **Developer mode**, clique em **Load unpacked** e selecione a pasta `zeroscript-extension` extraída.
4. Abra um terminal na pasta raiz do projeto e execute:

```bash
chmod +x start_agent.sh
./start_agent.sh
```

O launcher detecta Python 3.10 ou superior, cria um `.venv` dentro do projeto e instala automaticamente `websockets` sem alterar o Python global. Se o sistema só tiver Python antigo (por exemplo, Python 3.8 no Ubuntu 20.04/Mint baseado no Focal) ou não tiver suporte a `venv`, baixa `uv` e um runtime Python 3.12 para diretórios do seu usuário, depois continua a instalação local. **Não usa `sudo`, não roda `apt-get update` e não modifica pacotes do sistema.** É necessário ter `curl` ou `wget` e acesso à internet na primeira execução. Não é necessário ativar o ambiente virtual manualmente. Mantenha o terminal aberto enquanto usar o agente. Se o ZIP removeu a permissão executável, `chmod +x start_agent.sh` é esperado; `bash start_agent.sh` também funciona.

O serviço escuta somente em `127.0.0.1` por padrão. Configurações opcionais: `PYTHON=/caminho/python3` (3.10+), `ZS_VENV=/caminho/venv`, `ZS_BRIDGE_PORT=17613`, `ZS_AGENT_WORKSPACE=/caminho` e `ZS_AGENT_WORKSPACE_ROOTS=/caminho1:/caminho2`.

## Navegador Playwright opcional

O navegador do agente é desligado por padrão e usa um contexto novo do Chromium headless; ele não se conecta ao perfil pessoal do Chrome. Para habilitá-lo, antes de iniciar a bridge:

```bash
export ZS_BROWSER_ENABLED=1
export ZS_BROWSER_HOSTS="example.com,docs.python.org"
./start_agent.sh
```

Com essa opção, o launcher também instala Playwright e Chromium no venv local. Substitua a lista de hosts por domínios exatos autorizados; lista vazia não permite navegação. Redirecionamentos fora da allowlist e destinos locais/privados ficam bloqueados por padrão. Clique/preenchimento requer ainda `ZS_BROWSER_ALLOW_EXTERNAL_EFFECTS=1`; os limites do perfil da sessão continuam valendo. Valores preenchidos são omitidos dos logs locais.


## Terminal e diagnóstico local

Com `ZS_AGENT_ENABLED=1` (configuração do `start_agent.sh`), a bridge Linux expõe `terminal.run` com Bash/sh e também zsh ou PowerShell Core (`pwsh`) quando instalados. Se `sudo` estiver presente, também oferece `terminal.run_as_admin`: quando a autenticação for necessária, o próprio `sudo` chama um diálogo askpass do desktop (ssh-askpass, Zenity, YAD ou KDialog). Digite a senha apenas nesse diálogo do sistema — ela é enviada diretamente a `sudo`, nunca ao modelo, aos argumentos de ferramenta ou aos logs, e não é salva pelo Infinix. O `sudo` pode manter a autorização em cache pelo tempo definido na configuração do sistema; use `sudo -k` para revogá-la antes. Em modo Amplo, após as duas confirmações iniciais, o agente pode executar comandos administrativos sem aprovação por chamada; isso equivale a poder alterar o sistema como root. No modo Básico/Desenvolvimento, as regras de aprovação desses perfis continuam valendo. Se não houver uma sessão gráfica/askpass, o agente informa que não conseguiu abrir o diálogo; não cole a senha no chat nem use `sudo` interativo pelo terminal da bridge.

O grupo `diagnostics.*` oferece consultas locais limitadas a processos, serviços/systemd, endereços/rotas/listeners, logs recentes, inicialização, espaço em disco e inventário de ferramentas. A coleta pode revelar nomes de usuário, caminhos, endereços e eventos; os registros locais guardam metadados/contagens, não o conteúdo bruto do diagnóstico. Dados retornados ainda são visíveis à conversa de IA.

Após as duas confirmações iniciais do perfil Amplo, ferramentas e ações seguem a autorização da sessão sem prompts por chamada; Básico/Desenvolvimento seguem seus prompts de perfil. No Linux, scans ClamAV exigem `clamscan` instalado e um caminho específico; o launcher não instala ClamAV nem executa remoção/quarentena. Reparos Windows só funcionam no Windows e requerem o privilégio já existente da bridge; não há bypass de UAC. Ferramentas ausentes, falhas de permissão e cobertura parcial devem ser reportadas como não verificadas, não como resultado limpo.
