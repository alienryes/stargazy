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

An entry may instead be a `Paged` list of overlays, for a page holding more than
one screenful. It occupies a single slot in the rotation and is stepped by its
own button, so the rotation still turns at the same rate whether the deep-sky
list runs to six objects or forty.
"""
import logging
import random
import signal
import threading
import time

from core.night import night_mode_now
from core.panel import Controls
from core.sky import DEMO_PARAMS

log = logging.getLogger(__name__)

_RUNNING = True  # cleared by SIGTERM/SIGINT so the daemon exits gracefully


class Paged(list):
    """Several overlays occupying one slot in the page rotation.

    Every variant is rendered up front on the data thread, because stepping to
    the next one happens on the render loop, where a re-render - and the cutout
    fetches behind it - cannot be afforded. The cost is memory rather than
    frame time: one full-size RGBA overlay per screenful.
    """


def flatten(pages):
    """Every screenful in order, with Paged runs expanded.

    For the one-shot paths. The daemon steps a Paged page with a button, but
    --save and --once have no button and no rotation, so they take the lot;
    without this they hand a list where an image is expected. The daemon's own
    loop is not the only consumer of build_pages, and that is easy to forget.
    """
    out = []
    for page in pages:
        if isinstance(page, Paged):
            out.extend(page)
        else:
            out.append(page)
    return out


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
        pages = layout.build_pages(states, read_targets(out_dir), lat, moon_ring)
        # Through the layout, not core.sky directly: a build that knows what is
        # actually falling tonight can say so here. The 5" build re-exports
        # core.sky.sky_params unchanged.
        params = DEMO_PARAMS if demo else layout.sky_params(states)
        # Dusk/dawn drive night mode, and they only change when the data does.
        window = layout.night_window(states)
        # Build the cloud strip on THIS thread, and BEFORE the new parameters
        # are published. It is a field-width image costing about 0.6 s on either
        # Pi, which mid-frame is some seven dropped frames at 12 fps; leaving it
        # for the render loop to discover missing is what that would do, four
        # times an hour. Measured at a 550 ms worst frame that way against 19 ms
        # this way.
        #
        # The order is the point. Published first, the render loop would ask for
        # a cover whose strip did not exist yet and build it itself - the stall
        # this exists to avoid, simply moved. At startup this is the main thread
        # and nothing is being drawn yet.
        sky.clouded_base(params["twilight"], params.get("cloud", 0))
        state["pages"], state["params"], state["window"] = pages, params, window

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
                        sky.paint(params, 0.0, [], 0.0), page, None)
                    out.seek(0)
                    out.write(fb.to_bytes(frame, mode, night_dim))
                    last, last_mode = page, mode
                time.sleep(1)
            return

        log.info("Animated mode at %.0f fps.", fps)
        frame_dt = 1.0 / fps
        t0 = time.time()
        meteors = []
        cloud_scroll = 0.0
        next_meteor = t0 + random.uniform(1.0, 3.0)
        page_i, card_i, next_flip = 0, 0, t0 + page_seconds
        paged = False   # set from the page actually composed, one frame behind
        dark = fb.dark_frame()
        blanked = False
        while _RUNNING:
            now = time.time()
            t = now - t0
            params = state["params"]
            if controls:
                tap = reader.get()
                if tap:
                    # Dispatched against the strip as last DRAWN, which is what
                    # the user aimed at. `paged` is from the previous frame for
                    # exactly that reason.
                    controls.touched(tap[0], tap[1], state["window"], paged)
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
            cloud_scroll += params["cloud_deg_s"] * frame_dt
            if params["meteors"] and now >= next_meteor:
                meteors.append(sky.spawn_meteor())
                next_meteor = now + random.uniform(params["met_min"], params["met_max"])
            sky.step_meteors(meteors)
            pages = state["pages"]
            # The page holds while the strip is up as well as while paused.
            # Rotating out from under a finger is the hostility Pause exists to
            # fix, and it is now also a correctness matter: a Paged page carries
            # an extra button, so a flip mid-strip would reflow every button
            # under the user's hand. Holding while the strip is up makes the
            # layout stable by construction rather than by luck.
            holding = bool(controls and (controls.paused or controls.visible))
            if controls and controls.take_next():
                page_i, card_i, next_flip = page_i + 1, 0, now + page_seconds
            elif now >= next_flip:
                # The deadline still moves while holding, so releasing gives a
                # full turn on the page rather than an instant flip.
                if not holding:
                    page_i, card_i = page_i + 1, 0
                next_flip = now + page_seconds
            page = pages[page_i % len(pages)]
            paged = isinstance(page, Paged)
            if paged:
                if controls and controls.take_next_cards():
                    card_i += 1
                # Wraps, so pressing past the last screenful returns to the
                # best targets rather than stopping on the worst.
                page = page[card_i % len(page)]
            labels = (controls.labels(state["window"], paged)
                      if controls and controls.visible else None)
            frame = layout.compose(sky.paint(params, t, meteors, cloud_scroll),
                                   page, labels)
            mode = controls.night_now(state["window"]) if controls \
                else night_mode_now(night, state["window"])
            out.seek(0)
            out.write(fb.to_bytes(frame, mode, night_dim))
            dt = time.time() - now
            if dt < frame_dt:
                time.sleep(frame_dt - dt)
    finally:
        out.close()
