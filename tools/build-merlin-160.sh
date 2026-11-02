#!/bin/bash
# Build RT-AC86U Merlin 386.14_2 with 160 MHz inside an Ubuntu 20.04 container
# and check the result. Usage, as root: build-merlin-160.sh PROJECT_DIR OUT_DIR
# Follows the Merlin build wiki. The firmware stays in the container on purpose:
# OUT_DIR only receives the log and a report.
set -euo pipefail

PROJECT=$1
OUT=$2
MERLIN_TAG=386.14_2
# Upstream removed gcc 5.3 from am-toolchains in 2026-10, but this tree needs it.
# This is the last commit before 386.14_2 was tagged.
TOOLCHAIN_COMMIT=d1af80e6b6686a4edc680386c09a8361453dd5c1
BUILD_USER=builder
TOOLCHAIN_NAME=crosstools-arm-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25
TOOLCHAIN64_NAME=crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25
TOOLCHAIN=/opt/toolchains/$TOOLCHAIN_NAME
TOOLCHAIN64=/opt/toolchains/$TOOLCHAIN64_NAME

setup() {
	dpkg --add-architecture i386
	apt-get update
	# The wiki's list, minus the GUI tools gconf-editor and gitk. On focal its
	# "python" is provided by python2 plus python-is-python2. The first line adds
	# what a full Ubuntu install has but the container image lacks.
	DEBIAN_FRONTEND=noninteractive apt-get install -y \
		ca-certificates sudo rsync xxd bc cpio wget curl kmod lzma dos2unix net-tools lsb-release \
		python3-venv python3-pip python2 python-is-python2 \
		libtool-bin cmake libproxy-dev uuid-dev liblzo2-dev autoconf autoconf-archive automake bash bison \
		bzip2 diffutils file flex m4 g++ gawk groff-base libncurses5-dev libtool libslang2 make patch perl \
		pkg-config shtool subversion tar texinfo zlib1g zlib1g-dev git gettext libexpat1-dev libssl-dev cvs \
		gperf unzip libxml-parser-perl gcc-multilib libxml2-dev g++-multilib libncurses5 mtd-utils \
		libvorbis-dev autopoint autogen automake-1.15 sed build-essential intltool libglib2.0-dev \
		xutils-dev lib32z1-dev lib32stdc++6 xsltproc gtk-doc-tools libelf1:i386 gengetopt
	echo "dash dash/sh boolean false" | debconf-set-selections
	dpkg-reconfigure -f noninteractive dash
	useradd -m "$BUILD_USER"
	echo "$BUILD_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$BUILD_USER"
	ln -s "/home/$BUILD_USER/am-toolchains/brcm-arm-hnd" /opt/toolchains
	chmod 777 "$OUT"
}

build() {
	cd "$HOME"
	git clone --filter=blob:none --no-checkout https://github.com/RMerl/am-toolchains
	# Not "git sparse-checkout set": focal's git refuses it because master no
	# longer has these directories.
	git -C am-toolchains config core.sparseCheckout true
	printf '/brcm-arm-hnd/%s/\n' "$TOOLCHAIN_NAME" "$TOOLCHAIN64_NAME" > am-toolchains/.git/info/sparse-checkout
	git -C am-toolchains checkout "$TOOLCHAIN_COMMIT"
	git clone --depth 1 --branch "$MERLIN_TAG" https://github.com/RMerl/asuswrt-merlin.ng
	python3 "$PROJECT/tools/merlin160.py" patch asuswrt-merlin.ng | tee "$OUT/report.txt"

	export LD_LIBRARY_PATH=$TOOLCHAIN/usr/lib
	export TOOLCHAIN_BASE=/opt/toolchains
	export PATH=$PATH:$TOOLCHAIN/usr/bin:$TOOLCHAIN64/usr/bin

	cd asuswrt-merlin.ng/release/src-rt-5.02hnd
	while sleep 300; do echo "still building: $(wc -l < "$OUT/build.log") log lines"; done &
	local heartbeat=$!
	local status=0
	make rt-ac86u > "$OUT/build.log" 2>&1 || status=$?
	kill "$heartbeat"
	tail -n 200 "$OUT/build.log"
	gzip -k "$OUT/build.log"
	if [ "$status" -ne 0 ]; then
		echo "FAIL make exited with $status" | tee -a "$OUT/report.txt"
		return "$status"
	fi
	echo "PASS make rt-ac86u finished" | tee -a "$OUT/report.txt"
	check_image
}

check_image() {
	cd "$HOME/asuswrt-merlin.ng/release"
	local image
	image=$(find src-rt-5.02hnd/targets/94908HND -maxdepth 1 -name '*_ubi.w' ! -name '*cferom*' ! -name '*pureubi*' | head -n 1)
	if [ -z "$image" ]; then
		echo "FAIL no *_ubi.w image found" | tee -a "$OUT/report.txt"
		return 1
	fi
	{
		echo "INFO image: $(basename "$image"), $(stat -c %s "$image") bytes"
		echo "INFO sha256: $(sha256sum "$image" | cut -d' ' -f1)"
		grep -H 'RTCONFIG_BW160M' src/router/.config || echo "WARN no RTCONFIG_BW160M line in .config"
		python3 "$PROJECT/tools/fwtool.py" verify "$image" --expect RT-AC86U
	} 2>&1 | tee -a "$OUT/report.txt"

	python3 -m venv "$HOME/venv"
	"$HOME/venv/bin/pip" install --quiet ubi_reader==0.8.16
	python3 -I - "$image" "$HOME/ubi.bin" <<'PY'
import sys
data = open(sys.argv[1], "rb").read()
open(sys.argv[2], "wb").write(data[data.index(b"UBI#"):])
PY
	"$HOME/venv/bin/ubireader_extract_files" -k -o "$HOME/rootfs" "$HOME/ubi.bin" > /dev/null
	local dhd rootfs
	dhd=$(find "$HOME/rootfs" -path '*/lib/modules/4.1.27/extra/dhd.ko' | head -n 1)
	rootfs=${dhd%/lib/modules/*}
	python3 "$PROJECT/tools/merlin160.py" check-rootfs "$rootfs" 2>&1 | tee -a "$OUT/report.txt"
}

case "${3:-all}" in
all)
	setup
	sudo -u "$BUILD_USER" -H bash "$0" "$PROJECT" "$OUT" build
	;;
build)
	build
	;;
esac
