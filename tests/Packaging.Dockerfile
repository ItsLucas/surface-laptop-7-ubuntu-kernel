ARG UBUNTU_IMAGE=ubuntu:26.10@sha256:73b76549166d2d32444ccbd2b79b34381a1b3e25fd150cdd7fb12383fe7ebdc2
FROM ${UBUNTU_IMAGE}
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 dpkg-dev dracut grub2-common linux-base kmod binutils gcc file zstd flash-kernel \
    && apt-get clean
WORKDIR /workspace
CMD ["python3", "tests/install-smoke.py"]
