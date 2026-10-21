"""python -m seo_agent_team run|write|track|refresh|publish|check|index"""
import argparse
import logging
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="seo_agent_team", description="Six agents that grow a WordPress site.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="the daily routine: track, plus write/refresh on their days")
    w = sub.add_parser("write", help="write one article now (the Strategist picks, unless you give a topic)")
    w.add_argument("topic", nargs="*", help='optional, e.g. "how much does a website cost for a cafe"')
    sub.add_parser("track", help="pull Google and Bing numbers for every article")
    sub.add_parser("refresh", help="rewrite the article with the best chance of moving up")
    pub = sub.add_parser("publish", help="publish a draft the Editor held back")
    pub.add_argument("slug")
    sub.add_parser("check", help="test the WordPress and Search Console connections")
    sub.add_parser("index", help="which sitemap pages Google has indexed")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    try:
        return _run(args)
    except Exception as e:  # noqa: BLE001  # a clear one-line error, not a traceback
        print(f"Error: {str(e).splitlines()[0] if str(e) else type(e).__name__}", file=sys.stderr)
        return 1


def _run(args) -> int:
    from . import gsc, pipeline, team, wp
    if args.cmd == "run":
        print("\n".join(team.run()))
    elif args.cmd == "write":
        topic = pipeline.topic_from_text(" ".join(args.topic)) if args.topic else None
        print(team.write_next(topic))
    elif args.cmd == "track":
        print(team.summary(team.track()))
    elif args.cmd == "refresh":
        print(team.refresh_one())
    elif args.cmd == "publish":
        print(pipeline.publish_draft(args.slug))
    elif args.cmd == "check":
        print(wp.check())
        print("Search Console: " + ("connected" if gsc.ready() else "not set up (optional)"))
    elif args.cmd == "index":
        print(gsc.index_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
