param(
    [ValidatePattern('^[a-zA-Z0-9]+$')][string]$OutputTag = 'u15display',
    [ValidateRange(1,1800)][int]$Seconds = 90,
    [switch]$AllowHostStop,
    [ValidatePattern('^[a-zA-Z0-9]+$')][string]$BuildTag = 'u15',
    [switch]$UserTrapSnapshot,
    [string]$UiThreadPlan = '',
    [ValidateRange(0,600)][int]$UiThreadInterval = 0,
    [switch]$HostInputLog,
    [string[]]$AdditionalDataLogPaths = @(),
    [string]$SystemImage = 'work/UniXNU-odin/build/root-media/system-cryptex-links-u13.apfs',
    [string]$DataImage = 'work/UniXNU-odin/build/root-media/host-data-u11b.apfs',
    [ValidateSet('0xc0000000','0x100000000')][string]$OwnedMemorySize = '0xc0000000',
    [ValidateRange(0,600)][int]$FrameInterval = 0,
    [string]$AdtImage = 'work/UniXNU-odin/build/desktop-handoff-u13cryptex/kernel.macho.adt',
    [string]$TrustCache = 'work/UniXNU-odin/build/root-media/services-cryptex-trust-u13.bundle',
    [switch]$QuietUserspace,
    [switch]$MappedScanoutReady,
    [switch]$LogicalDisplayPM,
    [switch]$CpuPresentation,
    [switch]$KeyStoreEvents,
    [switch]$EphemeralKeyState,
    [switch]$SpringBoardUiComponent,
    [switch]$SpringBoardPathVariables,
    [switch]$SurfaceInspect,
    [switch]$ObserveDisplayClient,
    [switch]$DisplayClientPayload
)
# Computer-only original display lifecycle replay. No phone commands.
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Push-Location $workspaceRoot
try {
    if (Test-Path "work/UniXNU-odin/build/qemu-early-entry-$OutputTag") {
        throw "Preserving existing replay; choose a new OutputTag: $OutputTag"
    }
    $displayBootArgs='-v serial=0 cpus=1 rd=md0 odin-init-path=/sbin/launchd.ios dyld_flags=8 odin-data-mount=1 odin-gop-display=1'
    if ($MappedScanoutReady) { $displayBootArgs += ' odin-gop-ready=1' }
    if ($LogicalDisplayPM) {
        if (!$MappedScanoutReady) { throw 'LogicalDisplayPM requires MappedScanoutReady' }
        $displayBootArgs += ' odin-gop-pm=1'
    }
    if ($CpuPresentation) {
        if (!$LogicalDisplayPM -or !$SurfaceInspect) { throw 'CpuPresentation requires LogicalDisplayPM and SurfaceInspect' }
        $displayBootArgs += ' odin-gop-cpu=1'
    }
    if ($KeyStoreEvents) { $displayBootArgs += ' odin-key-events=1' }
    if ($SpringBoardUiComponent) { $displayBootArgs += ' odin-sb-ui=1' }
    if ($SpringBoardPathVariables) {
        if (!$SpringBoardUiComponent) { throw 'SpringBoardPathVariables requires SpringBoardUiComponent' }
        $displayBootArgs += ' odin-sb-pathvars=1'
    }
    if ($SurfaceInspect) { $displayBootArgs += ' odin-surface-inspect=1' }
    if ($EphemeralKeyState) {
        if (!$KeyStoreEvents) { throw 'EphemeralKeyState requires KeyStoreEvents' }
        $displayBootArgs += ' odin-key-state=1'
    }
    $replayArgs = @(
        '-X', 'utf8', 'work/UniXNU-odin/scripts/qemu_early_entry.py',
        '--trampoline',
        '--kernel', "work/UniXNU-odin/build/display-owner-$BuildTag/kernel.prelinked.experimental.macho",
        '--adt', $AdtImage,
        '--output-tag', $OutputTag, '--virt-platform', '--qemu-vmm-present',
        '--ramdisk', $SystemImage,
        '--data-ramdisk', $DataImage,
        '--data-no-sep',
        '--trust-cache', $TrustCache,
        '--owned-memory-size', $OwnedMemorySize,
        '--boot-args', $displayBootArgs,
        '--break-at', $(if ($UserTrapSnapshot) {'_handle_breakpoint'} else {'_panic_trap_to_debugger'}), '--seconds', $Seconds,
        '--printf-log', '--log-function', '_IOLog', '--log-function', '_kprintf',
        '--max-syscalls', '30000'
    )
    if ($FrameInterval) { $replayArgs += @('--frame-interval', $FrameInterval) }
    if ($AllowHostStop) { $replayArgs += '--allow-host-stop' }
    if ($UiThreadPlan) { $replayArgs += @('--ui-thread-plan', $UiThreadPlan) }
    if ($UiThreadInterval) { $replayArgs += @('--ui-thread-interval', $UiThreadInterval) }
    if ($HostInputLog) {
        if (!$UiThreadInterval) { throw 'HostInputLog requires periodic UI observation' }
        $replayArgs += @('--data-log-path', '/tmp/odin-host-input.log')
    }
    if ($AdditionalDataLogPaths.Count) {
        if (!$UiThreadInterval) { throw 'AdditionalDataLogPaths requires periodic observation' }
        foreach ($dataLogPath in $AdditionalDataLogPaths) {
            if ($dataLogPath -notin @('/tmp/odin-host-input.log', '/tmp/odin-sb-unlock.log')) { throw 'Expected an audited host component log path' }
            $replayArgs += @('--data-log-path', $dataLogPath)
        }
    }
    if ($UserTrapSnapshot) { $replayArgs += '--user-trap-snapshot' }
    if (!$QuietUserspace) { $replayArgs += '--write-log' }
    if ($ObserveDisplayClient) {
        & python -X utf8 work/UniXNU-odin/scripts/audit_ios16_display_observer.py --build-tag $BuildTag
        if ($LASTEXITCODE -ne 0) { throw 'Original display observation points failed qualification' }
        $observer = Get-Content "work/UniXNU-odin/build/display-owner-$BuildTag/display-observer-contract.json" -Raw | ConvertFrom-Json
        $replayArgs += @('--observe-address', $observer.entry, '--observe-address', $observer.returned)
    }
    if ($DisplayClientPayload) {
        if (!$ObserveDisplayClient) { throw 'DisplayClientPayload requires ObserveDisplayClient' }
        $replayArgs += '--display-client-payload'
    }
    if ($KeyStoreEvents) { $replayArgs += @('--read-symbol', '_odin_keyevents_stage') }
    if ($EphemeralKeyState) { $replayArgs += @('--read-symbol', '_odin_aks_calls', '--read-symbol', '_odin_aks_opened') }
    if ($SurfaceInspect) { $replayArgs += @('--read-symbol', '_odin_surface_inspections') }
    foreach ($symbol in @('_odin_display_owner_stage', '_odin_display_owner_status',
        '_native_owner_data_stage', '_native_owner_data_status',
        '_native_ram_block_reads', '_native_ram_block_writes', '_native_ram_block_failures')) {
        $replayArgs += @('--read-symbol', $symbol)
    }
    & python @replayArgs
    if ($LASTEXITCODE -ne 0) { throw "Host replay failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}
