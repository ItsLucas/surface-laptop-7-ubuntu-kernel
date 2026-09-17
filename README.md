# Surface Laptop 7 Ubuntu kernel automation

Daily native ARM64 builds of Ubuntu **26.10 / stonking generic**, with the Romulus13 Wi-Fi, QSPI touchpad, SPI touchscreen and power-management patch series.

The version resolver follows Ubuntu's generic metapackage, including future **7.3** kernels. Patch conflicts or build failures stop the pipeline and open/update a GitHub issue mentioning the repository owner. Successful builds produce signed prerelease debs plus reproducible unsigned bundles; kernels are never automatically installed.

Configure the **public certificate** in repository variable `MODULE_CERT_PEM` and the two signing key/certificate pairs as encrypted Secrets in the main-only `secure-boot-signing` Environment. The separate signing job verifies signatures and handles keys only in a network-disabled container; PRs and compilation jobs never receive them. This repository contains reusable patches and tooling, without machine firmware, calibration or network settings.

[中文使用与维护说明](README.zh-CN.md) · [Patch provenance](PROVENANCE.md)
