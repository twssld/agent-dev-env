"""Command-line interface for the transcript scanner."""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from typing import Any, Dict, Iterable, List, Tuple

from .analyzer import analyze_events, attach_metadata, display_path
from .config import AnalyzerConfig, load_vocab
from .io_jsonl import JsonlStats, read_jsonl
from .io_store import StoreStats, read_store_db
from .render import render_markdown, render_message


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scan_transcripts.py",
        description=(
            "Scan Claude/Cursor JSONL transcripts for repo Harness failure "
            "candidates. Emits coarse hint locations only — the agent must "
            "validate each candidate against the evidence-chain standard."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan transcript roots and emit candidates")
    scan.add_argument(
        "roots",
        nargs="+",
        help="One or more transcript root directories",
    )
    scan.add_argument(
        "--min-score",
        type=float,
        default=AnalyzerConfig.score_floor,
        help=(
            "Minimum candidate score (default %(default)s). "
            "Candidates below this floor are discarded."
        ),
    )
    scan.add_argument("--limit", type=int, default=0)
    scan.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of Markdown",
    )
    scan.add_argument("--output", help="Write output to this file")
    scan.add_argument(
        "--vocab",
        type=pathlib.Path,
        default=None,
        help="Path to vocab.json (default: bundled references/vocab.json)",
    )
    scan.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Number of evidence items to render per category (default %(default)s)",
    )
    scan.add_argument(
        "--similarity-threshold",
        type=float,
        default=None,
        help="Override default similarity threshold (default 0.82)",
    )
    scan.add_argument(
        "--last-action-window",
        type=int,
        default=None,
        help="Override how many events back a steer can refer to (default 25)",
    )
    scan.add_argument(
        "--verbose",
        action="store_true",
        help="Print parser/IO statistics to stderr",
    )

    show = sub.add_parser(
        "show",
        help="Print a window of messages around a hit line",
    )
    show.add_argument("path", help="Transcript path (*.jsonl or store.db)")
    show.add_argument(
        "--line",
        type=int,
        required=True,
        help="Center index (line for jsonl, virtual index for store.db)",
    )
    show.add_argument(
        "--context",
        type=int,
        default=3,
        help="Number of messages before and after to include (default 3)",
    )
    show.add_argument(
        "--max-field",
        type=int,
        default=AnalyzerConfig.show_max_field,
        help="Maximum characters per text field (default %(default)s)",
    )
    return parser


def _config_from_args(args: argparse.Namespace) -> AnalyzerConfig:
    overrides: Dict[str, Any] = {"score_floor": args.min_score}
    if args.similarity_threshold is not None:
        overrides["similarity_threshold"] = args.similarity_threshold
    if args.last_action_window is not None:
        overrides["last_action_window"] = args.last_action_window
    return dataclasses.replace(AnalyzerConfig(), **overrides)


def _scan_paths(
    root: pathlib.Path,
    cfg: AnalyzerConfig,
    vocab,
) -> Iterable[Tuple[Dict[str, Any], JsonlStats | StoreStats, str]]:
    for path in root.rglob("*.jsonl"):
        stats = JsonlStats()
        candidate = analyze_events(
            read_jsonl(path, stats),
            display_path(path, root),
            vocab=vocab,
            cfg=cfg,
        )
        candidate = attach_metadata(candidate, display_path(path, root))
        if candidate is not None:
            yield candidate, stats, str(path)
        else:
            yield {}, stats, str(path)
    for path in root.rglob("store.db"):
        stats = StoreStats()
        candidate = analyze_events(
            read_store_db(path, stats, log=False),
            display_path(path, root),
            vocab=vocab,
            cfg=cfg,
        )
        candidate = attach_metadata(candidate, display_path(path, root))
        if candidate is not None:
            yield candidate, stats, str(path)
        else:
            yield {}, stats, str(path)


def _verbose_summary(records: List[Tuple[str, JsonlStats | StoreStats]]) -> str:
    out: List[str] = ["", "[scan_transcripts] IO summary:"]
    for path, stats in records:
        if isinstance(stats, JsonlStats):
            out.append(
                f"  jsonl {path}: lines={stats.lines_read} "
                f"json_errors={stats.json_decode_errors} "
                f"open_errors={stats.open_errors}"
            )
        else:
            out.append(
                f"  store {path}: blobs={stats.blobs_walked}/{stats.blobs_total} "
                f"unparseable={stats.blobs_unparseable} "
                f"json_objs={stats.json_objects_seen} "
                f"messages={stats.messages_yielded} "
                f"deduped={stats.messages_deduped} "
                f"open_errors={stats.open_errors}"
            )
    return "\n".join(out)


def _run_scan(args: argparse.Namespace) -> int:
    cfg = _config_from_args(args)
    vocab = load_vocab(args.vocab)

    roots: List[pathlib.Path] = []
    for raw in args.roots:
        path = pathlib.Path(raw).expanduser().resolve()
        if not path.exists():
            print(f"Root does not exist: {path}", file=sys.stderr)
            return 2
        roots.append(path)

    candidates: List[Dict[str, Any]] = []
    stats_log: List[Tuple[str, JsonlStats | StoreStats]] = []
    for root in roots:
        for candidate, stats, path in _scan_paths(root, cfg, vocab):
            stats_log.append((path, stats))
            if candidate:
                candidates.append(candidate)

    candidates.sort(key=lambda item: item["score"], reverse=True)
    if args.limit > 0:
        candidates = candidates[: args.limit]

    if args.json:
        output = json.dumps(
            {
                "roots": [str(root) for root in roots],
                "candidates": candidates,
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        output = render_markdown(candidates, roots, top_n=args.top_n)

    if args.output:
        pathlib.Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    if args.verbose:
        print(_verbose_summary(stats_log), file=sys.stderr)
    return 0


def _run_show(args: argparse.Namespace) -> int:
    target = pathlib.Path(args.path).expanduser().resolve()
    if not target.exists():
        print(f"File not found: {target}", file=sys.stderr)
        return 2

    if target.suffix == ".jsonl":
        events = read_jsonl(target)
    elif target.name == "store.db":
        events = read_store_db(target)
    else:
        print(
            f"Unsupported file type (need *.jsonl or store.db): {target}",
            file=sys.stderr,
        )
        return 2

    lo = args.line - args.context
    hi = args.line + args.context
    print(f"# Window @ {target}")
    print(f"# Center line {args.line}, context ±{args.context}\n")

    seen = 0
    for index, obj in events:
        if index < lo:
            continue
        if index > hi:
            break
        print(render_message(index, obj, max_field=args.max_field))
        print()
        seen += 1

    if seen == 0:
        print(
            f"(no messages found in window; transcript may have fewer than "
            f"{args.line + 1} messages)",
            file=sys.stderr,
        )
    return 0


_KNOWN_SUBCOMMANDS = {"scan", "show"}


def main(argv: List[str]) -> int:
    parser = _build_parser()
    if not argv:
        parser.print_help(sys.stderr)
        return 2
    # Default to `scan` so the historical `scan_transcripts.py <root>` form
    # keeps working. Only inject the prefix when the first arg is clearly not
    # a subcommand (avoids hiding `--help` and friends).
    if argv[0] not in _KNOWN_SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["scan", *argv]
    args = parser.parse_args(argv)
    if args.command == "show":
        return _run_show(args)
    if args.command == "scan":
        return _run_scan(args)
    parser.print_help(sys.stderr)
    return 2
