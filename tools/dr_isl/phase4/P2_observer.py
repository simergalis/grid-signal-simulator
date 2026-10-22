"""Read-only pytest observation/port isolation for the Phase 4 GPU audit."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

TARGET = "tests/test_gpu_load_profile.py::test_gpu_load_profile"
CFG = None
ROWS = {}


def pytest_addoption(parser):
    parser.addoption("--p2-output")
    parser.addoption("--p2-port", type=int, default=22126)
    parser.addoption("--p2-prefix", action="store_true")


def pytest_configure(config):
    global CFG
    CFG = config
    # Only transport addressing differs. No assertion, clock, profile or
    # application parameter is patched. In-process TestClients are untouched.
    port = config.getoption("--p2-port")
    if port != 22126:
        import httpx
        original = httpx.Client.send
        original_async = httpx.AsyncClient.send

        def redirected(self, request, *a, **kw):
            if request.url.host in ("localhost", "127.0.0.1") and request.url.port == 22126:
                request.url = request.url.copy_with(port=port)
            return original(self, request, *a, **kw)

        async def redirected_async(self, request, *a, **kw):
            if request.url.host in ("localhost", "127.0.0.1") and request.url.port == 22126:
                request.url = request.url.copy_with(port=port)
            return await original_async(self, request, *a, **kw)

        httpx.Client.send = redirected
        httpx.AsyncClient.send = redirected_async


def pytest_collection_modifyitems(config, items):
    if config.getoption("--p2-prefix"):
        index = next(i for i, item in enumerate(items) if item.nodeid == TARGET)
        deselected = items[index + 1:]
        del items[index + 1:]
        config.hook.pytest_deselected(items=deselected)
    path = Path(config.getoption("--p2-output"))
    path.with_suffix(".order.json").write_text(json.dumps([i.nodeid for i in items], indent=2))


def _save():
    path = Path(CFG.getoption("--p2-output"))
    suite = ET.Element("testsuite", tests=str(len(ROWS)))
    for node, value in ROWS.items():
        file, _, test = node.partition("::")
        case = ET.SubElement(suite, "testcase", classname=file, name=test)
        if value["outcome"] != "passed":
            child = ET.SubElement(case, "skipped" if value["outcome"] == "skipped" else "failure")
            child.text = value.get("failure", "")
    data = ET.tostring(suite, encoding="utf-8", xml_declaration=True)
    assert len(data) < 50_000_000
    path.with_suffix(".incremental.xml").write_bytes(data)
    payload = json.dumps({"cases": ROWS}, indent=2).encode()
    assert len(payload) < 50_000_000
    path.with_suffix(".results.json").write_bytes(payload)


def pytest_runtest_logreport(report):
    if report.when == "call" or report.failed or report.skipped:
        ROWS[report.nodeid] = {
            "outcome": report.outcome,
            "stage": report.when,
            "duration": report.duration,
            "failure": str(report.longrepr) if report.failed else "",
        }
        _save()


def pytest_sessionfinish(session, exitstatus):
    _save()
