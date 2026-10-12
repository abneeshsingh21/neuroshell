#!/usr/bin/env bash
# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Build standalone Debian / Kali Linux package (.deb) for NeuroShell Cyber

set -euo pipefail

VERSION="5.18.0"
PKG_NAME="neuroshell-cyber"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo 'amd64')"
STAGING_DIR="build/debian/${PKG_NAME}_${VERSION}_${ARCH}"

echo "=================================================================="
echo "📦 Building Debian/Kali Package: ${PKG_NAME}_${VERSION}_${ARCH}.deb"
echo "=================================================================="

# 1. Clean staging directory
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}/DEBIAN"
mkdir -p "${STAGING_DIR}/usr/bin"
mkdir -p "${STAGING_DIR}/usr/share/neuroshell"
mkdir -p "${STAGING_DIR}/usr/share/applications"
mkdir -p "${STAGING_DIR}/usr/share/icons/hicolor/scalable/apps"

# 2. Copy control file
cp packaging/debian_kali/control "${STAGING_DIR}/DEBIAN/control"
sed -i "s/Architecture: any/Architecture: ${ARCH}/" "${STAGING_DIR}/DEBIAN/control"

# 3. Build native C++ executable if needed
if [[ -f "build/neuroshell" ]]; then
    cp build/neuroshell "${STAGING_DIR}/usr/bin/neuroshell"
    chmod +x "${STAGING_DIR}/usr/bin/neuroshell"
elif [[ -f "build/Release/neuroshell.exe" ]]; then
    echo "[!] Warning: Windows binary detected, Linux binary build required for native execution."
fi

# 4. Copy Python modules & models
cp -r editions "${STAGING_DIR}/usr/share/neuroshell/"
cp -r intelligence "${STAGING_DIR}/usr/share/neuroshell/"
cp -r core "${STAGING_DIR}/usr/share/neuroshell/"
cp -r models "${STAGING_DIR}/usr/share/neuroshell/"
cp main.py "${STAGING_DIR}/usr/share/neuroshell/main.py"

# 5. Create launcher wrapper in /usr/bin/neuroshell
cat << 'EOF' > "${STAGING_DIR}/usr/bin/neuroshell-cyber"
#!/usr/bin/env bash
exec python3 /usr/share/neuroshell/main.py --cyber "$@"
EOF
chmod +x "${STAGING_DIR}/usr/bin/neuroshell-cyber"

# 6. Copy Desktop entry
cp packaging/debian_kali/neuroshell-cyber.desktop "${STAGING_DIR}/usr/share/applications/"

# 7. Package with dpkg-deb
if command -v dpkg-deb >/dev/null 2>&1; then
    dpkg-deb --build "${STAGING_DIR}" "build/${PKG_NAME}_${VERSION}_${ARCH}.deb"
    echo "[+] Successfully created build/${PKG_NAME}_${VERSION}_${ARCH}.deb"
else
    echo "[i] dpkg-deb not found on this system. Staging directory ready at ${STAGING_DIR}."
fi
