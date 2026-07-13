"""Unit tests for the resident-session auto-viewer (``_watch``)."""

import asyncio

import pytest

from h5i.orchestra._conductor import Conductor
from h5i.orchestra._watch import (
    Opener,
    SessionWatcher,
    resolve_opener,
    session_prefix,
    template_argv,
    wt_argv,
)

# ── opener resolution ────────────────────────────────────────────────────────


def _no_binary(_name: str) -> None:
    return None


def test_template_wins_over_everything():
    opener = resolve_opener(
        "kitty -e tmux attach -t {session}",
        env={"TMUX": "/tmp/tmux-1000/default,42,0"},
        which=_no_binary,
    )
    assert opener.kind == "spawn"
    assert opener.argv("h5i-orch-r-a") == [
        "kitty", "-e", "tmux", "attach", "-t", "h5i-orch-r-a"
    ]


def test_template_without_placeholder_gets_attach_appended():
    assert template_argv("foot --hold", "s1") == [
        "foot", "--hold", "tmux", "attach-session", "-t", "s1"
    ]


def test_env_template_is_honored():
    opener = resolve_opener(env={"H5I_TERMINAL": "myterm -e"}, which=_no_binary)
    assert opener.name == "myterm"
    assert opener.argv("s")[:2] == ["myterm", "-e"]


def test_inside_tmux_links_windows():
    opener = resolve_opener(env={"TMUX": "sock,1,0"}, which=_no_binary)
    assert opener.kind == "tmux-link"


def test_wsl_uses_windows_terminal():
    opener = resolve_opener(
        env={"WSL_DISTRO_NAME": "Ubuntu"},
        which=lambda name: name if name in ("wt.exe", "wsl.exe") else None,
    )
    assert opener.name == "wt.exe"
    argv = opener.argv("s1")
    assert argv[:2] == ["wt.exe", "-w"]
    assert ["wsl.exe", "-d", "Ubuntu"] == argv[argv.index("wsl.exe"):][:3]
    assert argv[-4:] == ["tmux", "attach-session", "-t", "s1"]


def test_wt_argv_without_distro():
    assert "-d" not in wt_argv("s")


def test_gui_terminal_on_display():
    opener = resolve_opener(
        env={"DISPLAY": ":0"},
        which=lambda name: name if name == "alacritty" else None,
    )
    assert opener.name == "alacritty"
    assert opener.argv("s1")[0] == "alacritty"


def test_headless_falls_back_to_hint():
    assert resolve_opener(env={}, which=_no_binary).kind == "hint"


# ── the watcher loop ─────────────────────────────────────────────────────────


class ScriptedWatcher(SessionWatcher):
    """A watcher over a scripted tmux session list — no subprocesses."""

    def __init__(self, run_id: str, listings, **kwargs):
        self.opened: list[str] = []
        self.echoed: list[str] = []
        super().__init__(
            run_id,
            opener=Opener("fake", "spawn", lambda s: ["true", s]),
            echo=self.echoed.append,
            **kwargs,
        )
        self._listings = iter(listings)

    async def _list_sessions(self):
        return next(self._listings)

    async def _spawn(self, argv):
        self.opened.append(argv[1])


@pytest.mark.asyncio
async def test_opens_each_new_session_once():
    prefix = session_prefix("run1")
    w = ScriptedWatcher(
        "run1",
        [
            ["unrelated"],
            [f"{prefix}claude", "unrelated"],
            [f"{prefix}claude", f"{prefix}codex"],
            [f"{prefix}claude", f"{prefix}codex"],
        ],
    )
    for _ in range(4):
        assert await w.poll_once()
    assert w.opened == [f"{prefix}claude", f"{prefix}codex"]


@pytest.mark.asyncio
async def test_reopens_a_session_that_died_and_came_back():
    session = session_prefix("run1") + "claude"
    w = ScriptedWatcher("run1", [[session], [], [session]])
    for _ in range(3):
        await w.poll_once()
    assert w.opened == [session, session]


@pytest.mark.asyncio
async def test_no_tmux_binary_stops_the_loop():
    class NoTmux(ScriptedWatcher):
        async def _list_sessions(self):
            return None

    assert not await NoTmux("run1", []).poll_once()


@pytest.mark.asyncio
async def test_broken_viewer_degrades_to_hint():
    session = session_prefix("run1") + "claude"

    class Broken(ScriptedWatcher):
        async def _spawn(self, argv):
            raise OSError("boom")

    w = Broken("run1", [[session]])
    assert await w.poll_once()
    assert any(f"tmux attach -t {session}" in line for line in w.echoed)


# ── Conductor wiring ─────────────────────────────────────────────────────────


def test_watch_defaults_follow_the_launcher():
    assert Conductor(".", "r", launcher="resident")._watch is True
    assert Conductor(".", "r")._watch is False
    assert Conductor(".", "r", launcher="resident", watch=False)._watch is False
    c = Conductor(".", "r", watch="kitty -e tmux attach -t {session}")
    assert c._watch == "kitty -e tmux attach -t {session}"


@pytest.mark.asyncio
async def test_close_cancels_the_watch_task():
    c = Conductor(".", "r", launcher="resident")

    async def forever():
        await asyncio.Event().wait()

    c._watch_task = asyncio.ensure_future(forever())
    task = c._watch_task
    await c.close()
    assert task.cancelled()
    assert c._watch_task is None
