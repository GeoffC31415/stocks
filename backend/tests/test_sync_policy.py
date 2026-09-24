"""Policy template evaluated synthetically; never authorize a real systemd action."""

import json
import subprocess
from pathlib import Path


def test_policy_allows_only_stocks_start_of_exact_sync_unit():
    policy = Path(__file__).resolve().parents[2] / "deploy" / "stocks-sync-trigger.rules"
    assert policy.is_file()
    javascript = """
const fs = require('fs');
let rule;
global.polkit = { Result: { YES: 'YES' }, addRule: r => { rule = r; } };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const results = [];
for (const user of ['stocks', 'other', 'root'])
for (const id of ['org.freedesktop.systemd1.manage-units', 'org.freedesktop.systemd1.manage-unit-files'])
for (const unit of ['stocks-sync.service', 'stocks.service', 'stocks-sync.timer', 'evil.service'])
for (const verb of ['start', 'stop', 'restart', 'reload', 'enable']) {
  const allowed = rule({ id, lookup: key => ({unit, verb})[key] }, { user });
  if (allowed === 'YES') results.push([user, id, unit, verb]);
}
console.log(JSON.stringify(results));
"""
    result = subprocess.run(
        ["node", "-e", javascript, str(policy)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert json.loads(result.stdout) == [
        ["stocks", "org.freedesktop.systemd1.manage-units", "stocks-sync.service", "start"]
    ]
    for name in ("stocks.service", "stocks-sync.service"):
        assert "NoNewPrivileges=true" in (policy.parent / name).read_text()
