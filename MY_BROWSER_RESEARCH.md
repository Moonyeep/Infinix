# Pesquisa: Manus My Browser

## Manus

A página oficial `https://manus.im/my-browser` descreve autorização, instalação da extensão, abertura de uma nova aba e supervisão. O aviso recomenda fechar abas sensíveis para revogar autorização e parar diante de dúvida. A página não publica repositório, código-fonte ou licença de software.

O anúncio oficial `https://manus.im/blog/manus-browser-operator` descreve uma extensão proprietária que opera no navegador local autenticado. Os padrões úteis são: aba dedicada por tarefa, grupo de abas nomeado, autorização de sessão, takeover manual, interrupção fechando a aba, log de ações e separação entre browser cloud e browser local. O próprio anúncio informa que interações complexas como drag-and-drop e formulários de várias etapas ainda podem falhar.

A conclusão é que não há source público verificável da extensão Manus My Browser nas páginas oficiais consultadas. O link de instalação aponta para a Chrome Web Store, não para um repositório aberto. Não devemos extrair, copiar ou redistribuir o bundle proprietário.

## Alternativas com source público

Nanobrowser (`https://github.com/nanobrowser/nanobrowser`) é Apache-2.0 e documenta side panel, grupos de abas, modos Ask/Auto, permissões por site, confirmação para submit/send/delete/upload, takeover para senha/CAPTCHA, memória, histórico e browser control layer com IDs de elementos estáveis. A camada usa `chrome.debugger`, Puppeteer e validações de visibilidade/estabilidade antes de agir.

AIPex (`https://github.com/AIPexStudio/AIPex`) é MIT e documenta um daemon local WebSocket, extensão executando ações por APIs do navegador, snapshots DOM antes de visão, UIDs estáveis, MCP bridge e CLI. O fluxo `MCP -> WebSocket -> extensão -> browser` é diretamente compatível com a ideia de integrar um browser provider ao bridge do Infinix.

## Decisões para o Infinix

Reutilizar legalmente os padrões de autorização por sessão, aba dedicada, grupos por tarefa, stop/kill switch, audit log, Ask/Auto por site, takeover para autenticação/CAPTCHA e IDs estáveis de elementos. Clonar os repositórios Apache-2.0/MIT em uma área de referência antes de adaptar código. Não copiar o bundle Manus nem tentar contornar a autorização do usuário.

## Fontes

- https://manus.im/my-browser
- https://manus.im/blog/manus-browser-operator
- https://github.com/nanobrowser/nanobrowser
- https://github.com/AIPexStudio/AIPex
