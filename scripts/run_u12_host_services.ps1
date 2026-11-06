param(
    [ValidatePattern('^[a-zA-Z0-9]+$')][string]$OutputTag = ('hostServices' + (Get-Date -Format yyyyMMddHHmmss)),
    [ValidateRange(1,300)][int]$Seconds = 300,
    [string]$TrustCache = 'work/UniXNU-odin/build/root-media/services-development-trust-u12.bundle',
    [string]$SystemImage = 'work/UniXNU-odin/build/root-media/system-launch-services-u12.apfs',
    [string]$HandoffADT = 'work/UniXNU-odin/build/desktop-handoff-u12services/kernel.macho.adt'
)
# Computer-only replay. No ADB, fastboot or physical device commands.
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Push-Location $workspaceRoot
try {
    if (Test-Path "work/UniXNU-odin/build/qemu-early-entry-$OutputTag") {
        throw "Preserving existing run; choose a new OutputTag: $OutputTag"
    }
    $replayArgs = @(
        '-X', 'utf8', 'work/UniXNU-odin/scripts/qemu_early_entry.py',
        '--trampoline',
        '--kernel', 'work/UniXNU-odin/build/ios16-prelink-u12match/kernel.prelinked.experimental.macho',
        '--adt', $HandoffADT,
        '--output-tag', $OutputTag, '--virt-platform', '--qemu-vmm-present',
        '--ramdisk', $SystemImage,
        '--data-ramdisk', 'work/UniXNU-odin/build/root-media/host-data-u11b.apfs',
        '--data-no-sep',
        '--trust-cache', $TrustCache,
        '--owned-memory-size', '0xc0000000',
        '--boot-args', '-v serial=0 cpus=1 rd=md0 odin-init-path=/sbin/launchd.ios dyld_flags=8 odin-data-mount=1',
        '--break-at', '_panic_trap_to_debugger', '--seconds', $Seconds,
        '--printf-log', '--log-function', '_IOLog', '--log-function', '_kprintf',
        '--write-log', '--max-syscalls', '30000'
    )
    foreach ($symbol in @('_native_owner_data_stage', '_native_owner_data_status',
        '_native_owner_data_readonly', '_native_ram_block_ready',
        '_native_ram_block_reads', '_native_ram_block_writes', '_native_ram_block_failures')) {
        $replayArgs += @('--read-symbol', $symbol)
    }
    & python @replayArgs
    if ($LASTEXITCODE -ne 0) { throw "Host replay failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}
