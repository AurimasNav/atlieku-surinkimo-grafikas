"""The builds of the live check on pull requests (schedule_pipeline.live_builds): every provider,
once, as the daily job builds it."""

import dataclasses
import importlib
import json
import re
from pathlib import Path
from types import ModuleType

from schedule_pipeline import build as schedule_build
from schedule_pipeline import ecoservice, live_builds, svara
from schedule_pipeline.live_builds import BUILDS
from schedule_pipeline.model import Provider

PACKAGE = Path(live_builds.__file__).parent
ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / ".github" / "workflows" / "schedule-data.yml"
EXPECTED = ROOT / "pipeline" / "expected-sources.json"
MONITORING = ROOT / "docs" / "monitoring.md"


def module_name(build):
    # The root build runs the package, whose __main__ is build.main.
    return "build" if build.module == "schedule_pipeline" else build.module.split(".")[-1]


def test_every_folder_and_job_name_is_built_once():
    for values in ([b.out for b in BUILDS], [b.name for b in BUILDS]):
        assert len(values) == len(set(values))


def test_every_provider_module_is_built():
    # The modules that write a provider's files to --out, except two tools: pratc_word
    # re-transcribes a Word document, site renders a page.
    modules = {
        path.stem
        for path in PACKAGE.glob("*.py")
        if 'add_argument("--out"' in path.read_text(encoding="utf-8")
    } - {"pratc_word", "site"}
    assert {module_name(b) for b in BUILDS} == modules


def test_every_ecoservice_region_is_built():
    regions = {b.args[b.args.index("--region") + 1] for b in BUILDS if "--region" in b.args}
    assert regions == set(ecoservice.REGIONS)


def test_the_daily_job_builds_the_same():
    # schedule-data.yml: the same modules, arguments and folders, without --strict (there, a
    # build that fails keeps the published data).
    daily = re.findall(
        r"uv run python -m (schedule_pipeline\S*) (.*?)--out \.\./site/([\w.-]+)$",
        DAILY.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    live = [(b.module, [a for a in b.args if a != live_builds.STRICT], b.out) for b in BUILDS]
    assert sorted((m, a.split(), o) for m, a, o in daily) == sorted(live)


def daily_steps():
    """The steps of the daily job, each as its text from its `- name:` line on."""
    text = DAILY.read_text(encoding="utf-8")
    return re.split(r"\n(?=      - (?:name|id|uses|run):)", text)


def test_every_build_that_may_fail_keeps_yesterdays_folder():
    # A build that fails (continue-on-error) is followed by a step that downloads the folder
    # published yesterday. Only a 404 (nothing was published) may leave the folder out: any
    # other error fails the job, so the site keeps everything it has and a part published
    # yesterday never silently vanishes.
    steps = daily_steps()
    builds = [
        (re.search(r"id: (\w+)", s)[1], re.search(r"--out \.\./site/([\w.-]+)", s)[1])
        for s in steps
        if "continue-on-error: true" in s and "--out ../site/" in s
    ]
    assert len(builds) == len(BUILDS) - 1  # all but the root build, which keeps parts itself
    for step_id, folder in builds:
        (keep,) = [s for s in steps if f"if: steps.{step_id}.outcome == 'failure'" in s]
        assert f"out=../site/{folder}\n" in keep
        assert f"/atlieku-surinkimo-grafikas/{folder}\n" in keep
        assert "|| true" not in keep.replace("-w '%{http_code}' \"$base/$1\" || true;", "")
        dropped, failed = keep.split('elif [ "$code" = 404 ]; then')
        assert 'rm -rf "$out"\n' in failed.split("else")[0]
        assert "exit 1" in failed.split("else", 1)[1]
        assert "exit 1" not in dropped or "couldn't be downloaded" in dropped


def test_prints_the_matrix_on_one_line(capsys):
    assert live_builds.main(["--matrix"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and out.isascii()
    jobs = json.loads(out)["include"]
    assert len(jobs) == len(BUILDS)
    assert len({job["artifact"] for job in jobs}) == len(BUILDS)
    assert jobs[0] == {
        "name": "Vilniaus r.",
        "title": "Build schedule.json from the live websites",
        "module": "schedule_pipeline",
        "args": "--strict",
        "out": "schedule.json",
        "artifact": "live-root",
    }
    assert {
        "name": "Šilutės r.",
        "title": "Build the Šilutės r. schedule from the PDF on silute.lt (or its copy)",
        "module": "schedule_pipeline.ecoservice",
        "args": "--region silutes-r --strict",
        "out": "silutes-r",
        "artifact": "live-silutes-r",
    } in jobs


def module_sources(build):
    """The sources a build's module defines: its providers' ids (status.py names a source by its
    provider), Kauno švara's municipalities, each Ecoservice folder's municipalities."""
    module = importlib.import_module(build.module)
    if build.module == "schedule_pipeline":
        return {source.provider.id for source in schedule_build.SOURCES}
    if module is svara:
        return {municipality.id for municipality in svara.MUNICIPALITIES}
    if module is ecoservice:
        region = ecoservice.REGIONS[build.args[build.args.index("--region") + 1]]
        return {municipality.provider.id for municipality in region.municipalities}
    found: set[str] = set()
    seen: set[int] = set()

    def walk(value, depth=0):
        if id(value) in seen or depth > 4:
            return
        seen.add(id(value))
        if isinstance(value, Provider):
            found.add(value.id)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                walk(item, depth + 1)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item, depth + 1)
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            for f in dataclasses.fields(value):
                walk(getattr(value, f.name), depth + 1)

    for name, value in vars(module).items():
        if not name.startswith("_") and not isinstance(value, ModuleType):
            walk(value)
    return found


def test_every_build_names_the_sources_its_module_defines():
    for build in BUILDS:
        assert set(build.sources) == module_sources(build), build.name
        assert len(build.sources) == len(set(build.sources)), build.name


def test_the_expected_sources_are_those_the_builds_publish():
    # pipeline/expected-sources.json: a PR that adds or removes a provider changes both.
    built = [source for build in BUILDS for source in build.sources]
    assert len(built) == len(set(built))
    assert json.loads(EXPECTED.read_text(encoding="utf-8")) == sorted(built)


def test_the_monitoring_doc_lists_the_expected_sources():
    # The table of sources in docs/monitoring.md, one row a source.
    doc = MONITORING.read_text(encoding="utf-8")
    table = doc[doc.index("| `source` | Company | Published in |") :].split("\n\n")[0]
    rows = re.findall(r"^\| `([\w-]+)` \| ", table, flags=re.M)[1:]
    assert sorted(rows) == json.loads(EXPECTED.read_text(encoding="utf-8"))
