# Windows: conta administrativa suspeita e CMD bloqueado

## Objetivo

Separar quatro hipóteses distintas: uma conta local nova; um principal adicionado ao grupo Administradores; um perfil/pasta de usuário; ou uma restrição de execução do CMD. Nenhum item isolado confirma invasão. Colete antes de mudar estado e registre usuário/contexto/arquitetura do PowerShell.

## Coleta PowerShell read-only

Execute com a conta/sessão atual, sem elevação automática. Se uma consulta falhar, registre o erro como lacuna.

```powershell
# Versão e bitness da sessão
$PSVersionTable
[pscustomobject]@{
  Is64BitOS = [Environment]::Is64BitOperatingSystem
  Is64BitPowerShell = [Environment]::Is64BitProcess
  ProcessArchitecture = $env:PROCESSOR_ARCHITECTURE
  Wow64Architecture = $env:PROCESSOR_ARCHITEW6432
}

# Contas locais: nome, estado, SID, último logon e origem quando disponível
Get-LocalUser | Select-Object Name,Enabled,SID,LastLogon,PrincipalSource

# Membros do grupo local Administradores via SID conhecido do grupo
Get-LocalGroupMember -SID ([System.Security.Principal.SecurityIdentifier]'S-1-5-32-544') |
  Select-Object Name,ObjectClass,PrincipalSource,SID

# Perfis locais são outro inventário; mostrar SID/caminho/estado, sem apagar
Get-CimInstance Win32_UserProfile |
  Select-Object SID,LocalPath,Loaded,Special

# Política do usuário atual que pode bloquear cmd.exe e arquivos .cmd/.bat
Get-ItemProperty 'HKCU:\Software\Policies\Microsoft\Windows\System' `
  -Name DisableCMD -ErrorAction SilentlyContinue

# Resolução e assinatura do executável normal do CMD
$cmd = Join-Path $env:SystemRoot 'System32\cmd.exe'
$env:ComSpec
Test-Path $cmd
if (Test-Path $cmd) { Get-AuthenticodeSignature $cmd | Select-Object Status,@{n='Signer';e={$_.SignerCertificate.Subject}} }

# Valor Debugger da Image File Execution Options, se existir; é um indicador que exige validação
Get-ItemProperty 'HKLM:\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\cmd.exe' `
  -Name Debugger -ErrorAction SilentlyContinue
```

`Get-LocalUser` inclui contas internas padrão, contas criadas localmente e contas locais ligadas a Microsoft accounts. `Get-LocalGroupMember` lista membros locais e permite identificar origem quando suportada. A documentação Microsoft informa que o módulo `Microsoft.PowerShell.LocalAccounts` não está disponível em PowerShell de 32 bits num sistema de 64 bits; se a bridge ou terminal estiver nessa bitness, não concluir que a lista vazia/incompleta é confiável. Detectar a arquitetura real do SO e do processo (x86, x64, ARM64 ou outra) antes de escolher PowerShell; não inferir ARM pelo relato. Repetir somente numa sessão nativa compatível e autorizada.

## Interpretação cuidadosa

- Um SID local terminando em `-500` é normalmente a conta Administrador embutida; sua existência, nome ou estado não prova invasão. Confirme o SID completo, origem, estado e histórico conhecido com o proprietário/TI.
- A associação ao grupo Administradores informa privilégio local, mas não autoria, quando foi criada ou se é maliciosa. Compare com contas legítimas de suporte, Microsoft account, Entra/AD e políticas da organização.
- Um perfil em `C:\Users\...` e uma conta/principal são objetos diferentes. A tela Microsoft de exclusão de perfil remove um perfil do dispositivo; isso não equivale a remover o usuário do grupo local. Confirmar backup e alvo antes de apagar perfil, especialmente se contiver arquivos pessoais.
- A política `DisableCMD` é descrita pela Microsoft como política de usuário que impede o CMD interativo e também pode controlar execução de arquivos batch. Ela pode explicar o sintoma sem substituição do executável e sem prova de invasão; confirmar se é política corporativa/gerenciada antes de propor alteração.
- `ComSpec` diferente, assinatura inesperada ou valor IFEO `Debugger` são indícios para investigação, não prova autônoma de malware. Verificar arquivo, assinatura, GPO/MDM e histórico com profissional autorizado.
- Esta coleta não altera política, Registro, grupo, conta, perfil ou assinatura. No ZeroScript, `windows_disable_local_account` pode **desativar**, nunca excluir, uma conta local confirmada pelo SID exato. No perfil Amplo, já autorizado pelas duas confirmações iniciais, a ação executa sem aprovação adicional por chamada; Básico/Desenvolvimento seguem seus prompts de perfil. A proteção recusa o SID `-500`, a conta que executa a bridge, um alvo fora do grupo Administradores e a operação se não houver outro administrador local habilitado verificável. A ação não encerra sessões existentes, não remove o perfil e não trata contas de domínio/Entra. Falha/bitness incompatível significa que não se deve prosseguir.
- Não confundir conta com perfil nem apagar dados como substituto da desativação. Se a identidade/localidade do alvo estiver ambígua ou não houver autoridade clara para o dispositivo, não adivinhar: esclarecer isso antes de agir. O perfil Amplo elimina confirmações repetidas, não a verificação técnica do alvo nem os limites da ação.

## Fontes oficiais

- [Get-LocalUser — Microsoft Learn](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.localaccounts/get-localuser?view=powershell-5.1)
- [Get-LocalGroupMember — Microsoft Learn](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.localaccounts/get-localgroupmember?view=powershell-5.1)
- [Policy CSP: Prevent access to the command prompt — Microsoft Learn](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-admx-shellcommandpromptregedittools)
- [Delete a user profile in Windows — Microsoft Support](https://learn.microsoft.com/en-us/troubleshoot/windows-server/user-profiles-and-logon/delete-user-profile)
- [How User Account Control works — Microsoft Learn](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/user-account-control/how-it-works)
