from pathlib import Path
import time
import os
import wave
from typing import Optional, Tuple, Iterable, Union

from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys
from pywinauto.timings import wait_until_passes


DEFAULT_TITLE_RE = ".*OpenUtau.*"
DEBUG = os.environ.get("OPENUTAU_AUTOMATION_DEBUG", "").lower() in ("1", "true", "yes")


class OpenUtauAutomationError(RuntimeError):
    pass


def _log(msg: str):
    if DEBUG:
        print(f"[openutau_automation] {msg}")


def _is_rendered_wav(path: Path, min_bytes: int = 10000, min_frames: int = 512) -> bool:
    try:
        if not path.exists() or path.stat().st_size < min_bytes:
            return False
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() >= min_frames
    except Exception:
        return False


def _wav_duration_sec(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            sr = wf.getframerate() or 1
            return float(frames) / float(sr)
    except Exception:
        return 0.0


def _wait_for_wav_complete(
    path: Path,
    timeout_sec: int = 180,
    stable_sec: int = 4,
    min_duration_sec: Optional[float] = None,
) -> bool:
    last_size = -1
    stable_start = None
    start = time.time()
    min_dur = float(min_duration_sec) * 0.9 if min_duration_sec else None

    while time.time() - start < timeout_sec:
        if _is_rendered_wav(path):
            dur = _wav_duration_sec(path)
            dur_ok = (min_dur is None) or (dur >= max(1.0, min_dur))
            if dur_ok:
                size = path.stat().st_size
                if size == last_size:
                    if stable_start is None:
                        stable_start = time.time()
                    elif time.time() - stable_start >= stable_sec:
                        return True
                else:
                    stable_start = None
                    last_size = size
        time.sleep(1)
    return False


def _yielding_retry(fn, timeout: int = 10, initial_sleep: float = 0.2, max_sleep: float = 1.5):
    start = time.time()
    delay = initial_sleep
    last_exc = None
    while time.time() - start < timeout:
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            time.sleep(delay)
            delay = min(max_sleep, delay * 1.5)
    if last_exc:
        raise last_exc
    raise OpenUtauAutomationError("Retry loop timed out.")


def _get_window(title_re: str = DEFAULT_TITLE_RE):
    return Desktop(backend="uia").window(title_re=title_re)


def ensure_openutau_running(
    exe_path: Optional[str],
    autostart: bool = True,
    wait_sec: int = 20,
    title_re: str = DEFAULT_TITLE_RE,
) -> Tuple[Optional[Application], object]:
    try:
        win = _get_window(title_re)
        if win.exists(timeout=1):
            return None, win
    except Exception:
        pass

    if not autostart:
        raise OpenUtauAutomationError("OpenUtau is not running and autostart is disabled.")
    if not exe_path:
        raise OpenUtauAutomationError("Missing OpenUtau exe path for autostart.")

    app = Application(backend="uia").start(exe_path)

    def _wait_for_window():
        win = _get_window(title_re)
        win.wait("visible", timeout=2)
        return win

    win = wait_until_passes(wait_sec, 1, _wait_for_window)
    return app, win


def _iter_title_patterns(title_re: Union[str, Iterable[str]]) -> Iterable[str]:
    if isinstance(title_re, str):
        return [title_re]
    return list(title_re)


def _wait_for_dialog(title_re: Optional[Union[str, Iterable[str]]], timeout: int = 20):
    def _get():
        if title_re is None:
            dlg = Desktop(backend="uia").window(class_name="#32770")
            if dlg.exists(timeout=1):
                dlg.wait("visible", timeout=2)
                return dlg
            raise OpenUtauAutomationError("Dialog not found yet.")
        for pattern in _iter_title_patterns(title_re):
            dlg = Desktop(backend="uia").window(title_re=pattern)
            if dlg.exists(timeout=1):
                dlg.wait("visible", timeout=2)
                return dlg
        raise OpenUtauAutomationError("Dialog not found yet.")

    return wait_until_passes(timeout, 1, _get)


def _set_dialog_filename(dlg, path: str):
    # Strategy 1: original child_window by title
    try:
        dlg.child_window(title="File name:", control_type="Edit").set_edit_text(path)
        return
    except AttributeError:
        # dlg is a raw UIAWrapper — re-wrap it
        pass
    except Exception:
        pass

    # Strategy 2: re-wrap via Application.connect to get full pywinauto wrapper
    try:
        app = Application(backend="uia").connect(handle=dlg.handle)
        wrapped = app.window(handle=dlg.handle)
        wrapped.child_window(title="File name:", control_type="Edit").set_edit_text(path)
        return
    except Exception:
        pass

    # Strategy 3: descendants on re-wrapped dialog
    try:
        app = Application(backend="uia").connect(handle=dlg.handle)
        wrapped = app.window(handle=dlg.handle)
        edits = wrapped.descendants(control_type="Edit")
        if edits:
            edits[0].set_edit_text(path)
            return
    except Exception:
        pass

    # Strategy 4: descendants on original dlg
    try:
        edits = dlg.descendants(control_type="Edit")
        if edits:
            edits[0].set_edit_text(path)
            return
    except Exception:
        pass

    raise OpenUtauAutomationError("Could not find filename input in dialog.")


def _set_dialog_directory(path: str):
    # Try to focus the address bar and type the directory.
    try:
        send_keys("%d")
        time.sleep(0.2)
        send_keys(path, with_spaces=True)
        time.sleep(0.1)
        send_keys("{ENTER}")
        time.sleep(0.4)
        return True
    except Exception:
        return False


def _click_dialog_primary(dlg, button_title: str):
    try:
        dlg.child_window(title=button_title, control_type="Button").click()
        return True
    except Exception:
        return False


def _confirm_overwrite_if_needed():
    # Handle overwrite confirmation if it appears.
    for title in ["Confirm Save As", "Confirm Save", "Replace", "Save As"]:
        try:
            dlg = Desktop(backend="uia").window(title_re=f".*{title}.*", class_name="#32770")
            if dlg.exists(timeout=1):
                for btn in ["Yes", "Replace", "OK"]:
                    if _click_dialog_primary(dlg, btn):
                        return
        except Exception:
            continue


def _wait_for_cache_stable(
    cache_dir: str,
    stable_seconds: int = 6,
    timeout: int = 180,
):
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return

    start = time.time()
    last_change = time.time()
    saw_activity = False
    last_mtime = 0.0

    while time.time() - start < timeout:
        newest_mtime = 0.0
        for f in cache_path.rglob("*"):
            if not f.is_file():
                continue
            try:
                mtime = f.stat().st_mtime
            except Exception:
                continue
            if mtime > newest_mtime:
                newest_mtime = mtime

        if newest_mtime > start:
            saw_activity = True
        if newest_mtime > last_mtime:
            last_mtime = newest_mtime
            last_change = time.time()
        elif saw_activity and time.time() - last_change > stable_seconds:
            return
        elif not saw_activity and time.time() - start > 15:
            return

        time.sleep(1)


def _find_menu_popup(timeout: int = 5):
    start = time.time()
    while time.time() - start < timeout:
        for w in Desktop(backend="uia").windows():
            try:
                if w.exists() and (w.class_name() in ("#32768", "Popup") or w.friendly_class_name() == "Menu"):
                    return w
            except Exception:
                continue
        time.sleep(0.2)
    return None


def _try_export_via_menu_search(win) -> bool:
    win.set_focus()
    send_keys("%f")
    menu = _find_menu_popup(timeout=3)
    if menu is None:
        return False

    try:
        export_items = [
            item for item in menu.descendants(control_type="MenuItem")
            if "export" in (item.window_text() or "").lower()
        ]
        if not export_items:
            return False
        export_items[0].click_input()
    except Exception:
        return False

    sub_menu = _find_menu_popup(timeout=3)
    if sub_menu is None:
        return False

    try:
        wav_items = [
            item for item in sub_menu.descendants(control_type="MenuItem")
            if "wav" in (item.window_text() or "").lower()
        ]
        if not wav_items:
            return False
        wav_items[0].click_input()
        return True
    except Exception:
        return False


def _try_export_via_explicit_text(win) -> bool:
    labels = [
        "Mixdown To Wav File",
        "Export Wav Files",
        "Export Wav Files To...",
        "Export Wav File",
        "Export Wav File...",
    ]

    def _click_menu_item(menu_root, text: str) -> bool:
        items = [
            item for item in menu_root.descendants(control_type="MenuItem")
            if (item.window_text() or "").strip() == text
        ]
        if not items:
            return False
        items[0].click_input()
        return True

    win.set_focus()
    send_keys("%f")
    file_menu = _find_menu_popup(timeout=3)
    if file_menu is None:
        return False

    if not _click_menu_item(file_menu, "Export Audio"):
        return False

    export_menu = _find_menu_popup(timeout=3)
    if export_menu is None:
        return False

    for label in labels:
        if _click_menu_item(export_menu, label):
            _log(f"Menu clicked via explicit text: {label}")
            return True
    return False


def _click_menu_item_contains(menu_root, token: str):
    token = (token or "").strip().lower()
    if not token:
        return None
    try:
        items = menu_root.descendants(control_type="MenuItem")
    except Exception:
        return None
    for item in items:
        txt = (item.window_text() or "").strip().lower()
        if token in txt:
            try:
                item.click_input()
                return item
            except Exception:
                continue
    return None


def _click_menu_item_with_all_tokens(menu_root, tokens):
    tokens = [str(t).strip().lower() for t in (tokens or []) if str(t).strip()]
    if not tokens:
        return None
    try:
        items = menu_root.descendants(control_type="MenuItem")
    except Exception:
        return None
    for item in items:
        txt = (item.window_text() or "").strip().lower()
        if all(tok in txt for tok in tokens):
            try:
                item.click_input()
                return item
            except Exception:
                continue
    return None


def _try_open_batch_edit_dialog(win, timeout: int = 4):
    try:
        win.set_focus()
        send_keys("%p")
        time.sleep(0.25)
    except Exception:
        return None
    menu = _find_menu_popup(timeout=timeout)
    if menu is None:
        return None
    batch_item = (
        _click_menu_item_contains(menu, "batch")
        or _click_menu_item_contains(menu, "edit")
    )
    if batch_item is None:
        return None
    try:
        return _wait_for_dialog((r".*Batch.*Edit.*", r".*Batch.*", r".*Edit.*"), timeout=6)
    except Exception:
        return None


def _window_title(win) -> str:
    try:
        return (win.window_text() or "").strip()
    except Exception:
        return ""


def _is_note_editor_context(win) -> bool:
    # In note editor, title usually looks like: "Track1 - Verse L1"
    title = _window_title(win).lower()
    if not title:
        return False
    if "openutau" in title and " - " not in title:
        return False
    return (" - " in title) and ("track" in title or "verse" in title or "chorus" in title or "bridge" in title)


def _try_merge_all_parts(win) -> bool:
    """
    Arrangement pre-step:
      Ctrl+A (select parts) -> right-click part lane -> Merge parts
    Returns True if merge command was clicked, False otherwise.
    """
    try:
        win.set_focus()
    except Exception:
        return False

    # If we are already in note editor, treat this as already past merge stage.
    if _is_note_editor_context(win):
        return True

    try:
        r = win.rectangle()
    except Exception:
        return False

    # First, focus likely arrangement part lanes.
    click_points = [
        (0.30, 0.26),
        (0.50, 0.26),
        (0.70, 0.26),
        (0.45, 0.30),
        (0.55, 0.30),
        (0.40, 0.36),
        (0.60, 0.36),
        (0.50, 0.28),
    ]
    for xr, yr in click_points:
        try:
            x = int((r.right - r.left) * xr)
            y = int((r.bottom - r.top) * yr)
            win.click_input(coords=(x, y))
            time.sleep(0.15)
            send_keys("^a")
            time.sleep(0.15)

            # Exact requested flow: context menu -> DOWN x3 -> Enter (Merge Edits).
            for hotkey in ("+{F10}", "{APPS}"):
                try:
                    send_keys(hotkey)
                    time.sleep(0.25)
                except Exception:
                    continue
                menu = _find_menu_popup(timeout=2)
                if menu is None:
                    continue
                try:
                    send_keys("{DOWN 3}")
                    time.sleep(0.15)
                    send_keys("{ENTER}")
                    time.sleep(0.8)
                    return True
                except Exception:
                    try:
                        send_keys("{ESC}")
                    except Exception:
                        pass
        except Exception:
            continue
    return False


def _ensure_note_editor_context(win, tries: int = 6) -> bool:
    if _is_note_editor_context(win):
        return True

    try:
        win.set_focus()
    except Exception:
        return False

    # Try opening the selected part editor via Enter first.
    for _ in range(2):
        try:
            send_keys("{ENTER}")
            time.sleep(0.45)
            if _is_note_editor_context(win):
                return True
        except Exception:
            pass

    # Try repeated double-clicks at likely part-lane areas.
    try:
        r = win.rectangle()
    except Exception:
        return False
    ratios = [
        (0.30, 0.26),
        (0.50, 0.26),
        (0.70, 0.26),
        (0.35, 0.30),
        (0.45, 0.30),
        (0.55, 0.30),
        (0.40, 0.36),
        (0.60, 0.36),
        (0.50, 0.25),
    ]
    for i in range(min(tries, len(ratios))):
        xr, yr = ratios[i]
        try:
            x = int((r.right - r.left) * xr)
            y = int((r.bottom - r.top) * yr)
            win.click_input(coords=(x, y))
            time.sleep(0.1)
            win.double_click_input(coords=(x, y))
            time.sleep(0.55)
            if _is_note_editor_context(win):
                return True
        except Exception:
            continue
    return False


def _try_apply_rendered_pitch_via_batch_menu(win) -> bool:
    """
    Exact UI path used in the note editor window:
      Batch Edits -> Notes -> Load Rendered Pitch
    """
    try:
        win.set_focus()
    except Exception:
        return False
    if not _is_note_editor_context(win):
        return False

    # Ensure note selection is active in the current part editor.
    try:
        send_keys("^a")
        time.sleep(0.2)
    except Exception:
        pass

    # Open top menu: Batch Edits (Alt+B).
    try:
        send_keys("%b")
        time.sleep(0.25)
    except Exception:
        return False

    menu = _find_menu_popup(timeout=3)
    if menu is None:
        return False

    # First level: Notes
    notes_item = _click_menu_item_contains(menu, "notes")
    if notes_item is None:
        return False
    time.sleep(0.2)

    # Second level: Load Rendered Pitch
    sub_menu = _find_menu_popup(timeout=3)
    if sub_menu is None:
        return False
    load_item = (
        _click_menu_item_with_all_tokens(sub_menu, ["render", "pitch"])
        or _click_menu_item_with_all_tokens(sub_menu, ["load", "pitch"])
        or _click_menu_item_contains(sub_menu, "rendered pitch")
        or _click_menu_item_contains(sub_menu, "load rendered")
    )
    if load_item is None:
        return False

    _wait_for_cache_stable(
        r"C:\Users\adolf\Documents\OpenUtau\Cache",
        stable_seconds=8,
        timeout=180,
    )
    return True


def _try_focus_part_subwindow(win) -> bool:
    if _ensure_note_editor_context(win):
        return True

    # Try several likely note-area coordinates because UI layout/zoom varies.
    ratios = [
        (0.72, 0.22),
        (0.68, 0.26),
        (0.60, 0.28),
        (0.74, 0.30),
    ]
    try:
        r = win.rectangle()
    except Exception:
        return False

    for xr, yr in ratios:
        try:
            x = int((r.right - r.left) * xr)
            y = int((r.bottom - r.top) * yr)
            win.click_input(coords=(x, y))
            time.sleep(0.12)
            win.double_click_input(coords=(x, y))
            time.sleep(0.45)
            # Probe whether part editor context is active by opening Batch Edit.
            dlg = _try_open_batch_edit_dialog(win, timeout=2)
            if dlg is not None:
                try:
                    send_keys("{ESC}")
                    time.sleep(0.15)
                except Exception:
                    pass
                return True
        except Exception:
            continue
    return False


def _try_apply_rendered_pitch(win) -> bool:
    """
    Best-effort automation for:
      Part -> Select all notes -> Batch Edit -> Load Rendered Pitch
    UI labels can vary by OpenUtau version, so this silently falls back.
    """
    try:
        win.set_focus()
    except Exception:
        return False

    # Hard gate: subwindow must actually be open.
    if not _ensure_note_editor_context(win):
        return False

    # Preferred path for this UI: Batch Edits -> Notes -> Load Rendered Pitch.
    if _try_apply_rendered_pitch_via_batch_menu(win):
        return True

    # Focus the note/part subwindow exactly like manual double-click flow.
    if not _try_focus_part_subwindow(win):
        return False

    try:
        # Part -> Select All Notes first.
        send_keys("%p")
        time.sleep(0.25)
        part_menu = _find_menu_popup(timeout=2)
        if part_menu is not None:
            _click_menu_item_contains(part_menu, "select all")
        time.sleep(0.2)
        # Fallback global select.
        send_keys("^a")
        time.sleep(0.2)
    except Exception:
        pass

    # Open Part -> Batch Edit dialog.
    dlg = _try_open_batch_edit_dialog(win, timeout=3)
    if dlg is None:
        return False

    # Required sequence: Batch Edit -> Notes -> Load Rendered Pitch.
    notes_selected = False
    try:
        for ctrl in dlg.descendants():
            txt = (ctrl.window_text() or "").strip().lower()
            if txt == "notes" or txt.startswith("notes"):
                ctrl.click_input()
                notes_selected = True
                time.sleep(0.25)
                break
    except Exception:
        notes_selected = False
    if not notes_selected:
        return False

    # Click option containing "Load Rendered Pitch" (wording may vary).
    picked = False
    for token in ["load rendered pitch", "rendered pitch", "load pitch"]:
        try:
            # Try list/menu item style controls first.
            for ctrl in dlg.descendants():
                txt = (ctrl.window_text() or "").strip().lower()
                if token in txt:
                    ctrl.click_input()
                    picked = True
                    break
            if picked:
                break
        except Exception:
            continue

    if not picked:
        return False

    # Confirm dialog if needed.
    for button in ["OK", "Apply", "Done"]:
        if _click_dialog_primary(dlg, button):
            break
    # Give OpenUtau time to build rendered-pitch curves before export.
    _wait_for_cache_stable(
        r"C:\Users\adolf\Documents\OpenUtau\Cache",
        stable_seconds=8,
        timeout=180,
    )
    return True


def open_ustx_file(
    win,
    ustx_path: str,
    open_key: str = "^o",
    open_dialog_title_re: Union[str, Iterable[str]] = (r"Open.*", r".*Open.*"),
):
    win.set_focus()
    send_keys(open_key)

    try:
        dlg = _wait_for_dialog(open_dialog_title_re)
        _set_dialog_filename(dlg, ustx_path)
        if not _click_dialog_primary(dlg, "Open"):
            send_keys("%o")
        try:
            dlg.wait_not("visible", timeout=10)
        except Exception:
            pass
    except Exception:
        pass




def export_wav_file(
    win,
    wav_path: str,
    timeout_sec: int = 400,
    menu_down: int = 10,
    submenu_down: int = 1,
    export_dir: Optional[str] = None,
    min_duration_sec: Optional[float] = None,
):
   
    win.set_focus()
    time.sleep(0.5)

    send_keys("%")
    time.sleep(0.4)
    send_keys("{ENTER}")
    time.sleep(0.6)
    send_keys(f"{{DOWN {menu_down}}}")
    time.sleep(0.4)
    send_keys("{ENTER}")
    time.sleep(0.6)
    send_keys(f"{{DOWN {submenu_down}}}")
    time.sleep(0.4)
    send_keys("{ENTER}")
    time.sleep(1.2)

    # Find Save dialog.
    dlg = None
    for _ in range(15):
        for w in Desktop(backend="uia").windows():
            try:
                cls = w.class_name()
                txt = w.window_text().lower()
                if cls == "#32770" or "save" in txt or "export" in txt:
                    dlg = w
                    break
            except Exception:
                pass
        if dlg:
            break
        time.sleep(1)

    if dlg:
        out_path = Path(wav_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _set_dialog_directory(str(out_path.parent.resolve()))
        _set_dialog_filename(dlg, out_path.name)
        time.sleep(0.3)
        saved = False
        for _ in range(3):
            if _click_dialog_primary(dlg, "Save") or _click_dialog_primary(dlg, "OK"):
                saved = True
                break
            time.sleep(0.3)
        if not saved:
            send_keys("{ENTER}")
        # Export starts asynchronously; give renderer time to initialize.
        time.sleep(3.0)
        _confirm_overwrite_if_needed()
    else:
        send_keys("{ENTER}")
        time.sleep(3.0)

    out_path = Path(wav_path)
    export_path = Path(export_dir) if export_dir else out_path.parent
    fallback_path = Path(r"output\openutau")
    legacy_path = Path(r"output")
    export_paths = []
    for p in [export_path, fallback_path, legacy_path]:
        if p.exists() and p not in export_paths:
            export_paths.append(p)
    before = {p: {f.name for f in p.glob("*.wav")} for p in export_paths}
    start = time.time()
    while time.time() - start < timeout_sec:
        if _wait_for_wav_complete(out_path, timeout_sec=8, min_duration_sec=min_duration_sec):
            return str(out_path)
        for p in export_paths:
            after = {f.name for f in p.glob("*.wav")}
            new_files = [f for f in p.glob("*.wav") if f.name in (after - before[p])]
            if new_files:
                newest = max(new_files, key=lambda f: f.stat().st_mtime)
                if _wait_for_wav_complete(newest, timeout_sec=8, min_duration_sec=min_duration_sec):
                    return str(newest)
        time.sleep(1)

    # Timeout — but before failing, scan ALL known locations for any recent WAV
    all_scan = [
        Path(r"output\openutau"),
        Path(r"output"),
        Path(export_dir) if export_dir else None,
    ]
    for p in all_scan:
        if p and p.exists():
            wavs = sorted(p.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)
            for w in wavs[:3]:
                age = time.time() - w.stat().st_mtime
                if (age < 600 and _wait_for_wav_complete(w, timeout_sec=8, min_duration_sec=min_duration_sec)):  # made in last 10 min
                    print(f"✅ Found export at fallback path: {w}")
                    return str(w)

    raise OpenUtauAutomationError("Export timed out — file never appeared.")


def render_ustx_to_wav(
    ustx_path: str,
    export_dir: str,
    exe_path: Optional[str] = None,
    autostart: bool = True,
    wait_sec: int = 20,
    open_key: str = "^o",
    export_key: str = "^e",
    export_menu_down: Optional[int] = None,
    export_submenu_down: Optional[int] = None,
    export_timeout_sec: int = 900,
    apply_rendered_pitch: bool = True,
    merge_parts_before_pitch: bool = False,
    require_merge_parts: bool = False,
    require_rendered_pitch: bool = True,
    min_duration_sec: Optional[float] = None,
) -> str:
    export_dir_path = Path(export_dir)
    export_dir_path.mkdir(parents=True, exist_ok=True)
    out_path = export_dir_path / (Path(ustx_path).stem + ".wav")

    # Snapshot WAVs before export so we can detect new ones
    all_scan_paths = [
        export_dir_path,
        Path(r"output\openutau"),
        Path(r"output"),
    ]
    before_snaps = {}
    for p in all_scan_paths:
        if p.exists():
            before_snaps[p] = {f.name for f in p.glob("*.wav")}

    _, win = ensure_openutau_running(exe_path, autostart=autostart, wait_sec=wait_sec)
    open_ustx_file(win, str(Path(ustx_path).resolve()), open_key=open_key)
    _wait_for_cache_stable(r"C:\Users\adolf\Documents\OpenUtau\Cache")
    if merge_parts_before_pitch:
        try:
            if _try_merge_all_parts(win):
                _log("Merged selected parts before rendered-pitch step.")
            else:
                msg = "Merge parts step failed (Ctrl+A -> context menu -> Merge)."
                if require_merge_parts:
                    raise OpenUtauAutomationError(msg)
                _log(msg + " Continuing because require_merge_parts=False.")
        except Exception as exc:
            if require_merge_parts:
                raise
            _log(f"Merge-parts pre-step failed: {exc}")
    if apply_rendered_pitch:
        try:
            if _try_apply_rendered_pitch(win):
                _log("Applied rendered pitch via Part > Batch Edit.")
                _wait_for_cache_stable(
                    r"C:\Users\adolf\Documents\OpenUtau\Cache",
                    stable_seconds=8,
                    timeout=240,
                )
            else:
                msg = "Rendered pitch step failed (could not open subwindow/Batch Edit/Notes path)."
                if require_rendered_pitch:
                    raise OpenUtauAutomationError(msg)
                _log(msg + " Continuing because require_rendered_pitch=False.")
        except Exception as exc:
            if require_rendered_pitch:
                raise
            _log(f"Rendered pitch step failed, continuing export: {exc}")

    try:
        out_path_str = export_wav_file(
            win,
            str(out_path.resolve()),
            timeout_sec=export_timeout_sec,
            menu_down=export_menu_down or 11,
            submenu_down=export_submenu_down or 2,
            export_dir=str(export_dir_path.resolve()),
            min_duration_sec=min_duration_sec,
        )
        if out_path_str:
            return out_path_str
    except OpenUtauAutomationError:
        pass  # timed out — fall through to scan

    # Scan all locations for any new WAV created after we started
    for p, before_set in before_snaps.items():
        if not p.exists():
            continue
        new_wavs = [f for f in p.glob("*.wav") if f.name not in before_set and _wait_for_wav_complete(f, timeout_sec=8, min_duration_sec=min_duration_sec)]
        if new_wavs:
            newest = max(new_wavs, key=lambda f: f.stat().st_mtime)
            print(f"✅ Found export: {newest}")
            return str(newest)

    # Last resort: newest WAV anywhere in output created in last 10 minutes
    for p in all_scan_paths:
        if not p.exists():
            continue
        wavs = sorted(p.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)
        for w in wavs[:3]:
            if ((time.time() - w.stat().st_mtime) < 600 and _wait_for_wav_complete(w, timeout_sec=8, min_duration_sec=min_duration_sec)):
                print(f"✅ Found recent export: {w}")
                return str(w)

    raise OpenUtauAutomationError("Export finished but no output wav was found.")

