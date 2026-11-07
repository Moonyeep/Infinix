# Resposta a incidente e triagem Linux

## Incidente em endpoint

1. Registrar relato, horário, mensagens, sintomas, ativos e responsável autorizador. Preservar logs e evidências disponíveis; não apagar nem reiniciar por reflexo.
2. Em malware/ransomware ativo, orientar desconexão da rede pelo proprietário ou pela equipe de IR para conter propagação. Em organização, coordenar isolamento; desligar pode perder evidência volátil e não deve ser automatizado.
3. Usar primeiro telemetria e consultas read-only. Distinguir resultado ausente de acesso negado, log indisponível, retenção expirada e ferramenta não instalada.
4. Usar dispositivo conhecido como limpo para trocar credenciais potencialmente expostas e revogar sessões. Não digitar novas senhas no host suspeito.
5. Antes de limpar, reparar, restaurar ou reinstalar, determinar escopo, persistência, disponibilidade de backups conhecidos como íntegros e impacto. Em comprometimento de administrador ou persistência ampla, escalar para TI/IR; considerar reconstrução limpa em vez de confiar em rollback simples.
6. Registrar ferramenta/versão, identidade, horário, alvo, autorização, comando/ação, código de saída, erros, limitações e verificação posterior. Redigir segredos e evitar envio a terceiros sem consentimento.

A CISA recomenda isolar sistemas afetados, preservar dados voláteis quando possível, avaliar escopo e coordenar resposta; o desligamento pode remover evidência em memória. A SP 800-61 Rev. 3 do NIST orienta preparação, detecção, resposta, recuperação e melhoria contínua, com responsabilidades e autoridades definidas. Canais de reporte da CISA/FBI/IC3 são dos EUA; seguir autoridades locais fora dessa jurisdição.

## Triagem Linux somente leitura

Identificar primeiro distro e kernel; WSL só descreve o ambiente WSL consultado, não automaticamente o Windows hospedeiro.

```bash
cat /etc/os-release
uname -a
id
ps -eo pid,ppid,user,stat,pcpu,pmem,comm --sort=-pcpu
systemctl list-units --type=service --all --no-pager
systemctl list-unit-files --type=service --state=enabled --no-pager
journalctl --no-pager --since '24 hours ago' -p warning -n 50 -o short-iso
df -hT
findmnt
free -h
ss -lntu
```

Use `dpkg-query` em sistemas baseados em Debian/Ubuntu e `rpm` em distribuições que usem RPM. A coleta é parcial: permissões, containers/namespaces, retenção de logs e configuração podem ocultar dados. Não use `sudo` automaticamente. Não parar serviços, apagar logs, alterar firewall ou remover pacotes durante triagem.

ClamAV pode ser usado para scan explicitamente aprovado. Não adicionar flags de remoção/movimentação à varredura. Lynis, auditd, rkhunter e chkrootkit produzem achados que precisam de contexto; presença de ferramenta ou alerta isolado não prova proteção ou infecção.

## Fontes oficiais

- [CISA: I've Been Hit By Ransomware](https://www.cisa.gov/stopransomware/ive-been-hit-ransomware)
- [CISA #StopRansomware Guide](https://www.cisa.gov/stopransomware/ransomware-guide)
- [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final)
- [Linux `/proc` documentation](https://docs.kernel.org/filesystems/proc.html)
- [systemctl — systemd documentation](https://www.freedesktop.org/software/systemd/man/systemctl.html)
- [ss(8) — Linux manual page](https://man7.org/linux/man-pages/man8/ss.8.html)
- [ClamAV scanning documentation](https://docs.clamav.net/manual/Usage/Scanning.html)
