"""Measure the display daemon's CPU as a percentage of ONE core.

Run on the panel. The figure published in the release notes is for RED night
mode, which is the expensive path and the mode the display is in from dusk to
dawn, so this refuses to report unless the panel is actually in red.

⚠ `ps`/`top` %CPU is the average since the process STARTED - across mode changes,
data refreshes and idle - so it cannot answer this. This samples
/proc/<pid>/stat utime+stime across a window instead.

⚠ A data refresh inside the window inflates the result: it runs the network
fetches and rebuilds every page overlay on the data thread. The window is
discarded if the journal shows one.

    python3 tools/measure_cpu.py --seconds 150
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/operations/stargazy")

CLK_TCK = os.sysconf("SC_CLK_TCK")


def main_pid():
    out = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", "stargazy"],
                         capture_output=True, text=True).stdout.strip()
    return int(out)


def cpu_ticks(pid):
    """utime + stime for the whole process, in clock ticks."""
    with open("/proc/%d/stat" % pid) as fh:
        f = fh.read().rsplit(") ", 1)[1].split()
    return int(f[11]) + int(f[12])          # utime, stime (fields 14/15, 1-based)


def night_mode():
    """Read the mode off the framebuffer rather than the config.

    The config states an intent; an override from the touch strip changes what
    is actually being drawn, and the expensive path is what is on the panel.
    """
    from grab_panel import grab
    import numpy as np
    a = np.asarray(grab().convert("RGB")).astype(float)
    r, g, b = a[:, :, 0].mean(), a[:, :, 1].mean(), a[:, :, 2].mean()
    # night_filter's red branch writes lum, lum>>4, lum>>5 - so green is about a
    # sixteenth of red and blue a thirty-second. Anything near that is red mode.
    red = r > 4 and g < r * 0.25 and b < r * 0.25
    return ("red" if red else "not red"), (r, g, b)


def refreshes(since):
    out = subprocess.run(
        ["journalctl", "-u", "stargazy", "--since", since, "--no-pager"],
        capture_output=True, text=True).stdout
    return sum(1 for l in out.splitlines() if "Fetching conditions" in l)


ap = argparse.ArgumentParser()
ap.add_argument("--seconds", type=float, default=150.0)
args = ap.parse_args()

pid = main_pid()
if not pid:
    sys.exit("stargazy is not running")

mode, (r, g, b) = night_mode()
host = os.uname().nodename
print("%s  pid %d  mode=%s (mean RGB %.1f/%.1f/%.1f)" % (host, pid, mode, r, g, b))
if mode != "red":
    sys.exit("REFUSED: the panel is not in red mode; the published figure is for red.")

start_wall = time.time()
t0, c0 = time.monotonic(), cpu_ticks(pid)
time.sleep(args.seconds)
t1, c1 = time.monotonic(), cpu_ticks(pid)

n = refreshes("@%d" % int(start_wall - 1))
pct = (c1 - c0) / CLK_TCK / (t1 - t0) * 100.0

print("%s  window %.0fs  refreshes in window: %d" % (host, t1 - t0, n))
if n:
    sys.exit("DISCARDED: %d data refresh(es) fell in the window; re-run." % n)
print("%s  RESULT: %.1f%% of one core (red mode)" % (host, pct))
