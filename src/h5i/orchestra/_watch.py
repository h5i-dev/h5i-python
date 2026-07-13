"""Auto-attach viewers for resident agent sessions — ``Conductor(watch=True)``.

The ``"resident"`` launcher brings each agent up in a *detached* tmux session
named ``h5i-orch-<run>-<agent>``, which normally means hunting for the right
``tmux attach -t …`` in a second terminal. Watching removes the hunt: a
background task polls for those sessions and opens an interactive viewer on
each one as it appears (and again if it dies and comes back).

How a viewer is opened, in order of preference:

1. an explicit command template — ``watch="kitty --title {session} tmux
   attach -t {session}"`` or ``$H5I_TERMINAL``. ``{session}`` is replaced
   with the session name; a template without the placeholder gets
   ``tmux attach-session -t <session>`` appended as trailing argv (the
   ``terminal -e``-style convention);
2. already inside tmux (``$TMUX``): the agent's window is **linked** into
   your current session — no nested clients, switch to it like any other
   window (it is removed when the agent session ends);
3. WSL with Windows Terminal on PATH: a new ``wt.exe`` tab per agent;
4. a GUI terminal on ``$DISPLAY``/``$WAYLAND_DISPLAY`` (wezterm, kitty,
   alacritty, gnome-terminal, konsole, foot, x-terminal-emulator, xterm);
5. otherwise: a hint line on stderr with the exact attach command.

A broken viewer never fails the score — every opener error degrades to the
stderr hint.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import sys
from typing import Callable, Mapping, NamedTuple

__all__ = ["Opener", "SessionWatcher", "resolve_opener", "session_prefix"]


def session_prefix(run_id: str) -> str:
    """The resident launcher's session-name prefix for a run (mirrors the
    Rust side's ``h5i-orch-{run_id}-{agent_id}``)."""
    return f"h5i-orch-{run_id}-"


def _attach_argv(session: str) -> list[str]:
    return ["tmux", "attach-session", "-t", session]


def template_argv(template: str, session: str) -> list[str]:
    """Expand a user command template into argv for one session."""
    words = shlex.split(template)
    if any("{session}" in w for w in words):
        return [w.replace("{session}", session) for w in words]
    return words + _attach_argv(session)


def wt_argv(session: str, distro: str | None = None) -> list[str]:
    """A new Windows Terminal tab attached to ``session`` (WSL interop)."""
    wsl = ["wsl.exe"] + (["-d", distro] if distro else [])
    return ["wt.exe", "-w", "0", "new-tab", "--title", session, *wsl, "-e", *_attach_argv(session)]


#: GUI terminals we know how to hand an attach command, most specific first.
_GUI_TERMINALS: tuple[tuple[str, Callable[[str], list[str]]], ...] = (
    ("wezterm", lambda s: ["wezterm", "start", "--", *_attach_argv(s)]),
    ("kitty", lambda s: ["kitty", "--title", s, *_attach_argv(s)]),
    ("alacritty", lambda s: ["alacritty", "--title", s, "-e", *_attach_argv(s)]),
    ("gnome-terminal", lambda s: ["gnome-terminal", "--title", s, "--", *_attach_argv(s)]),
    ("konsole", lambda s: ["konsole", "-p", f"tabtitle={s}", "-e", *_attach_argv(s)]),
    ("foot", lambda s: ["foot", "--title", s, *_attach_argv(s)]),
    ("x-terminal-emulator", lambda s: ["x-terminal-emulator", "-e", *_attach_argv(s)]),
    ("xterm", lambda s: ["xterm", "-T", s, "-e", *_attach_argv(s)]),
)


class Opener(NamedTuple):
    """How viewers are opened: spawn argv, link a tmux window, or just hint."""

    name: str
    kind: str  # "spawn" | "tmux-link" | "hint"
    argv: Callable[[str], list[str]] | None = None


def resolve_opener(
    template: str | None = None,
    *,
    env: Mapping[str, str] = os.environ,
    which: Callable[[str], str | None] = shutil.which,
) -> Opener:
    """Pick the best way to surface agent sessions in this environment."""
    template = template or env.get("H5I_TERMINAL")
    if template:
        name = shlex.split(template)[0]
        return Opener(name, "spawn", lambda s: template_argv(template, s))
    if env.get("TMUX"):
        return Opener("tmux link-window", "tmux-link")
    if which("wt.exe") and which("wsl.exe"):
        distro = env.get("WSL_DISTRO_NAME")
        return Opener("wt.exe", "spawn", lambda s: wt_argv(s, distro))
    if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        for name, build in _GUI_TERMINALS:
            if which(name):
                return Opener(name, "spawn", build)
    return Opener("hint", "hint")


class SessionWatcher:
    """Polls tmux for a run's agent sessions and opens a viewer on each.

    Sessions appear lazily (the resident launcher brings one up on an
    agent's *first turn*), so the watcher runs for the whole score. A
    session that vanishes and comes back gets a fresh viewer.
    """

    def __init__(
        self,
        run_id: str,
        *,
        template: str | None = None,
        opener: Opener | None = None,
        poll_interval: float = 1.0,
        echo: Callable[[str], None] | None = None,
    ):
        self._prefix = session_prefix(run_id)
        self._opener = opener or resolve_opener(template)
        self._poll_interval = poll_interval
        self._echo = echo or (lambda line: print(line, file=sys.stderr, flush=True))
        self._open_now: set[str] = set()

    def _agent(self, session: str) -> str:
        return session[len(self._prefix):] or session

    async def run(self) -> None:
        """Poll until cancelled (or until tmux turns out not to exist)."""
        how = (
            f"each opens in {self._opener.name} as its first turn starts"
            if self._opener.kind != "hint"
            else "attach commands are printed as each comes up"
        )
        self._echo(f"[h5i] watching for agent sessions ({self._prefix}*) — {how}")
        while await self.poll_once():
            await asyncio.sleep(self._poll_interval)

    async def poll_once(self) -> bool:
        """One poll step; returns False when polling can never succeed."""
        names = await self._list_sessions()
        if names is None:
            self._echo(
                "[h5i] tmux not found — agent sessions cannot be watched "
                "(the resident launcher needs tmux)"
            )
            return False  # no tmux binary — sessions will never appear
        current = {n for n in names if n.startswith(self._prefix)}
        for session in sorted(self._open_now - current):
            self._echo(
                f"[h5i] agent '{self._agent(session)}' session ended ({session})"
            )
        self._open_now &= current  # a vanished session may come back
        for session in sorted(current - self._open_now):
            self._open_now.add(session)
            await self._open(session)
        return True

    async def _list_sessions(self) -> list[str] | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "list-sessions",
                "-F",
                "#{session_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return None
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            return []  # no tmux server yet — keep polling
        return out.decode(errors="replace").splitlines()

    async def _open(self, session: str) -> None:
        opener = self._opener
        agent = self._agent(session)
        try:
            if opener.kind == "spawn":
                assert opener.argv is not None
                await self._spawn(opener.argv(session))
                self._echo(
                    f"[h5i] agent '{agent}' session up — opened in {opener.name} "
                    f"(or: tmux attach -t {session})"
                )
                return
            if opener.kind == "tmux-link":
                await self._link_window(session)
                self._echo(
                    f"[h5i] agent '{agent}' session up — linked as window "
                    f"'{session}' in your current tmux session"
                )
                return
        except Exception as e:  # a broken viewer must not fail the score
            self._echo(
                f"[h5i] agent '{agent}' session up, but its viewer failed ({e}) — "
                f"attach with: tmux attach -t {session}"
            )
            return
        self._echo(
            f"[h5i] agent '{agent}' session up — view it with: tmux attach -t {session}"
        )

    async def _spawn(self, argv: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        # Terminals live as long as the viewer stays open; reap in background.
        asyncio.ensure_future(proc.wait())

    async def _link_window(self, session: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "list-windows",
            "-t",
            session,
            "-F",
            "#{window_id}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        window_ids = out.decode(errors="replace").split()
        if proc.returncode != 0 or not window_ids:
            raise RuntimeError(f"no windows found in tmux session '{session}'")
        link = await asyncio.create_subprocess_exec(
            "tmux",
            "link-window",
            "-d",
            "-a",
            "-s",
            window_ids[0],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        if await link.wait() != 0:
            raise RuntimeError("tmux link-window failed")
