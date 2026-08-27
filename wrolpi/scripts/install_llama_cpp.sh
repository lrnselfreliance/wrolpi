#!/usr/bin/env bash
# Install llama.cpp's llama-server, WROLPi's local AI inference runtime.
#
# This is the single source of truth, called by every place that provisions a
# WROLPi so a version bump only has to be made here:
#   - scripts/upgrade.sh                                  (on-device upgrade)
#   - pi-gen/stage2/04-wrolpi/03-run-chroot.sh            (Raspberry Pi image build)
#   - debian-live-config/config/hooks/normal/9999-wrolpi.hook.chroot  (Debian Live ISO build)
#   - docker/llm/Dockerfile                               (Docker llm container)
#
# Built from the SHA-pinned source tarball (llama.cpp ships no generic Linux
# binaries for ARM).  The build takes several minutes on a Raspberry Pi; the
# version marker makes re-runs no-ops until the pinned version changes.
# Run as root: installs into /usr/local/bin and apt-installs build dependencies.
set -e

LLAMA_CPP_VERSION="v0.3.0"
# SHA256 of the source tarball -- arch-independent, one value covers every build.
LLAMA_CPP_SHA256="d94c02d86db22d68692f6bb5b3854763d5091e52142868dc7251995517c666d1"

# llama-server's version output tracks build numbers, not release tags, so the
# installed release is recorded in a marker file.  The +dl suffix marks the
# multi-variant CPU build; bumping it forces a rebuild of older installs.
MARKER_DIR=/usr/local/share/wrolpi
MARKER="${MARKER_DIR}/llama_cpp_version"
MARKER_VALUE="${LLAMA_CPP_VERSION}+dl1"

# llama-server and its dlopen'd CPU-variant backends live together here; the
# backend loader scans the real executable's directory.
INSTALL_DIR=/opt/llama-cpp

install_llama_cpp() {
  if [ -f "${MARKER}" ] && [ "$(cat "${MARKER}")" = "${MARKER_VALUE}" ] \
      && command -v llama-server &>/dev/null; then
    echo "llama.cpp ${LLAMA_CPP_VERSION} already installed"
    return 0
  fi

  echo "Building llama.cpp ${LLAMA_CPP_VERSION}..."
  apt-get install -y build-essential cmake

  local build_dir
  build_dir=$(mktemp -d)
  curl -fsSL "https://github.com/ggml-org/llama.cpp/archive/refs/tags/${LLAMA_CPP_VERSION}.tar.gz" \
    -o /tmp/llama_cpp.tar.gz
  echo "${LLAMA_CPP_SHA256}  /tmp/llama_cpp.tar.gz" | sha256sum -c -
  tar -xz -C "${build_dir}" --strip-components=1 -f /tmp/llama_cpp.tar.gz
  rm -f /tmp/llama_cpp.tar.gz

  # GGML_NATIVE=OFF: an image built in a chroot/QEMU (or a docker image moved
  # between machines) must not bake in the build host's CPU features.  On
  # x86_64 the baseline still assumes AVX2, which SIGILLs on older CPUs
  # (AMD FX, early Atom) -- so build every CPU variant with runtime dispatch,
  # exactly like llama.cpp's official release binaries.
  local variant_flags=""
  if [ "$(uname -m)" = "x86_64" ]; then
    variant_flags="-DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON"
  fi
  (cd "${build_dir}" &&
    cmake -B build \
      -DCMAKE_BUILD_TYPE=Release \
      -DGGML_NATIVE=OFF \
      -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON \
      ${variant_flags} \
      -DLLAMA_CURL=OFF \
      -DLLAMA_BUILD_TESTS=OFF \
      -DLLAMA_BUILD_EXAMPLES=OFF \
      -DLLAMA_BUILD_SERVER=ON &&
    cmake --build build -j"$(nproc)")

  # Install the binary and every built library (CPU-variant backends included)
  # together; the backend loader scans the executable's real directory.
  rm -rf "${INSTALL_DIR}"
  mkdir -p "${INSTALL_DIR}"
  cp "${build_dir}"/build/bin/llama-server "${INSTALL_DIR}/"
  cp "${build_dir}"/build/bin/*.so "${INSTALL_DIR}/" 2>/dev/null || true
  find "${build_dir}/build" -name 'lib*.so*' -exec cp {} "${INSTALL_DIR}/" \; 2>/dev/null || true
  chmod 0755 "${INSTALL_DIR}"/llama-server
  ln -sf "${INSTALL_DIR}/llama-server" /usr/local/bin/llama-server
  rm -rf "${build_dir}"

  mkdir -p "${MARKER_DIR}"
  echo "${MARKER_VALUE}" > "${MARKER}"
  LD_LIBRARY_PATH="${INSTALL_DIR}" llama-server --version || true
  echo "llama.cpp ${LLAMA_CPP_VERSION} installed"
}

install_llama_cpp
