"""Generate a persisted full-batch summary for Power BI to refresh."""
import argparse
import json
from .config import ROOT
from .assistant import llm_summary, rule_summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--llm', action='store_true')
    args = parser.parse_args()
    payload = json.loads((ROOT / 'artifacts/ai_input.json').read_text(encoding='utf-8'))
    answer = llm_summary(payload) if args.llm else rule_summary(payload)
    (ROOT / 'artifacts/summary.md').write_text(answer, encoding='utf-8')
    print('Saved artifacts/summary.md (' + ('LLM' if args.llm else 'rule-based') + ')')


if __name__ == '__main__':
    main()
