#Requires -Version 5.1
# Startet c2pa-scanner aus dem Quellcode.
$ErrorActionPreference = "Stop"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

# ErrorActionPreference vor dem nativen Aufruf lockern - sonst verpackt PS 5.1
# jede stderr-Zeile in einen ErrorRecord und bricht ab, bevor der Reset laeuft.
$ErrorActionPreference = "Continue"

# try/finally: der Terminal-Reset MUSS auch dann laufen, wenn Ctrl+C das Skript
# abbricht - PowerShell fuehrt finally auch bei Unterbrechung aus.
$code = 0
try {
    & $python -m c2pa_scanner @args
    $code = $LASTEXITCODE
} finally {
    # Terminal nach dem App-Ende IMMER wiederherstellen - egal wie Python endete
    # (sauberes Quit, Ctrl+C, harter oder nativer Crash). Textuals Teardown und
    # der Python-finally-Block greifen bei einem harten Absturz nicht; dieser
    # Shell-Reset laeuft, wenn Python komplett weg ist und PowerShell die Konsole
    # wieder besitzt. Sonst bleibt das Maus-Tracking an und die Shell ist
    # "zerschossen" (jede Mausbewegung kippt Steuerzeichen ins Eingabefeld).
    # Reset: Maus-Tracking (?1000/?1002/?1003), SGR/urxvt-Encoding (?1006/?1015),
    # Bracketed-Paste (?2004); Cursor sichtbar (?25h); Alternate-Screen verlassen
    # (?1049l), der bei einem Crash die sichtbare Shell blockiert.
    $esc = [char]27
    [Console]::Write("$esc[?1000l$esc[?1002l$esc[?1003l$esc[?1006l$esc[?1015l$esc[?2004l$esc[?25h$esc[?1049l")
}

exit $code
