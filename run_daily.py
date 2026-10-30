"""Run the morning brief. GitHub Actions calls this every day, I can also run it by hand.

    python run_daily.py            live sources, sends the push
    python run_daily.py --demo     saved PubMed sample, no internet needed
    python run_daily.py --no-push  everything except the notification
"""

import argparse
import logging

from halflife.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Halflife morning brief")
    parser.add_argument("--demo", action="store_true", help="use the saved sample data")
    parser.add_argument("--no-push", action="store_true", help="skip the ntfy notification")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run(demo=args.demo, push=not args.no_push and not args.demo)

    print(f"Mode: {result['mode']}, {len(result['cards'])} cards")
    for c in result["cards"]:
        print(f"  {c['title'][:80]}  {c['drugs']}")
    if result["molecule"]:
        print(f"Molecule: {result['molecule']['name']}")
    p = result["pair"]
    print(f"Pair: {p['a']} and {p['b']}, illustrative AUC ratio {p['illustrative_auc_ratio']} ({p['category']})")
    print(f"Errors per source: {result['status']['errors'] or 'none'}")
    print(f"Output: {result['output_dir']}")


if __name__ == "__main__":
    main()
