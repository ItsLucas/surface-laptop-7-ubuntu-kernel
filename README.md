# Surface Laptop 7 Ubuntu kernel automation

Daily native ARM64 builds of Ubuntu **26.10 / stonking generic**, with the Romulus13 Wi-Fi, QSPI touchpad, SPI touchscreen and power-management patch series.

The version resolver follows Ubuntu's generic metapackage, including future **7.3** kernels. Patch conflicts or build failures stop the pipeline and open/update a GitHub issue mentioning the repository owner. Successful builds produce signed prerelease debs plus reproducible unsigned bundles; kernels are never automatically installed.

The 7.3 Wi-Fi resume workaround reverts the registration-only QRTR HELLO change.
One Romulus13 deep-resume test passed with the original PCIe power policy.
A reviewed source-state check applies this revert only when needed; unknown
upstream changes still stop the build. See the [diagnosis and validation scope](docs/7.3-wifi-resume.zh-CN.md).

Configure the **public certificate** in repository variable `MODULE_CERT_PEM` and the two signing key/certificate pairs as encrypted Secrets in the main-only `secure-boot-signing` Environment. The separate signing job verifies signatures and handles keys only in a network-disabled container; PRs and compilation jobs never receive them. This repository contains reusable patches and tooling, without machine firmware, calibration or network settings.

[中文使用与维护说明](README.zh-CN.md) · [Patch provenance](PROVENANCE.md)

Builds reuse a compressed ccache through GitHub Actions caching (3 GB per snapshot).
Each successful build saves a new snapshot; subsequent runs restore the latest
snapshot for the runner OS/architecture. Compiler contents, inputs and options
still determine individual cache hits. The first run populates the cache;
linking, Rust compilation and packaging are not accelerated. Cache statistics
appear in the build log and `build-diagnostics/ccache-stats.txt` (inside the
diagnostic artifact's logs directory). Change the `ccache-v1` workflow key prefix
to start with an empty cache.

The signed APT archive is **https://mirrors.5cena.cc/sl7/** (`stonking`, `arm64`,
`candidate` / `stable`). Install the `linux-sl7` metapackage to follow updates.
The image package uses Ubuntu kernel hooks to generate initrd with dracut and
refresh the existing GRUB2 menu; old kernels remain available for rollback.
The support package preserves machine-local firmware and settings. Existing
Secure Boot certificate enrollment is still required; no headers are provided yet.
See the Chinese guide for setup and [archive operations](repo/README.md) for deployment.
## Experimental power telemetry

On the tested Romulus13 / BIOS 175.235.235, the next kernel build includes
read-only Qualcomm PLD hwmon modules. They expose seven one-second average power
channels to `sensors`, with stale-data and PM handling. See the
[driver documentation](drivers/qcom-pld-power/README.md),
[protocol evidence](drivers/qcom-pld-power/PROTOCOL.md), and
[validation status](docs/pld-power-validation.md) before enabling it elsewhere.
