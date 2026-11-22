"""The builds of the live check on pull requests, a job each (schedule-data-live.yml).

Pull requests that change the pipeline build the data from today's files on the providers' sites,
the way the daily job does (.github/workflows/schedule-data-live.yml). The builds run in parallel,
a job per entry of BUILDS that uploads its folder of the site; then one job puts the folders
together, compares schedule.json with the published data and indexes the regions. A new provider
is an entry here, next to its steps in schedule-data.yml (tests/test_live_builds.py checks that
the two build the same).

    python -m schedule_pipeline.live_builds --matrix

prints the jobs as the matrix of the workflow, JSON on one line:

    {"include": [{"name": "Vilniaus r.", "title": "Build schedule.json from the live websites",
      "module": "schedule_pipeline", "args": "--strict", "out": "schedule.json",
      "artifact": "live-root"}, ...]}

- `name`: the job in the checks of a pull request, "live (Vilniaus r.)".
- `title`: its build step.
- `module`, `args`: the build, python -m <module> <args> --out <site>/<out>.
- `out`: the build's folder in the site; for the site root (Vilniaus r.) schedule.json, which
  the build writes addresses.json next to.
- `artifact`: the name of the folder uploaded for the last job.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

# --strict: a build that fails (or, as the comments say, a part of it) fails the check, instead
# of keeping its part of the published data as the daily job does.
STRICT = "--strict"


@dataclass(frozen=True)
class Build:
    name: str
    title: str
    module: str
    folder: str  # "" for the site root
    args: tuple[str, ...] = ()

    @property
    def out(self) -> str:
        return self.folder or "schedule.json"

    def entry(self) -> dict[str, str]:
        return {
            "name": self.name,
            "title": self.title,
            "module": self.module,
            "args": " ".join(self.args),
            "out": self.out,
            "artifact": f"live-{self.folder or 'root'}",
        }


BUILDS: tuple[Build, ...] = (
    Build(
        name="Vilniaus r.",
        title="Build schedule.json from the live websites",
        module="schedule_pipeline",
        folder="",
        args=(STRICT,),  # a company whose build fails fails the check
    ),
    Build(
        name="Kauno r., Kaišiadorių r.",
        title="Build the Kauno r. and Kaišiadorių r. schedules from Kauno švara's open-data file",
        module="schedule_pipeline.svara",
        folder="kauno-r",
    ),
    Build(
        name="Mažeikių r., Telšių r., Plungės r., Rietavo sav.",
        title=(
            "Build the Mažeikių r., Telšių r., Plungės r. and Rietavo sav. schedules from the files"
            " on tratc.lt"
        ),
        module="schedule_pipeline.tratc",
        folder="mazeikiu-r",
        args=(STRICT,),  # a municipality whose build fails fails the check
    ),
    Build(
        name="Klaipėdos r.",
        title="Build the Klaipėdos r. schedule from the spreadsheet on gargzdusvara.eu",
        module="schedule_pipeline.gargzdu",
        folder="klaipedos-r",
    ),
    Build(
        name="Jurbarko r., Tauragės r., Šilalės r., Pagėgių sav.",
        title=(
            "Build the Jurbarko r., Tauragės r., Šilalės r. and Pagėgių sav. schedules from the"
            " PDFs on uabtratc.lt"
        ),
        module="schedule_pipeline.taurage",
        folder="jurbarko-r",
        args=(STRICT,),  # a municipality whose build fails fails the check
    ),
    Build(
        name="Šiaulių RATC",
        title="Build the Šiaulių RATC schedules (six municipalities) from the PDFs on sratc.lt",
        module="schedule_pipeline.sratc",
        folder="sratc",
        args=(STRICT,),  # a part (the five, or Radviliškio r.) whose build fails fails the check
    ),
    Build(
        name="Alytaus RATC",
        title="Build the Alytaus RATC schedule from the PDFs on aratc.lt",
        module="schedule_pipeline.aratc",
        folder="alytaus-ratc",
    ),
    Build(
        name="Pasvalio r., Rokiškio r., Biržų r., Panevėžio r.",
        title=(
            "Build the Pasvalio r., Rokiškio r., Biržų r. and Panevėžio r. schedules from the"
            " spreadsheets and the Word document on pratc.lt"
        ),
        module="schedule_pipeline.pratc",
        folder="panevezio-ratc",
        # A municipality whose build fails fails the check, and so does Panevėžio r.'s mixed
        # waste document if it can't be read (a route with notes that
        # pipeline/data/schedule-panevezio-r-mixed.json doesn't have: re-transcribe it).
        args=(STRICT,),
    ),
    Build(
        name="Marijampolės AATC",
        title=(
            "Build the Marijampolės AATC schedules (five municipalities) from the PDFs on maatc.lt"
        ),
        module="schedule_pipeline.maatc",
        folder="maatc",
        args=(STRICT,),  # a municipality whose build fails fails the check
    ),
    Build(
        name="Raseinių r.",
        title="Build the Raseinių r. schedule from the PDFs on rkp.lt",
        module="schedule_pipeline.raseiniai",
        folder="raseiniu-r",
        args=(STRICT,),  # a file that can't be read fails the check
    ),
    Build(
        name="Jonavos r.",
        title="Build the Jonavos r. schedule from the PDFs on jonavospaslaugos.lt",
        module="schedule_pipeline.jonava",
        folder="jonavos-r",
        args=(STRICT,),  # a file that can't be read fails the check
    ),
    Build(
        name="Kretingos r.",
        title="Build the Kretingos r. schedule from the PDFs on kretkom.lt",
        module="schedule_pipeline.kretinga",
        folder="kretingos-r",
    ),
    # silute.lt refuses the runners: the copy in pipeline/data is read instead, with a warning.
    Build(
        name="Šilutės r.",
        title="Build the Šilutės r. schedule from the PDF on silute.lt (or its copy)",
        module="schedule_pipeline.ecoservice",
        folder="silutes-r",
        args=("--region", "silutes-r", STRICT),  # a build that fails fails the check
    ),
    Build(
        name="Trakų r., Šalčininkų r.",
        title="Build the Trakų r. and Šalčininkų r. schedules from the PDFs on ecoservice.lt",
        module="schedule_pipeline.ecoservice",
        folder="ecoservice",
        args=("--region", "ecoservice", STRICT),  # a municipality whose build fails fails it
    ),
    # kedainiai.lt refuses the runners: the copy in pipeline/data is read instead, with a warning.
    Build(
        name="Kėdainių r.",
        title=(
            "Build the Kėdainių r. schedule from the elderships' files on kedainiai.lt (or their"
            " copy)"
        ),
        module="schedule_pipeline.kedainiai",
        folder="kedainiu-r",
        args=(STRICT,),  # a file that can't be read fails the check
    ),
    Build(
        name="Molėtų r.",
        title="Build the Molėtų r. schedule from the PDFs on moletusvara.lt",
        module="schedule_pipeline.moletai",
        folder="moletu-r",
        args=(STRICT,),  # a file that can't be read fails the check
    ),
    Build(
        name="Skuodo r.",
        title="Build the Skuodo r. schedule from the spreadsheets on skuodas.lt",
        module="schedule_pipeline.skuodas",
        folder="skuodo-r",
    ),
    # ukmerge.lt refuses the runners: the copy in pipeline/data is read instead, with a warning.
    Build(
        name="Ukmergės r.",
        title="Build the Ukmergės r. schedule from the PDFs on ukmerge.lt (or their copy)",
        module="schedule_pipeline.ukmerge",
        folder="ukmerges-r",
    ),
    Build(
        name="Anykščių r.",
        title="Build the Anykščių r. schedule from the PDFs on anykom.lt",
        module="schedule_pipeline.anyksciai",
        folder="anyksciu-r",
        args=(STRICT,),  # a file that can't be read fails the check
    ),
    Build(
        name="Utenos r.",
        title="Build the Utenos r. schedule from the PDFs on utenoskom.lt",
        module="schedule_pipeline.utena",
        folder="utenos-r",
        args=(STRICT,),  # a file that can't be read fails the check
    ),
    Build(
        name="Ignalinos r.",
        title="Build the Ignalinos r. schedule from the PDFs on kompata.lt",
        module="schedule_pipeline.ignalina",
        folder="ignalinos-r",
    ),
    Build(
        name="Elektrėnų sav.",
        title="Build the Elektrėnų sav. schedule from the schedule pages on eku.lt",
        module="schedule_pipeline.elektrenai",
        folder="elektrenu-sav",
    ),
    # sirvintos.lt refuses the runners: the copy in pipeline/data is read instead, with a warning.
    Build(
        name="Širvintų r.",
        title="Build the Širvintų r. schedule from the PDFs on sirvintos.lt (or their copy)",
        module="schedule_pipeline.sirvintos",
        folder="sirvintu-r",
    ),
    Build(
        name="Kupiškio r.",
        title="Build the Kupiškio r. schedule from the page and PDFs on kupkom.lt",
        module="schedule_pipeline.kupiskis",
        folder="kupiskio-r",
    ),
    # svencionys.lt refuses the runners: the copy in pipeline/data is read instead, with a
    # warning.
    Build(
        name="Švenčionių r.",
        title="Build the Švenčionių r. schedule from the PDFs on svencionys.lt (or their copy)",
        module="schedule_pipeline.svencionys",
        folder="svencioniu-r",
        args=(STRICT,),  # a file that can't be read fails the check
    ),
    # zarasai.lt refuses the runners: the copy in pipeline/data is read instead, with a warning.
    # Fails if the scan's hash isn't the transcription's.
    Build(
        name="Zarasų r.",
        title=(
            "Build the Zarasų r. schedule from zarasai.lt or its copy (mixed waste from the scan's"
            " transcription)"
        ),
        module="schedule_pipeline.zarasai",
        folder="zarasu-r",
    ),
)


def matrix() -> dict:
    """The matrix of the workflow's build job: an entry per build."""
    return {"include": [build.entry() for build in BUILDS]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--matrix", action="store_true", required=True, help="print the matrix as JSON"
    )
    parser.parse_args(argv)
    # One line, ASCII: written to $GITHUB_OUTPUT as matrix=<json>.
    print(json.dumps(matrix()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
