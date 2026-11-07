# Infinix v1.6.18 - Enhanced Edition

## Versao Aprimorada com Sistema de Permissões Expandidas

Esta versao inclui melhorias significativas que transformam o agente em um assistente de sistema completo.

---

## Conteudo do Pacote

### Codigo Principal
- agent_core/ - Nucleo do agente com todas as melhorias
- bridge.py - Bridge WebSocket
- zeroscript-extension/ - Extensao do navegador

### Melhorias (Pasta ENHANCEMENTS/)
1. improvement_patch.diff - Melhorias de resiliencia da API
2. agent_core/permissions.py - Sistema de permissoes granulares
3. Documentacao completa (4 arquivos .md)
4. Testes validados (21 testes no total)

---

## Novidades Principais

### 1. Sistema de Permissoes Granulares

4 perfis: Sandbox, Developer, Power User, System Admin
10 escopos: workspace, user_home, system_read, system_write, process_full, network_full, registry_read, registry_write, service_control, desktop_control

### 2. Capacidades Expandidas

Com perfil adequado:
- Ler/escrever arquivos em QUALQUER lugar
- Executar QUALQUER comando (com validacoes)
- Gerenciar processos e servicos
- Acessar registro Windows
- Controlar aplicacoes desktop

### 3. Melhorias no Auto-Aperfeicoamento

- Retry com backoff exponencial
- Validacao estrutural rigorosa
- Metricas de desempenho
- Mensagens de erro enriquecidas

---

## Seguranca

### Protecoes
1. Caminhos protegidos nunca modificaveis (Windows, Program Files, etc.)
2. Comandos destrutivos sempre bloqueados
3. Confirmacoes obrigatorias para perfis elevados
4. Auditoria completa de todas as acoes

---

## Como Usar

### Ativando Permissoes Expandidas

Metodo 1: Variavel de ambiente
set ZS_PERMISSION_PROFILE=power_user

Metodo 2: Dinamicamente
registry.call("permissions.set_profile", {
    "profile": "power_user",
    "confirmation_code": "CONFIRM_POWER_USER"
})

### Exemplos

Acessar arquivo fora do workspace:
result = registry.call("file.read", {"path": "C:\\Users\\Arthur\\Documents\\notes.txt"})

Executar comando do sistema:
result = registry.call("terminal.run", {"shell": "powershell", "command": "Get-Process"})

---

## Testes

Todos os testes validados:
- 9 testes para auto-aperfeicoamento
- 12 testes para sistema de permissoes
Total: 21/21 passando

Para executar:
cd ENHANCEMENTS
python test_standalone.py
python test_permissions.py

---

## Documentacao Detalhada

- EXPANDED_CAPABILITIES_PROPOSAL.md - Proposta tecnica (17.6 KB)
- RESUMO_PERMISSOES.md - Guia pratico (8.3 KB)
- IMPROVEMENT_PROPOSAL.md - Melhorias API (6.3 KB)
- README_PROPOSTA.md - Resumo executivo (4.8 KB)

---

## Avisos Importantes

1. Perfil padrao: sandbox (maxima seguranca)
2. Perfis elevados requerem confirmacao explicita
3. Faca backup antes de elevar permissoes
4. Revise logs regularmente
5. Pode reduzir permissoes instantaneamente

---

## Rollback

Se algo der errado:
1. Reduzir permissoes: registry.call("permissions.set_profile", {"profile": "sandbox"})
2. Restaurar backup em .zeroscript/backups/
3. Reinstalar versao anterior se necessario

---

Versao: 1.6.18 Enhanced Edition
Data: 23 de Outubro de 2026
Status: Validado e pronto para producao
Testes: 21/21 passando