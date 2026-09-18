# SL7 APT archive operations

The deployed endpoint is https://mirrors.5cena.cc/sl7/. Packages target Ubuntu 26.10
`stonking`, `arm64`, Surface Laptop 7 13.8-inch / Romulus13, with existing GRUB2.
Use `sl7.sources` and the public archive key from the endpoint. The `candidate`
component receives completed native-package GitHub Releases; `stable` is promoted
only after hardware validation. An empty stable component is intentional.

The server serves already signed debs. It does not build kernels, possess the
Secure Boot private keys, run package maintainer scripts, or install ARM kernels.
Launchpad PPAs accept source uploads, not these prebuilt signed debs:
https://documentation.ubuntu.com/launchpad/user/reference/packaging/ppas/ppa/.

## Deployment layout

- `/opt/sl7-apt/{publish,sync}.py`: root-owned publisher and GitHub synchronizer.
- `/srv/mirrors`: generic Nginx document root and mirror landing page.
- `/srv/mirrors/sl7`: symlink to `/srv/sl7-apt/public`, the archive's immutable
  pool, public key and reports, exposed only under `/sl7/`.
- `/srv/sl7-apt/snapshots`: signed index generations; `public/dists` switches
  atomically. All earlier by-hash indexes remain accessible.
- `/srv/sl7-apt/gnupg`: mode 0700, owned by the `sl7repo` service account. Back up
  this directory securely; never copy it under `public` or into Git.
- `/etc/sl7-apt.conf`: `SIGNING_KEY=EFC66FC43239A82F1909B2A6283F87158DF052D9`.
- `sl7-apt-sync.timer`: hourly public GitHub polling, no GitHub token required.
  Every successful check refreshes the 14-day Release expiry, even without a build.

The archive key expires on 2028-09-17. Plan key renewal/distribution before then.
Its fingerprint is `EFC66FC43239A82F1909B2A6283F87158DF052D9`. It is separate from
the EFI/module certificate. HTTPS uses Certbot webroot renewal and an Nginx reload
deploy hook, with the existing Certbot timer retained.

Required server tools: Python 3, dpkg-dev, GnuPG, Nginx, Certbot, CA certificates.
Install `nginx-http.conf` to complete HTTP-01 issuance, then `nginx.conf` after the
certificate exists. Other virtual hosts are independent.
HTTP-01 challenges keep their existing `/srv/sl7-apt/public` webroot through the
dedicated Nginx challenge location; the domain root is not an APT repository.

## Import / promotion / recovery

Put the three matching debs and their `SIGNING.json` in a directory readable by
`sl7repo`. The publisher verifies digests, package names, architectures and versions.

```sh
sudo -u sl7repo python3 /opt/sl7-apt/publish.py \
  --signing-key EFC66FC43239A82F1909B2A6283F87158DF052D9 \
  --component candidate --input /srv/sl7-apt/incoming
sudo systemctl start sl7-apt-sync.service
sudo journalctl -u sl7-apt-sync.service
```

After hardware validation, run the same import with `--component stable`. Record
the hardware evidence separately; a copied candidate report does not itself
attest hardware success. The importer never overwrites a filename with different
bytes. Higher version metapackages point to new versioned image packages; all
previous image packages remain available. Do not delete pool files while a
published index or rollback may still reference them.

To undo a bad source subscription, remove the source file. To roll back a boot,
select a retained kernel in GRUB; package downgrades require explicit APT version
selection. Existing kernels are protected against unattended autoremove by
`linux-sl7-support`; remove unwanted versions explicitly after testing.

## First release migration

`ci/repackage.py` verifies the original Release deb and embedded boot certificate,
preserves the signed EFI image and every module byte, and builds the native image,
support package and metapackage with a higher Debian package version. The initial
publication uses `7.2.0-5.5+sl7.4.1+pkg1`, retaining kernel release
`7.2.0-5-sl7.4.1`. Subsequent CI builds produce native packages directly.

The packaging smoke test executes real dpkg, dracut and GRUB in an isolated Ubuntu
container. It simulates the disk probe and container detection; it is not a boot
test. Run `docker build -f tests/Packaging.Dockerfile -t sl7-package-check .` then
`docker run --rm -v "$PWD:/workspace:ro" sl7-package-check` from the repo root on
ARM64. On x86 use `--build-arg UBUNTU_IMAGE=ubuntu:26.10` when building the test
image. CI tests on native ARM64 and also tests the actual signed debs before
publishing each Release; local x86 tests do not prove ARM64 boot compatibility.
