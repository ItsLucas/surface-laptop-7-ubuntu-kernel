FROM ubuntu:26.10@sha256:73b76549166d2d32444ccbd2b79b34381a1b3e25fd150cdd7fb12383fe7ebdc2
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-pefile python3-cryptography openssl sbsigntool kmod zstd binutils dpkg ca-certificates \
    && apt-get clean && test -x /usr/bin/kmodsign
