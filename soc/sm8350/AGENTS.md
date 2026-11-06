# AGENTS.md - UniXNU-sm8350-common

Shared SoC support for SM8350. Only SoC-wide resources, platform operations and
XNU patches belong here; board wiring stays in the device repository.

Every register range and interrupt must be traceable to a vendor source or to a
device firmware FDT. Update `soc.toml` when the component set changes.
