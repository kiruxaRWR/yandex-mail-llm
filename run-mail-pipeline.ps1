$ProjectPath = "C:\Users\User\source\repos\yandex-mail-llm"
$PythonPath = "$ProjectPath\.venv\Scripts\python.exe"
$LogFile = "$ProjectPath\pipeline.log"

# Обработка сбоев: упавший шаг конвейера перезапускается
# $MaxRestarts раз с увеличивающимися интервалами (сек).
$MaxRestarts = 3
$RetryDelays = 30, 60, 120

chcp 65001 | Out-Null

[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Set-Location $ProjectPath

# Важно: Set-Location не меняет Win32-каталог процесса; дочерние процессы (python)
# наследуют именно его. Без этой строки из Планировщика они стартуют в system32.
[Environment]::CurrentDirectory = $ProjectPath

function Invoke-PipelineStep {
    param(
        [string]$Name,
        [string]$ScriptFile
    )

    Write-Host "=== Запуск $Name ==="

    & $PythonPath $ScriptFile 2>&1 | ForEach-Object { "$_" }
    $exitCode = $LASTEXITCODE

    $restart = 0

    while ($exitCode -ne 0 -and $restart -lt $MaxRestarts) {
        $delay = $RetryDelays[$restart]
        $restart++

        Write-Host "=== ОШИБКА: $Name завершился с кодом $exitCode. Перезапуск $restart/$MaxRestarts через $delay сек. ==="

        Start-Sleep -Seconds $delay

        Write-Host "=== Повторный запуск $Name (попытка $($restart + 1) из $($MaxRestarts + 1)) ==="

        & $PythonPath $ScriptFile 2>&1 | ForEach-Object { "$_" }
        $exitCode = $LASTEXITCODE
    }

    if ($exitCode -ne 0) {
        Write-Host "$Name не завершился успешно после $MaxRestarts перезапусков."
        exit $exitCode
    }

    Write-Host "=== $Name завершён успешно ==="
}

Start-Transcript -Path $LogFile -Append

try {
    Write-Host ("=== Запуск конвейера: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " ===")

    Invoke-PipelineStep -Name "mail-analyzer.py" -ScriptFile "$ProjectPath\mail-analyzer.py"

    Invoke-PipelineStep -Name "scheduler.py" -ScriptFile "$ProjectPath\scheduler.py"

    Write-Host "=== Конвейер завершён успешно ==="
}
finally {
    Stop-Transcript | Out-Null
}

