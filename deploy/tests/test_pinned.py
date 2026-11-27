"""Every image and action that is not ours is pinned by its digest or its commit. The update timer
pulls the images again on each deploy and CI runs the actions with the right to publish: a tag that
is published again must not change what runs."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def lines_with(pattern: str, files) -> list[str]:
    found = []
    for path in files:
        found += [line.strip() for line in path.read_text().splitlines() if re.match(pattern, line)]
    return found


@pytest.mark.parametrize("compose", ["docker-compose.prod.yml", "docker-compose.yml"])
def test_the_images_of_others_in_the_composes_are_pinned_by_digest(compose):
    images = lines_with(r"\s+image:", [ROOT / compose])
    # Ours (ghcr.io/${GHCR_OWNER...}:pro) are published by deploy-pro.yml from a reviewed commit.
    theirs = [line for line in images if "ghcr.io/${GHCR_OWNER" not in line]

    assert theirs
    assert [line for line in theirs if not re.search(r"@sha256:[0-9a-f]{64}$", line)] == []


def test_the_images_that_the_dockerfiles_build_on_or_copy_from_are_pinned_by_digest():
    dockerfiles = [*ROOT.glob("services/*/*.Dockerfile"), ROOT / "database/Dockerfile"]
    # FROM an image, and COPY --from= an image of a registry (uv): not --from=<a stage of the file>.
    lines = lines_with(r"FROM |COPY --from=\S+[/:]", dockerfiles)

    assert any(line.startswith("COPY") for line in lines)
    assert [line for line in lines if not re.search(r"@sha256:[0-9a-f]{64}\b", line)] == []


def test_the_actions_of_the_workflows_are_pinned_by_commit():
    uses = lines_with(r"\s+(- )?uses: ", list(ROOT.glob(".github/workflows/*.yml")))
    # A workflow of this repository is code that was reviewed here.
    theirs = [line for line in uses if "uses: ./" not in line]

    assert theirs
    assert [line for line in theirs if not re.search(r"@[0-9a-f]{40}\b", line)] == []
