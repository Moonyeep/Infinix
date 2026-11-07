$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Script = Join-Path $Repo "self_improve.py"
if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) {
    throw "self_improve.py não encontrado em $Repo"
}

function Test-PythonVersion([string]$Executable, [string[]]$PrefixArgs) {
    try {
        $result = & $Executable @PrefixArgs -c "import sys; print('%d.%d|%s' % (sys.version_info[0], sys.version_info[1], sys.executable))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $result) { return $null }
        $parts = ([string]$result).Trim().Split('|', 2)
        if ($parts.Count -ne 2) { return $null }
        $version = [version]($parts[0] + ".0")
        if ($version -lt [version]"3.10.0") { return $null }
        return [pscustomobject]@{ Executable = $Executable; PrefixArgs = $PrefixArgs; PythonPath = $parts[1] }
    } catch {
        return $null
    }
}

$Python = $null
$Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($Launcher) {
    $Python = Test-PythonVersion $Launcher.Source @("-3")
    foreach ($Minor in @("3.15", "3.14", "3.13", "3.12", "3.11", "3.10")) {
        if ($Python) { break }
        $Python = Test-PythonVersion $Launcher.Source @("-" + $Minor)
        if ($Python) { break }
    }
}
if (-not $Python) {
    $Command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($Command) { $Python = Test-PythonVersion $Command.Source @() }
}
if (-not $Python) {
    throw "Python 3.10 ou mais recente não foi encontrado. Instale uma versão compatível e execute este instalador novamente."
}

$TaskName = "Infinix Self-Improvement Weekly"
$QuotedScript = '"' + $Script + '"'
$QuotedRepo = '"' + $Repo + '"'
$Arguments = @("-u", $QuotedScript, "--repo", $QuotedRepo, "--mode", "propose", "--allow-source-upload") -join " "
$Action = New-ScheduledTaskAction -Execute $Python.PythonPath -Argument $Arguments -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:00AM
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Gera semanalmente um relatório e candidato isolado do Infinix; nunca instala nem promove alterações." -Force | Out-Null
Write-Output "Tarefa '$TaskName' criada para domingos às 03:00 (hora local), limitada ao usuário atual e sem privilégios elevados."
Write-Output "Para gerar candidatos, configure ZS_IMPROVE_API_BASE, ZS_IMPROVE_MODEL e ZS_IMPROVE_API_KEY no ambiente do usuário."
Write-Output "Para autorizar envio remoto sem confirmações por execução, configure uma vez ZS_IMPROVE_ALLOW_SOURCE_UPLOAD=1 no ambiente do usuário. Sem isso, nenhuma fonte será enviada."
Write-Output "A tarefa contém --allow-source-upload e executará sem prompts; instale-a e defina o opt-in persistente somente se aceitar o envio automatizado de snapshots sanitizados."
Write-Output "Resultados: $Repo\.zeroscript\improvement-reports e $Repo\.zeroscript\improvement-candidates"
