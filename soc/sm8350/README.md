# UniXNU-sm8350-common

Shared UniXNU support for Qualcomm SM8350 (lahaina / Snapdragon 888).

Contents:

- `soc.toml` - schema 2 SoC description and component selection.
- `dts/sm8350.dtsi` - CPU topology, PSCI, GICv3, UFS host/PHY, USB.
- `configs/sm8350.config` - shared kernel switches (no native Adreno/UFS yet).
- `patches/xnu/series` - SoC XNU patch order (empty during bring-up).
- `kits/` - shared platform operations (empty during bring-up).

Hardware values are derived from the live firmware FDT of a Redmi K40 Pro
(haydn); see the device repository record for provenance.
