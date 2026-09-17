# Surface Laptop 7 Ubuntu kernel automation

Daily native ARM64 builds of Ubuntu **26.10 / stonking generic**, with the Romulus13 Wi-Fi, QSPI touchpad, SPI touchscreen and power-management patch series.

The version resolver follows Ubuntu's generic metapackage, including future **7.3** kernels. Patch conflicts or build failures stop the pipeline and open/update a GitHub issue mentioning the repository owner. Successful builds are unsigned prerelease candidates, not automatically installed kernels.

Private MOK keys remain local. Configure the **public certificate** in repository variable `MODULE_CERT_PEM`; review and sign downloaded candidates locally. This repository contains reusable patches and tooling, without machine firmware, calibration or network settings.

[中文使用与维护说明](README.zh-CN.md) · [Patch provenance](PROVENANCE.md)
