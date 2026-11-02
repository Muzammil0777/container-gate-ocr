# Run by setup.exe (as administrator). -Install: lock the app folder, start the gate with Windows and
# open port 8000 to the site network. -Stop: stop the running gate (before an upgrade).
# -Remove: stop and undo -Install (the folder stays locked).
param([switch]$Install, [switch]$Stop, [switch]$Remove)
$name = 'Container Gate OCR'
$app = $PSScriptRoot

function Stop-Gate {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    # The restart loops first (the detection loop can outlive the task), then this folder's Python.
    Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains("$app\gate_service.bat") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith("$app\python\") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# Only SYSTEM (the gate) and Administrators (IT) can read the app folder: logs\gate.db has the
# password hashes, cameras.json the NVR password and the login secret. Everyone may open the shortcut.
# SIDs, not names, so it works on Arabic Windows too.
function Lock-Folder($dir) {
    if (Test-Path "$dir\Gate app.url") { icacls "$dir\Gate app.url" /grant '*S-1-5-32-545:R' /Q | Out-Null }
    icacls $dir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null  # files inside follow
}

if ($Stop -or $Remove) { Stop-Gate }
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Remove-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
}
if ($Install) {
    Stop-Gate
    Lock-Folder $app
    # At PC start, as SYSTEM (no one needs to sign in), never stopped after 3 days, also on battery.
    $action = New-ScheduledTaskAction -Execute "$app\gate_service.bat" -WorkingDirectory $app
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
        -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
    # Other PCs and phones on the site network (private or domain network, not public Wi-Fi).
    Remove-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 `
        -Profile Private, Domain | Out-Null
    Start-ScheduledTask -TaskName $name
}
