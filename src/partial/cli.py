"""partial: reconstruct a damaged biosignal session from its raw tape."""
from __future__ import annotations

import json
import os
from pathlib import Path

import typer

app = typer.Typer(help=__doc__, no_args_is_help=True, add_completion=False)


def _load_env():
    p = Path(".env")
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


@app.command()
def synth(out: Path = Path("data/session-synth"), trials: int = 8, seed: int = 20261107):
    """Make a synthetic session in the real session's shape (no hardware)."""
    from .synth import synth as _s
    m = _s(out, trials=trials, seed=seed)
    typer.echo(f"wrote {out}: {m['packets']} packets, {m['n_events']} trials, {m['tape_bytes']} tape bytes")


@app.command()
def corrupt(session: Path, out: Path = typer.Option(None), seed: int = 1,
            damage: list[str] = typer.Option(None, help="subset of drop_meta truncate_events strip_reads garbage_bytes cut_range")):
    """Copy a session and damage it in named, reproducible ways."""
    from .corrupt import corrupt as _c
    out = out or session.parent / (session.name + "-damaged")
    rep = _c(session, out, seed=seed, damage=damage or None)
    for a in rep["applied"]:
        typer.echo("  " + a)
    typer.echo(f"damaged copy at {out}")


@app.command()
def reconstruct(session: Path, max_steps: int = 40, model: str = None,
                fake_model: bool = typer.Option(False, "--fake-model", help="scripted stand-in, no API")):
    """Run the reconstruction agent on a session folder."""
    _load_env()
    from .agent import reconstruct as _r
    log = _r(session, max_steps=max_steps, model=model, fake_model=fake_model or None)
    typer.echo(f"{log.stopped} after {len(log.steps)} steps, {log.elapsed_s}s, model {log.model}")
    for need in ("parsed_agent.npz", "reconstruction.json", "figures/overview.png"):
        typer.echo(f"  {'ok ' if (session / need).exists() else 'MISSING '} {need}")


@app.command()
def score(session: Path, truth: Path = typer.Option(..., help="the untouched session")):
    """Score a reconstruction against the held-out oracle and the untouched session."""
    from .score import format_table, score as _sc
    res = _sc(session, truth)
    typer.echo(format_table(res))
    (session / "score.json").write_text(json.dumps(res, indent=1))


@app.command()
def demo(out: Path = Path("demo-run"), trials: int = 8, seed: int = 20261107,
         fake_model: bool = typer.Option(False, "--fake-model"), max_steps: int = 40, model: str = None):
    """synth, corrupt, reconstruct, score: the whole thing in one go."""
    _load_env()
    from .agent import reconstruct as _r
    from .corrupt import corrupt as _c
    from .score import format_table, score as _sc
    from .synth import synth as _s
    clean, damaged = out / "session-synth", out / "session-synth-damaged"
    m = _s(clean, trials=trials, seed=seed)
    typer.echo(f"synth: {m['packets']} packets, {m['n_events']} trials")
    rep = _c(clean, damaged, seed=seed)
    for a in rep["applied"]:
        typer.echo("  damage: " + a)
    log = _r(damaged, max_steps=max_steps, model=model, fake_model=fake_model or None, verbose=False)
    typer.echo(f"agent: {log.stopped} after {len(log.steps)} steps, {log.elapsed_s}s, model {log.model}")
    res = _sc(damaged, clean)
    typer.echo(format_table(res, title=f"\nreconstruction of {damaged.name} vs {clean.name}"))
    (damaged / "score.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    app()
