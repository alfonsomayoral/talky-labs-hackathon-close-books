"""closebooks run | score | diff | validate | holdout build | serve."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluate import score_file, segment_changes, validate_file
from .load import load_phase
from .paths import RUNS


def _run_dir(name: str) -> Path:
    path = Path(name)
    return path if path.exists() else RUNS / name


def _cmd_run(args: argparse.Namespace) -> int:
    from .pipeline import run_pipeline

    run = run_pipeline(args.phase, out=Path(args.out) if args.out else None)
    meta = json.loads((run / "run.json").read_text())
    size = meta["csvBytes"] / 1e6
    print(f"{run}\n{meta['txns']} txns, {meta['rows']} rows, {size:.1f} MB, {meta['durationMs'] / 1000:.0f} s")
    if meta["score"]:
        print(f"score {meta['score']['score']}  {meta['score']['metrics']}  {meta['score']['errors'][:3]}")
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    run = _run_dir(args.run)
    phase = json.loads((run / "run.json").read_text())["phase"]
    result = score_file(run / "submission.csv.gz", phase)
    if not result["ok"]:
        print(json.dumps(result["errors"], indent=1))
        return 1
    print(f"score {result['score']}  {result['metrics']}")
    if args.compare:
        base = score_file(_run_dir(args.compare) / "submission.csv.gz", phase)
        print(f"base  {base['score']}  {base['metrics']}")
        print(f"{'segment':34}{'n':>9}{'base':>9}{'now':>9}{'delta':>9}")
        for seg, n, before, now in segment_changes(base["segments"], result["segments"]):
            print(f"{seg:34}{n:>9}{before:>9.4f}{now:>9.4f}{now - before:>+9.4f}")
    else:
        for seg, info in sorted(result["segments"].items(), key=lambda kv: -kv[1]["n"]):
            print(f"{seg:34}{info['n']:>9}{info['accuracy']:>9.4f}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    from .diff import report

    run = _run_dir(args.run)
    print(report(run, json.loads((run / "run.json").read_text())["phase"], args.segment))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    report = validate_file(Path(args.csv), load_phase(args.phase))
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


def _cmd_holdout(args: argparse.Namespace) -> int:
    from .holdout import build_drift, build_holdout

    print(build_drift() if args.drift else build_holdout())
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api.app import create_app
    from .api.store import Store

    store = Store(RUNS)
    ids = store.run_ids()
    warm = _run_dir(args.run).name if args.run else (ids[0] if ids else None)
    app = create_app(store=store, warm=warm)
    if warm:
        print(f"opening {warm}...", flush=True)
        store.preload(warm)  # connections are accepted only once the served run is ready
    print(f"serving {RUNS} on http://{args.host}:{args.port}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="closebooks")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--phase", required=True)
    run.add_argument("--out")
    run.set_defaults(func=_cmd_run)

    score = sub.add_parser("score")
    score.add_argument("run")
    score.add_argument("--compare")
    score.set_defaults(func=_cmd_score)

    diff = sub.add_parser("diff")
    diff.add_argument("run")
    diff.add_argument("--segment")
    diff.set_defaults(func=_cmd_diff)

    validate = sub.add_parser("validate")
    validate.add_argument("csv")
    validate.add_argument("--phase", required=True)
    validate.set_defaults(func=_cmd_validate)

    holdout = sub.add_parser("holdout")
    holdout_sub = holdout.add_subparsers(dest="action", required=True)
    build = holdout_sub.add_parser("build")
    build.add_argument("--drift", action="store_true")
    build.set_defaults(func=_cmd_holdout)

    serve = sub.add_parser("serve")
    serve.add_argument("run", nargs="?", help="run to open at startup (default: the most recent)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
