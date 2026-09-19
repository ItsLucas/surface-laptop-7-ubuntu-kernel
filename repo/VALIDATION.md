# Deployment validation — 2026-09-18

## 2026-09-19 packaging correction

The original container tests below did not install `flash-kernel`. On the real
Romulus13 system, its normal postinst hook failed because the signed Stubble image
contained a DTB but the package omitted the separate versioned DTB searched by
`flash-kernel`. This was a package/test coverage defect, not an unclean host.

Packaging now extracts the exact FDT bytes from the signed `.dtbauto` section into
`/usr/lib/linux-image-<release>/qcom/x1e80100-microsoft-romulus13.dtb`, leaving the
EFI image unchanged. The container fixture now installs `flash-kernel`, identifies
itself as Romulus13, and checks that the installed `/boot/dtbs/<release>/` copy
matches the package-owned source across installation and reconfiguration.

The local regression suite has 15 passing tests, including rejection of malformed
or wrong-model embedded DTBs. Current container/hardware results must be checked
separately; the earlier successful container runs did not cover this case.

Endpoint: **https://mirrors.5cena.cc/sl7/**. The domain root is a general mirror
landing page. Root-level `/dists/`, `/pool/`, `sl7.sources` and archive key paths
return 404; the complete archive is under `/sl7/`.

## Published candidate

- Kernel release: `7.2.0-5-sl7.4.1`.
- Debian version: `7.2.0-5.5+sl7.4.1+pkg1`.
- Packages: versioned `linux-image`, `linux-sl7-support`, `linux-sl7` metapackage.
- Original signed build: GitHub run `35228827527`, kernel commit `db9bdff7d39e4a68ad905a45b7a42c99398cd4de`.
- The repackager verified the input deb digest, boot certificate fingerprint and
  EFI signature. The EFI image and all module files were unchanged. The original
  signing report records verification of 8,643 module signatures and both EFI layers.
- Image deb SHA256: `679a3497198986b6af7a1332c58b03ad8a6f7748b29d64efb860fa22f6c2934e`.
- Support deb SHA256: `6fe26d4808ee8da01bb827f6c453daf978a512384c02a0bae70b8b7d0afc6ddd`.
- Metapackage SHA256: `e14ecc6d29a3b63c3e35dae13d6518c301b9de7734b6c42c3f123bffefeab4ea`.

## Checks completed

- 14 Python unit tests; shell syntax, ShellCheck and actionlint checks passed.
- Real dpkg/dracut/GRUB integration passed in a disposable Ubuntu 26.10 x86
  container, including the actual signed ARM64 payload package. Only disk probing
  and container detection were simulated. Checks covered initrd module/firmware
  inclusion, GRUB entries and arguments, legacy default migration, coexistence,
  failed-hook recovery, reconfigure, purge, and fallback retention.
- Native ARM64 fixture integration and all unit tests passed in
  [GitHub run 35300979081](https://github.com/ItsLucas/surface-laptop-7-ubuntu-kernel/actions/runs/35300979081).
- An isolated APT client used the archive key through `Signed-By`, verified the
  signed index and resolved the full ARM64 Ubuntu 26.10 dependency set for
  `apt install linux-sl7`. The complete 194 MB image was downloaded through APT
  and matched the SHA256 above. Subscription and small-package downloads were
  rechecked after moving the archive under `/sl7/`.
- All four candidate/stable index files were fetched via HTTPS by-hash URLs and
  matched the signed Release sizes and hashes. Stable is intentionally empty.
- `/sl7/pool/`, `candidate/` and `stable/` directory listings return HTTP 200.
  Immutable caching applies only to deb and by-hash files, not directory requests;
  package downloads and by-hash digests were rechecked after fixing this routing.
- Nginx configuration and HTTPS issuance passed. Certbot renewal dry run passed,
  including the Nginx reload deploy hook. Certificate expiry: 2026-12-17.
- The hourly `sl7-apt-sync` service completed with exit status 0. The archive
  signing key is separate from Secure Boot keys and expires on 2028-09-17.

## Remaining hardware evidence

The Surface was powered off. These results do not establish successful firmware,
shim/GRUB, Secure Boot, device initialization or suspend/resume on that machine.
The candidate remains unvalidated on hardware; stable promotion requires that
evidence. The freshly triggered full native kernel build is separate from the
already published repackaged payload; future Releases are gated on the actual
signed-package installation smoke test.
