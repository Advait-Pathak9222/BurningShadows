"""Command entry points owned by the runtime lane.

`controlplane/cli.py` dispatches here for every runtime subcommand rather than growing
its own branch per command. That keeps `cli.py` under a single owner: two lanes appending
argument branches to one function is the merge conflict we are deliberately avoiding.

Implement each command in place. Do not add the subcommand names to `cli.py` or the
`Makefile`; both already route here, and both belong to the other lane.
"""

from __future__ import annotations

from pathlib import Path

RUNTIME_COMMANDS: frozenset[str] = frozenset({"slo-sweep", "chaos", "replay"})


def run_runtime_command(root: Path, command: str) -> int:
    """Dispatch a runtime subcommand. Returns a process exit code."""
    handler = _HANDLERS.get(command)
    if handler is None:  # pragma: no cover - argparse already constrains the choices
        raise ValueError(f"unknown runtime command: {command}")
    return handler(root)


def slo_sweep(root: Path) -> int:
    """Sweep admission limits against a stated service objective.

    Not implemented. See `CODEX_BRIEF_JENISH.md` item J1: state the objective before the
    sweep, then show which limits meet it. The current committed limits are a regression
    at 80 offered RPS, which is a defect until an objective says otherwise.
    """
    print("slo-sweep is not implemented yet (runtime lane, item J1).")
    return 1


def chaos(root: Path) -> int:
    """Exercise detector timeouts, breakers and per-route failure policy.

    Not implemented. See `CODEX_BRIEF_JENISH.md` item J3.
    """
    print("chaos is not implemented yet (runtime lane, item J3).")
    return 1


def replay(root: Path) -> int:
    """Reconstruct a decision from the ledger alone.

    Not implemented. See `CODEX_BRIEF_JENISH.md` item J6, which waits on the effect
    leases from J2 so there is something worth replaying.
    """
    print("replay is not implemented yet (runtime lane, item J6).")
    return 1


_HANDLERS = {"slo-sweep": slo_sweep, "chaos": chaos, "replay": replay}
