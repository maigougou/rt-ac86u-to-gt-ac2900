#!/bin/sh
# Read-only health report. Runs on the router (BusyBox ash), piped over SSH by
# ac86u2gt.py. Usage: sh -s pre|post. Exits 1 if any FAIL line was printed.
# Output: "INFO key=value" lines for later comparison, plus PASS/WARN/FAIL.

MODE=${1:-pre}
FAILED=0

info() { echo "INFO $1=$2"; }
pass() { echo "PASS $1"; }
warn() { echo "WARN $1"; }
fail() { echo "FAIL $1"; FAILED=1; }
nv() { nvram get "$1" 2>/dev/null; }

for key in productid odmpid firmver buildno extendno territory_code \
           label_mac et0macaddr 0:macaddr 1:macaddr serial_no sw_mode lan_ipaddr \
           skip_crc wl0_radio wl1_radio wl1_bw aurargb_enable pause_aura_rgb_nt turbo_mode; do
	info "$key" "$(nv "$key")"
done

info kernel "$(uname -r)"
info loadavg "$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null)"
info memfree_kb "$(awk '/^MemFree/{f=$2} /^Cached/{c=$2} END{print f+c}' /proc/meminfo 2>/dev/null)"
info mtd_table "$(awk 'NR>1{gsub(/"/,"",$4); gsub(/:/,"",$1); printf "%s=%s/%s ", $1, $4, $2}' /proc/mtd 2>/dev/null)"

# eth5 is the 2.4 GHz radio and eth6 the 5 GHz radio on both firmwares.
for ifname in eth5 eth6; do
	info "$ifname.country" "$(wl -i "$ifname" country 2>/dev/null)"
	info "$ifname.chanspecs" "$(wl -i "$ifname" chanspecs 2>/dev/null | wc -l | tr -d ' ')"
	info "$ifname.txpwr_max" "$(wl -i "$ifname" txpwr_target_max 2>/dev/null | head -n 1)"
done

case "$MODE" in
pre)
	case "$(nv productid)" in
	RT-AC86U) pass "firmware identifies as RT-AC86U" ;;
	*) fail "productid is '$(nv productid)', expected RT-AC86U" ;;
	esac
	;;
post)
	case "$(nv productid)" in
	GT-AC2900) pass "firmware identifies as GT-AC2900" ;;
	*) fail "productid is '$(nv productid)', expected GT-AC2900" ;;
	esac
	if [ "$(nv aurargb_enable)" = "1" ]; then
		warn "aurargb_enable=1: no Aura controller on this board, set it to 0"
	fi
	if grep -q 'TURBO' /tmp/syslog.log 2>/dev/null; then
		warn "syslog mentions TURBO: GPIO20 is the WAN LED on this board, check for phantom presses"
	fi
	;;
*)
	fail "unknown mode '$MODE'"
	;;
esac

if [ -s /proc/mtd ]; then
	pass "/proc/mtd is readable"
else
	fail "/proc/mtd is empty or unreadable"
fi

for ifname in eth5 eth6; do
	if wl -i "$ifname" ver >/dev/null 2>&1; then
		pass "radio $ifname responds"
	else
		fail "radio $ifname does not respond"
	fi
done

if grep -q skip_crc /usr/lib/libshared.so 2>/dev/null; then
	pass "this firmware has the skip_crc path"
else
	warn "skip_crc not found in libshared.so: the 'arm' route may not work, use the CFE route"
fi

if [ "$(nv skip_crc)" = "1" ]; then
	warn "skip_crc=1: the web UI will accept any image; run 'disarm' unless you are about to flash"
fi

exit "$FAILED"
