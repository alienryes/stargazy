"""The long-running loop: animate the panel while a thread refreshes the data.

The loop owns timing, touch, page rotation and the framebuffer. Everything that
depends on how a particular panel is laid out comes from the `layout` object a
build passes in, which must provide:

    fb          core.panel.Framebuffer
    sky         core.sky.Sky
    strip       core.panel.Strip
    build_pages(states, targets, lat, moon_ring) -> [RGBA overlay, ...]
    compose(frame, overlay, labels) -> Image

build_pages is only ever called from the data thread, so it is the right place
for the network calls that fetch the lunar frame and the deep-sky cutouts. It
returns one overlay per page; a page that has nothing to show should simply not
be returned, because one live page beats two with a dead one.
"""
import logging
import random
import signal
import threading
import time

from core.night import night_mode_now
from core.panel import Controls
from core.sky import DEMO_PARAMS, sky_params

log = logging.getLogger(__name__)

_RUNNING = True  # cleared by SIGTERM/SIGINT so the daemon exits gracefully


def install_signal_handlers():
    def stop(_signum, _frame):
        global _RUNNING
        _RUNNING = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def running():
    return _RUNNING


def run_daemon(layout, fetch, read_targets, out_dir, lat, animated, fps,
               refresh_min, page_seconds, demo=False, night="off", night_dim=45,
               touch_reader=None, strip_seconds=6, moon_ring=False):
    state = {"pages": [], "params": None, "window": None}
    sky, fb = layout.sky, layout.fb

    def load():
        states = fetch()
        state["pages"] = layout.build_pages(states, read_targets(out_dir), lat, moon_ring)
        state["params"] = DEMO_PARAMS if demo else sky_params(states)
        # Dusk/dawn drive night mode, and they only change when the data does.
        state["window"] = layout.night_window(states)

    log.info("Fetching conditions...")
    load()

    def refresher():
        while _RUNNING:
            for _ in range(int(refresh_min * 60)):
                if not _RUNNING:
                    return
                time.sleep(1)
            if _RUNNING:
                try:
                    load()
                    log.info("Data refreshed.")
                except Exception as e:  # keep animating on a transient fetch error
                    log.warning("Refresh failed: %s", e)

    threading.Thread(target=refresher, daemon=True).start()

    controls = None
    reader = touch_reader if animated else None
    if reader and reader.start():
        controls = Controls(night, strip_seconds, layout.strip)
    else:
        reader = None

    out = fb.open()
    try:
        if not animated:
            log.info("Static mode: redraw on data change.")
            last, last_mode = None, None
            while _RUNNING:
                page = state["pages"][0]
                mode = night_mode_now(night, state["window"])
                if page is not last or mode != last_mode:
                    params = state["params"]
                    frame = layout.compose(
                        sky.paint(params, 0.0, [], sky.initial_clouds(params)), page, None)
                    out.seek(0)
                    out.write(fb.to_bytes(frame, mode, night_dim))
                    last, last_mode = page, mode
                time.sleep(1)
            return

        log.info("Animated mode at %.0f fps.", fps)
        frame_dt = 1.0 / fps
        t0 = time.time()
        meteors = []
        clouds = sky.initial_clouds(state["params"])
        next_meteor = t0 + random.uniform(1.0, 3.0)
        page_i, next_flip = 0, t0 + page_seconds
        dark = fb.dark_frame()
        blanked = False
        while _RUNNING:
            now = time.time()
            t = now - t0
            params = state["params"]
            if controls:
                tap = reader.get()
                if tap:
                    controls.touched(tap[0], tap[1], state["window"])
                if controls.blanked:
                    # Backlight off and nothing composited: the one state in
                    # which this display is not using a whole core.
                    if not blanked:
                        out.seek(0)
                        out.write(dark)
                        blanked = True
                    time.sleep(0.05)
                    continue
                blanked = False
            sky.step_clouds(clouds, params, frame_dt)
            if params["meteors"] and now >= next_meteor:
                meteors.append(sky.spawn_meteor())
                next_meteor = now + random.uniform(params["met_min"], params["met_max"])
            sky.step_meteors(meteors)
            pages = state["pages"]
            if controls and controls.take_next():
                page_i, next_flip = page_i + 1, now + page_seconds
            elif now >= next_flip:
                # A paused page holds; the deadline still moves, so resuming
                # gives a full turn on the page rather than an instant flip.
                if not (controls and controls.paused):
                    page_i += 1
                next_flip = now + page_seconds
            labels = controls.labels() if controls and controls.visible else None
            frame = layout.compose(sky.paint(params, t, meteors, clouds),
                                   pages[page_i % len(pages)], labels)
            mode = controls.night_now(state["window"]) if controls \
                else night_mode_now(night, state["window"])
            out.seek(0)
            out.write(fb.to_bytes(frame, mode, night_dim))
            dt = time.time() - now
            if dt < frame_dt:
                time.sleep(frame_dt - dt)
    finally:
        out.close()
