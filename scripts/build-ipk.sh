#!/bin/sh
#
# Build the DreamPlex .ipk package.
#
# An .ipk is an ar archive holding debian-binary, control.tar.gz and
# data.tar.gz. opkg-build is not always available on a development machine, so
# the archive is assembled here with the standard tools.
#
# The package is Architecture: all - the plugin is pure Python and the only
# compiled artefacts are the gettext catalogues, which are architecture
# independent - so a single .ipk serves every Enigma2 box.
#
# Usage: scripts/build-ipk.sh [output directory]
#
# Run ./configure first. On a native build AX_PYTHON_DEVEL may need a hand:
#   ./configure --prefix=/usr PYTHON_CPPFLAGS="-I/usr/include/python$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"

set -e

TOP=$(cd "$(dirname "$0")/.." && pwd)
OUTDIR=${1:-$TOP}

cd "$TOP"

# Resolve to an absolute path now, while still in $TOP: the ar command below
# runs from a temp staging dir, so a relative OUTDIR would otherwise be
# resolved against that instead of the caller's intended location.
mkdir -p "$OUTDIR"
OUTDIR=$(cd "$OUTDIR" && pwd)

if [ ! -f Makefile ]; then
	echo "Makefile missing: run ./configure first" >&2
	exit 1
fi

PKG=$(sed -n 's/^Package:[[:space:]]*//p' CONTROL/control)
VERSION=$(sed -n 's/^Version:[[:space:]]*//p' CONTROL/control)
ARCH=$(sed -n 's/^Architecture:[[:space:]]*//p' CONTROL/control)

if [ -z "$PKG" ] || [ -z "$VERSION" ] || [ -z "$ARCH" ]; then
	echo "cannot read Package/Version/Architecture from CONTROL/control" >&2
	exit 1
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

STAGE=$WORK/stage
mkdir -p "$STAGE"

echo "installing into a staging tree ..."
make DESTDIR="$STAGE" install >/dev/null

# The .py files are installed as data, so no .pyc should ever appear here;
# should the build system change, they would be bytecode for the build host's
# interpreter and useless on the box.
if find "$STAGE" -name '*.pyc' | grep -q .; then
	echo "warning: .pyc files in the staging tree, removing them" >&2
	find "$STAGE" -name '*.pyc' -delete
	find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi

echo "building control.tar.gz ..."
CTRL=$WORK/control
mkdir -p "$CTRL"
cp CONTROL/control "$CTRL/"
for script in preinst postinst prerm postrm; do
	if [ -f "CONTROL/$script" ]; then
		cp "CONTROL/$script" "$CTRL/"
		chmod 755 "$CTRL/$script"
	fi
done
tar -C "$CTRL" -czf "$WORK/control.tar.gz" .

echo "building data.tar.gz ..."
tar -C "$STAGE" -czf "$WORK/data.tar.gz" .

echo "2.0" > "$WORK/debian-binary"

IPK=$OUTDIR/${PKG}_${VERSION}_${ARCH}.ipk
rm -f "$IPK"
( cd "$WORK" && ar rc "$IPK" debian-binary control.tar.gz data.tar.gz )

echo
echo "package: $IPK"
ls -lh "$IPK" | awk '{print "  size: " $5}'
