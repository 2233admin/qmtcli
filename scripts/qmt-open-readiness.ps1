param(
  [string]$Connection = 'C:\Users\Administrator\AppData\Local\QmtCli\daqmt\connection.json',
  [int]$TradedayDeadlineHour = 8,
  [int]$TradedayDeadlineMinute = 50,
  [int]$RestartGraceMinutes = 10,
  [switch]$SelfTest
)

# Read-only open-readiness probe for the Full-QMT client.
#
# It reads the local connection config for the loopback secret, asks the bridge
# for health, asset and one tick, and reads the client log for the trading day
# and the client's own daily restart. It never places, cancels or modifies an
# order, and never writes the client config or the connection file.
#
# The bridge HTTP server runs inside the 大QMT strategy, so a reachable bridge
# with bridge_running=true is the strong proof that the strategy is alive. The
# log is only needed to tell the client's own 08:50 daily restart apart from a
# crash: that restart logs "Rready to restart" and comes back by itself.
#
# The client writes the log while we read it and locks a portion of the file, so
# the log is opened with FileShare.ReadWrite and a locked read is retried. A log
# that cannot be read at all is a note, not a failure: the bridge checks below
# still decide readiness.

$ErrorActionPreference = 'Stop'
$today = (Get-Date).ToString('yyyyMMdd')
$log = 'D:\DFZQxtqmt_client_real_win64\userdata\log\XtClient_' + $today + '.log'
$problems = New-Object System.Collections.Generic.List[string]
$notes = New-Object System.Collections.Generic.List[string]

function Get-Stamp([string]$value) {
    if ([string]::IsNullOrEmpty($value)) { return $null }
    return [datetime]::ParseExact($value, 'yyyy-MM-dd HH:mm:ss', $null)
}

function Read-SharedLog([string]$path) {
    # Read a file another process is actively appending to. Returns $null when
    # the file stays locked across the retries.
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $stream = $null
        $reader = $null
        try {
            $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
            $stream = [System.IO.File]::Open($path, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read, $share)
            $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::GetEncoding(936))
            $text = $reader.ReadToEnd()
            return $text
        } catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 300
        } finally {
            if ($reader) { $reader.Dispose() }
            elseif ($stream) { $stream.Dispose() }
        }
    }
    return $null
}

function ConvertFrom-TickTimestamp([string]$value) {
    if ([string]::IsNullOrEmpty($value)) { return $null }
    $format = 'yyyyMMdd HH:mm:ss'
    if ($value.Contains('.')) { $format += '.FFFFFFF' }
    return [datetime]::ParseExact($value, $format, [Globalization.CultureInfo]::InvariantCulture)
}

function Get-SessionStart([datetime]$value) {
    $morningStart = $value.Date.AddHours(9).AddMinutes(30)
    $morningEnd = $value.Date.AddHours(11).AddMinutes(30)
    $afternoonStart = $value.Date.AddHours(13)
    $afternoonEnd = $value.Date.AddHours(15)
    if ($value -ge $afternoonStart -and $value -lt $afternoonEnd) { return $afternoonStart }
    if ($value -ge $morningStart -and $value -lt $morningEnd) { return $morningStart }
    return $null
}

function Get-TickFreshnessProblem([datetime]$tickAt, [datetime]$observedAt, [datetime]$sessionStart) {
    if ($tickAt -lt $sessionStart) { return 'quote-not-updating-since-open' }
    if ($tickAt -gt $observedAt) { return 'quote-timestamp-in-future' }
    # The 60-second cutoff is operational policy, not an SDK latency guarantee.
    if (($observedAt - $tickAt).TotalSeconds -gt 60) { return 'quote-stale' }
    return $null
}

function Assert-SelfTest([bool]$condition, [string]$name) {
    if (-not $condition) { throw "self-test failed: $name" }
}

if ($SelfTest) {
    $sessionStart = [datetime]::new(2026, 11, 10, 13, 0, 0)
    $observedAt = [datetime]::new(2026, 11, 10, 14, 57, 0)
    $cases = @(
        @{ Name = 'fresh-fractional'; Tick = '20261110 14:56:59.1'; Expected = 'fresh' },
        @{ Name = 'fresh-at-60s'; Tick = '20261110 14:56:00'; Expected = 'fresh' },
        @{ Name = 'stale-at-61s'; Tick = '20261110 14:55:59'; Expected = 'quote-stale' },
        @{ Name = 'stale-after-open'; Tick = '20261110 13:01:00'; Expected = 'quote-stale' },
        @{ Name = 'future'; Tick = '20261110 14:57:01'; Expected = 'quote-timestamp-in-future' },
        @{ Name = 'before-session-open'; Tick = '20261110 12:59:59'; Expected = 'quote-not-updating-since-open' }
    )
    foreach ($case in $cases) {
        $tickAt = ConvertFrom-TickTimestamp $case.Tick
        $problem = Get-TickFreshnessProblem $tickAt $observedAt $sessionStart
        if ($case.Expected -eq 'fresh') {
            Assert-SelfTest ($null -eq $problem) $case.Name
        } else {
            Assert-SelfTest ($problem -eq $case.Expected) $case.Name
        }
    }

    $sessionCases = @(
        @{ Name = 'before-morning'; Time = [datetime]::new(2026, 11, 10, 9, 29, 59); Expected = $null },
        @{ Name = 'morning-open'; Time = [datetime]::new(2026, 11, 10, 9, 30, 0); Expected = [datetime]::new(2026, 11, 10, 9, 30, 0) },
        @{ Name = 'morning-close'; Time = [datetime]::new(2026, 11, 10, 11, 30, 0); Expected = $null },
        @{ Name = 'lunch'; Time = [datetime]::new(2026, 11, 10, 12, 59, 59); Expected = $null },
        @{ Name = 'afternoon-open'; Time = [datetime]::new(2026, 11, 10, 13, 0, 0); Expected = [datetime]::new(2026, 11, 10, 13, 0, 0) },
        @{ Name = 'afternoon-before-close'; Time = [datetime]::new(2026, 11, 10, 14, 59, 59); Expected = [datetime]::new(2026, 11, 10, 13, 0, 0) },
        @{ Name = 'afternoon-close'; Time = [datetime]::new(2026, 11, 10, 15, 0, 0); Expected = $null }
    )
    foreach ($case in $sessionCases) {
        $actual = Get-SessionStart $case.Time
        if ($null -eq $case.Expected) {
            Assert-SelfTest ($null -eq $actual) $case.Name
        } else {
            Assert-SelfTest ($actual -eq $case.Expected) $case.Name
        }
    }

    Write-Output 'SELFTEST_OK tick-freshness=6 session-boundaries=7'
    exit 0
}

# --- client log: trading day and restart state ------------------------------
$lastRun = $null
$lastQuit = $null
$lastQuitWasRestart = $false
$tradedayToday = $false
$logReadable = $false
if (Test-Path -LiteralPath $log -PathType Leaf) {
    $text = Read-SharedLog $log
    if ($null -eq $text) {
        [void]$notes.Add('log-read-failed')
    } else {
        $logReadable = $true
        foreach ($line in ($text -split "`r?`n")) {
            if ($line -notmatch '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') { continue }
            $stamp = $matches[1]
            if ($line -like '*try run : ID:5, fromula:*') { $lastRun = $stamp }
            elseif ($line -like '*exec quiting*') {
                $lastQuit = $stamp
                $lastQuitWasRestart = $line -like '*Rready to restart*'
            }
            if ($line -like ('*tradeday ' + $today + '*')) { $tradedayToday = $true }
        }
    }
} else { [void]$problems.Add('log-missing') }

$now = Get-Date
$quitAt = Get-Stamp $lastQuit
$inRestartGrace = $false
if ($quitAt) {
    $minutesSinceQuit = ($now - $quitAt).TotalMinutes
    if ($minutesSinceQuit -le $RestartGraceMinutes) {
        if ($lastQuitWasRestart) {
            $inRestartGrace = $true
            [void]$notes.Add('client-restarting')
        } elseif ($minutesSinceQuit -le 2) {
            # A manual window close also writes "exec quiting" without the
            # restart marker; give the operator a moment before calling it down.
            $inRestartGrace = $true
            [void]$notes.Add('client-closing')
        }
    }
}

# --- client process ---------------------------------------------------------
$client = @(Get-Process -Name XtItClient -ErrorAction SilentlyContinue)
if ($client.Count -eq 0 -and -not $inRestartGrace) {
    [void]$problems.Add('client-process-missing')
}

# --- bridge -----------------------------------------------------------------
$bridge = 'unknown'
$cash = $null
$tickTag = $null
$tickAt = $null
$quoteObservedAt = $null
try {
    $cfg = Get-Content -LiteralPath $Connection -Raw -Encoding UTF8 | ConvertFrom-Json
    $headers = @{'X-Bridge-Secret' = $cfg.secret}
    $health = Invoke-RestMethod -Uri ($cfg.endpoint + '/api/health') -Headers $headers -TimeoutSec 8
    if ($health.bridge_running -ne $true) { [void]$problems.Add('bridge-not-running') }
    if ($health.trading_enabled -ne $true) { [void]$problems.Add('trading-disabled') }
    $bridge = 'ok'
    try {
        $asset = Invoke-RestMethod -Uri ($cfg.endpoint + '/api/account/asset') -Headers $headers -TimeoutSec 8
        $cash = $asset.cash
        if (-not ($cash -gt 0)) { [void]$problems.Add('cash-not-positive') }
    } catch { [void]$problems.Add('asset-unreadable') }

    try {
        $tick = Invoke-RestMethod -Uri ($cfg.endpoint + '/api/market/tick?symbol=600000.SH') -Headers $headers -TimeoutSec 8
        $quoteObservedAt = Get-Date
        $tickTag = $tick.tick.timetag
        if ($tickTag) { $tickAt = ConvertFrom-TickTimestamp $tickTag }
        else { [void]$problems.Add('tick-timetag-missing') }
    } catch { [void]$problems.Add('tick-unreadable') }
} catch {
    if ($inRestartGrace) { [void]$notes.Add('bridge-down-during-restart') }
    else { [void]$problems.Add('bridge-unreachable') }
}

# --- trading day ------------------------------------------------------------
$deadline = Get-Date -Hour $TradedayDeadlineHour -Minute $TradedayDeadlineMinute -Second 0
if ($logReadable -and $now -ge $deadline -and -not $tradedayToday) {
    [void]$problems.Add('tradeday-not-' + $today)
}

# --- market data freshness during continuous sessions -----------------------
$sessionStart = Get-SessionStart $now
$tickAgeSeconds = $null
if ($sessionStart -and $tickAt -and $quoteObservedAt) {
    $tickAgeSeconds = [math]::Round(($quoteObservedAt - $tickAt).TotalSeconds, 1)
    $quoteProblem = Get-TickFreshnessProblem $tickAt $quoteObservedAt $sessionStart
    if ($quoteProblem) { [void]$problems.Add($quoteProblem) }
}

$tickAge = 'not-evaluated'
if ($null -ne $tickAgeSeconds) { $tickAge = $tickAgeSeconds }
$state = 'client=' + $client.Count + ' bridge=' + $bridge + ' cash=' + $cash +
    ' tradeday_today=' + $tradedayToday + ' tick_age_s=' + $tickAge + ' tick=' + $tickTag +
    ' last_run=' + $lastRun + ' last_quit=' + $lastQuit +
    ' notes=' + ($notes -join ',')

if ($problems.Count -eq 0) {
    Write-Output ('QMT_READY ' + $state)
    exit 0
}

Write-Output ('QMT_NOT_READY ' + ($problems -join ',') + ' ' + $state)
exit 1
