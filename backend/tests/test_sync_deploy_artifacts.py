"""Review-only deploy artifacts; all authorization tuples are synthetic."""
import json
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / 'deploy'


def test_operator_rule_allows_exact_start_tuple_only():
    rule = DEPLOY / 'stocks-sync-operator.rules'
    assert rule.is_file()
    javascript = """
const fs = require('fs'); let rule;
global.polkit = {Result:{YES:'YES'}, addRule:r=>{rule=r;}};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const allowed=[];
for(const user of ['geoff','stocks','stocks-sync','root','other'])
for(const id of ['org.freedesktop.systemd1.manage-units','org.freedesktop.systemd1.manage-unit-files'])
for(const unit of ['stocks-sync.service','stocks.service','stocks-sync.timer','evil.service','stocks-sync.service.extra'])
for(const verb of ['start','stop','restart','reload','enable','disable','kill','set-property']) {
 if(rule({id,lookup:k=>({unit,verb})[k]}, {user})==='YES') allowed.push([user,id,unit,verb]);
}
console.log(JSON.stringify(allowed));
"""
    result = subprocess.run(['node', '-e', javascript, str(rule)], capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(result.stdout) == [['geoff', 'org.freedesktop.systemd1.manage-units', 'stocks-sync.service', 'start']]


def test_templates_match_isolated_identities_and_daily_timer():
    web = (DEPLOY / 'stocks.service').read_text()
    sync = (DEPLOY / 'stocks-sync.service').read_text()
    assert 'User=stocks\nGroup=stocks\nSupplementaryGroups=stocks-data' in web
    assert 'User=stocks-sync\nGroup=stocks-sync\nSupplementaryGroups=stocks-data' in sync
    assert 'InaccessiblePaths=-/var/lib/stocks-sync' in web
    assert 'InaccessiblePaths=-/var/lib/stocks\n' in sync
    assert 'ReadOnlyPaths=/var/lib/stocks-status' in web
    for unit in (web, sync):
        assert 'NoNewPrivileges=true' in unit
        assert 'ProtectHome=true' in unit
        assert 'ProtectSystem=strict' in unit
    timer = (DEPLOY / 'stocks-sync.timer').read_text()
    assert 'OnCalendar=*-*-* 18:30:00 Europe/London' in timer
    assert 'RandomizedDelaySec=2min' in timer
    assert 'Persistent=true' in timer
