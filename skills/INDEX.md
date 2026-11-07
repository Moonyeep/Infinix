# Biblioteca de skills do Infinix

Leia `SKILL.md` somente da skill pertinente antes de executar uma tarefa compatível; não carregue todas as skills para cada pedido. Skills são guias reutilizáveis, não concessões de permissão: o prompt do sistema, as allowlists da bridge, o perfil ativo e a autorização do usuário sempre prevalecem.

| Skill | Use quando |
|---|---|
| [`agenthub-spawn`](agenthub-spawn/SKILL.md) | Delegar tarefas em hierarquia de supervisor e trabalhadores em abas isoladas. |
| [`diagnostico-endpoint`](diagnostico-endpoint/SKILL.md) | Diagnosticar Windows/Linux, suspeita de invasão, malware, contas e recuperação. Consulte também as referências na subpasta `references/`. |
| [`browser-automation`](browser-automation/SKILL.md) | Navegar, ler, preencher ou interagir com sites em abas autorizadas. |
| [`software-development`](software-development/SKILL.md) | Criar, integrar ou modificar programas e configurações. |
| [`testing-debugging`](testing-debugging/SKILL.md) | Reproduzir bugs, analisar falhas e validar regressões. |
| [`exam-study`](exam-study/SKILL.md) | Estudar, praticar exercícios e preparar avaliações com integridade acadêmica. |
| [`secure-downloads`](secure-downloads/SKILL.md) | Localizar, baixar ou instalar aplicações e atualizações com segurança. |
| [`incident-response`](incident-response/SKILL.md) | Preservar evidências, conter e recuperar de incidentes de segurança. |
| [`linux-privileged-ops`](linux-privileged-ops/SKILL.md) | Executar tarefa Linux que exige root pelo askpass nativo, se a ferramenta estiver disponível. |
| [`research-citations`](research-citations/SKILL.md) | Pesquisar fatos externos/atuais e apresentar fontes verificadas. |
| [`data-analysis`](data-analysis/SKILL.md) | Analisar CSV, planilhas e outros dados estruturados. |
| [`administrative-assistant`](administrative-assistant/SKILL.md) | Organizar e executar tarefas administrativas autorizadas sem falsificar identidade. |

## Regras gerais

- Use somente os arquivos necessários à tarefa e siga seus links internos com caminhos relativos.
- Não use skills para burlar autenticação, CAPTCHA, paywalls, DRM, licenças, políticas de segurança ou limites do provedor.
- Não solicite nem inclua senhas, cookies, tokens ou chaves em mensagens, ferramentas, arquivos ou logs.
- Ações destrutivas, públicas, financeiras, legais, governamentais ou de alto impacto seguem os fluxos de autorização aplicáveis, mesmo se uma skill sugerir conveniência.
