"""Complete effective evidence: synthetic adapters only."""
import json

import pytest
from test_isolation_host import EFFECTIVE, helper
from test_isolation_migration import FakeSystem, deployment_fixture


@pytest.mark.parametrize("missing", list(EFFECTIVE))
@pytest.mark.parametrize("consumer", ["publication", "resume"])
def test_missing_property(tmp_path, monkeypatch, missing, consumer):
    m = helper()
    root, bundle, release, previous = deployment_fixture(tmp_path)
    fake, probe = FakeSystem(), m.System()
    probe.health = lambda: None
    probe.boot_identity = lambda: "00000000-0000-0000-0000-000000000001"
    monkeypatch.setattr(m.time, "sleep", lambda _: None)
    actions = []
    def command(*args, **kwargs):
        action = args[1]
        actions.append(action)
        assert action in {"show", "cat", "is-active", "is-enabled"}, "consumer mutation forbidden"
        if action == "show":
            return "\n".join(k + "=" + v for k, v in EFFECTIVE.items() if k != missing)
        return {"cat": "[Service]\nExecStart=/synthetic/web", "is-active": "inactive", "is-enabled": "disabled"}[action]
    probe.command = command
    if consumer == "publication":
        fake.readiness = probe.readiness
        with pytest.raises(m.MigrationError):
            m.activate_layout(root, bundle, release, previous, fake)
        assert json.loads((bundle / "transition.json").read_text())["state"] == "preparing"
    else:
        m.activate_layout(root, bundle, release, previous, fake)
        values = {k: v for k, v in EFFECTIVE.items() if k not in (missing, "InvocationID")}
        path = bundle / "transition.json"
        candidate = json.loads(path.read_text())
        candidate["identity"] = {"boot_id": probe.boot_identity(), "invocation_id": "1" * 32,
            "effective_sha256": m.digest((json.dumps(values, sort_keys=True) + "\n[Service]\nExecStart=/synthetic/web").encode())}
        path.write_text(json.dumps(candidate))
        before = path.read_bytes()
        with pytest.raises(m.MigrationError):
            probe.resume_timer(bundle, root=root)
        assert path.read_bytes() == before
        assert set(actions) <= {"show", "cat", "is-active", "is-enabled"}


@pytest.mark.parametrize("key,value", [("ProtectSystem", "mystery"), ("ProtectHome", "mystery"),
    ("PrivateTmp", "mystery"), ("NoNewPrivileges", "mystery"), ("FragmentPath", ""),
    ("FragmentPath", "relative"), ("WorkingDirectory", "relative"), ("User", "bad user")])
def test_invalid_required_value(monkeypatch, key, value):
    m = helper()
    probe = m.System()
    values = dict(EFFECTIVE, **{key: value})
    probe.health = lambda: None
    probe.boot_identity = lambda: "00000000-0000-0000-0000-000000000001"
    monkeypatch.setattr(m.time, "sleep", lambda _: None)
    probe.command = lambda *a, **kw: "\n".join(k + "=" + v for k, v in values.items()) if a[1] == "show" else {"cat": "unit", "is-active": "inactive", "is-enabled": "disabled"}[a[1]]
    with pytest.raises(m.MigrationError):
        probe.readiness({"timer_enabled": "disabled", "timer_active": False})
