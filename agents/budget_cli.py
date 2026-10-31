"""LLM budget status / correction.

python -m agents.budget_cli                          # status per key (env names only)
python -m agents.budget_cli --set GEMINI_API_KEY=230 # correct to the dashboard reading (MANAGER/human only)
"""
import argparse

from agents import budget


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", default=[], metavar="ENV_NAME=N")
    args = ap.parse_args(argv)
    for item in args.set:
        name, _, n = item.partition("=")
        if not name.startswith("GEMINI_API_KEY") or not n.isdigit():
            raise SystemExit(f"bad --set {item!r}; expected GEMINI_API_KEY[_2|_3]=<int>")
        budget.set_used(name, int(n))
        print(f"set {name} used={n}")
    st = budget.budget_status()
    print(f"enforce={st.enforce} resets_at={st.resets_at}")
    for name, k in st.keys.items():
        print(f"{name} used {k['used_today']}/{k['cap']} remaining {k['remaining']} rpm_cap {k['rpm_cap']}")


if __name__ == "__main__":
    main()
