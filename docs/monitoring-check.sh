#!/bin/sh
# Checks the Prometheus examples in docs/monitoring.md with promtool, as CI does
# (.github/workflows/monitoring.yml):
#   - the scrape job and the alert rules parse (promtool check config);
#   - metrics.txt as the data job writes it passes promtool's linter (promtool check metrics);
#   - every metric the rules use is one the data job writes;
#   - the rules fire, and stay quiet, as docs/monitoring.test.yml expects (promtool test rules).
#
# Usage, from anywhere in the repository: sh docs/monitoring-check.sh
# Needs promtool (it comes with Prometheus) and python3 on PATH.
set -eu
cd "$(dirname "$0")/.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

python3 - "$out" <<'EOF'
import re
import sys
from pathlib import Path

out = Path(sys.argv[1])

# The doc's fenced yaml blocks: the scrape job starts with `scrape_configs:`, the rule file
# with `groups:`.
doc = Path("docs/monitoring.md").read_text(encoding="utf-8")
blocks = re.findall(r"^```yaml\n(.*?)^```$", doc, flags=re.M | re.S)
scrape = [b for b in blocks if b.startswith("scrape_configs:")]
rules = [b for b in blocks if b.startswith("groups:")]
if len(scrape) != 1 or len(rules) != 1:
    sys.exit("docs/monitoring.md should have one yaml block starting with scrape_configs: and one with groups:")
(out / "rules.yml").write_text(rules[0], encoding="utf-8")
(out / "prometheus.yml").write_text("rule_files: [rules.yml]\n" + scrape[0], encoding="utf-8")

# metrics.txt as the data job writes it, from one source that has every metric.
sys.path.insert(0, "pipeline/src")
from schedule_pipeline import status  # noqa: E402

text = status.metrics(
    {
        "checkedAt": "2026-11-21T04:20:00+00:00",
        "sources": {
            "mazeikiai": {
                "generatedAt": "2026-11-21T04:19:00+00:00",
                "areas": {"household": 12},
                "places": 340,
                "warnings": 0,
                "newWarnings": 0,
                "lastDate": {"household": "2026-12-31"},
            }
        },
    }
)
(out / "metrics.txt").write_text(text, encoding="utf-8")

written = set(re.findall(r"^# TYPE (\S+) ", text, flags=re.M))
used = set(re.findall(r"\bsiuksliaveze_\w+", rules[0]))
if missing := sorted(used - written):
    sys.exit(f"The alert rules use metrics the data job doesn't write: {', '.join(missing)}")
print(f"The alert rules use {len(used)} metrics, all written by the data job")
EOF

promtool check config "$out/prometheus.yml"
promtool check metrics < "$out/metrics.txt"
cp docs/monitoring.test.yml "$out/"
promtool test rules "$out/monitoring.test.yml"
