"""Command line: python -m app.cli passwd|hash|demo|simulate|backup"""
from __future__ import annotations

import argparse
import getpass
import os
import random
import sys
import tempfile
from typing import List, Optional

from .auth import hash_password
from .config import Config, config_path, load_config, write_env_value


def _ask_password(prompt: str = "New password") -> str:
    while True:
        a = getpass.getpass(f"{prompt}: ")
        if len(a) < 6:
            print("Please use at least 6 characters.")
            continue
        b = getpass.getpass("Repeat: ")
        if a != b:
            print("The entries do not match.")
            continue
        return a


def cmd_passwd(args: argparse.Namespace) -> int:
    path = args.config or config_path()
    if args.which == "user":
        args.which = "dashboard"
    if args.stdin:
        pw = sys.stdin.readline().rstrip("\n")
        if len(pw) < 6:
            print("Password too short (minimum 6 characters).", file=sys.stderr)
            return 1
    else:
        pw = _ask_password(f"New password for '{args.which}'")
    key = "SCHNAPSEN_ADMIN_HASH" if args.which == "admin" else "SCHNAPSEN_DASHBOARD_HASH"
    write_env_value(path, key, hash_password(pw))
    if args.user:
        write_env_value(path, "SCHNAPSEN_ADMIN_USER" if args.which == "admin" else "SCHNAPSEN_DASHBOARD_USER", args.user)
    print(f"Password for {args.which} set ({path}). Restart the service: systemctl restart schnapsen")
    return 0


def cmd_hash(args: argparse.Namespace) -> int:
    pw = sys.stdin.readline().rstrip("\n") if args.stdin else _ask_password()
    print(hash_password(pw))
    return 0


def _service(args: argparse.Namespace):
    from .service import Service
    cfg = load_config(args.config)
    if getattr(args, "db", None):
        cfg = Config(**{**cfg.__dict__, "db": args.db, "backup_dir": ""})
    return Service(cfg), cfg


def cmd_demo(args: argparse.Namespace) -> int:
    from .simtools import make_demo
    svc, cfg = _service(args)
    make_demo(svc, args.seed)
    if args.finish:
        import random
        from .simtools import play_round
        rng = random.Random(args.seed)
        d = svc.derive(svc.require_tid())
        while not d["finished"]:
            if d["phase"] == "running":
                for pr in [x for x in d["rounds"][-1]["pairings"] if not x["bye"] and x["winner"] is None]:
                    svc.set_result(pr["id"], rng.choice([pr["a"], pr["b"]]))
                svc.close_round(d["current_round"])
                from .simtools import decide_nk
                decide_nk(svc, rng)
            else:
                play_round(svc, rng)
            d = svc.derive(svc.require_tid())
        for g in d["ranking"]["groups"]:
            if g["needs_playoff"]:
                svc.set_placement(g["key"], g["players"][::-1] if rng.random() < 0.5 else g["players"])
    print(f"Demo tournament created and activated in {cfg.db}")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    svc, cfg = _service(args)
    path = svc.backup("manuell")
    if not path:
        print("Backup failed.", file=sys.stderr)
        return 1
    print(path)
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    from .service import Service
    from .simtools import check_invariants, fill_players, play_tournament
    sizes = [int(x) for x in args.players.split(",")]
    failures = runs = 0
    for n in sizes:
        for seed in range(args.seeds):
            with tempfile.TemporaryDirectory() as tmp:
                svc = Service(Config(db=os.path.join(tmp, "sim.db"), backup_dir=os.path.join(tmp, "b")))
                rng = random.Random(seed * 1000 + n)
                fill_players(svc, n)
                svc.start_tournament()
                d = play_tournament(svc, rng, p_yes=rng.choice([0.0, 0.5, 0.8, 1.0]))
                errs = check_invariants(svc)
                runs += 1
                if errs:
                    failures += 1
                    print(f"FAILED n={n} seed={seed}: " + " | ".join(errs))
                elif args.verbose:
                    wn = next(p["number"] for p in d["players"] if p["id"] == d["winner"])
                    print(f"ok n={n} seed={seed}: {d['current_round']} rounds, winner no. {wn}")
    print(f"{runs} simulations, {failures} failures.")
    return 1 if failures else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="schnapsen", description="Preisschnapsen tournament manager")
    ap.add_argument("--config", help="path to the env file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("passwd", help="set a password")
    p.add_argument("which", choices=["admin", "user", "dashboard"])
    p.add_argument("--stdin", action="store_true", help="read the password from stdin")
    p.add_argument("--user", help="also set the user name")
    p.set_defaults(fn=cmd_passwd)
    p = sub.add_parser("hash", help="print a password hash")
    p.add_argument("--stdin", action="store_true")
    p.set_defaults(fn=cmd_hash)
    p = sub.add_parser("demo", help="create a demo tournament")
    p.add_argument("--db"); p.add_argument("--seed", type=int, default=7)
    p.add_argument("--finish", action="store_true", help="play the demo tournament to the end")
    p.set_defaults(fn=cmd_demo)
    p = sub.add_parser("backup", help="create a database backup")
    p.add_argument("--db")
    p.set_defaults(fn=cmd_backup)
    p = sub.add_parser("simulate", help="simulate tournaments and check invariants")
    p.add_argument("--players", default="2,3,19,24,40")
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_simulate)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
