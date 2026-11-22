"""The builds of the live check on pull requests (schedule_pipeline.live_builds): every provider,
once, as the daily job builds it."""

import json
import re
from pathlib import Path

from schedule_pipeline import ecoservice, live_builds
from schedule_pipeline.live_builds import BUILDS

PACKAGE = Path(live_builds.__file__).parent
DAILY = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "schedule-data.yml"


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
