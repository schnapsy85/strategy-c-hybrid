import json
from pathlib import Path

import pytest

from scripts.stamp_scan_outputs import stamp_scan_outputs


REQUEST_SHA = "a" * 40


def test_stamp_scan_outputs_stamps_every_supplied_file(tmp_path):
    paths = []
    for index in range(6):
        path = tmp_path / f"result-{index}.json"
        path.write_text(json.dumps({"strategy": index}), encoding="utf-8")
        paths.append(path)

    stamp_scan_outputs(REQUEST_SHA, paths)

    for index, path in enumerate(paths):
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "strategy": index,
            "request_commit_sha": REQUEST_SHA,
        }


@pytest.mark.parametrize(
    "request_sha",
    ["", "a" * 39, "a" * 41, "A" * 40, "g" * 40],
)
def test_stamp_scan_outputs_rejects_invalid_request_sha(tmp_path, request_sha):
    path = tmp_path / "result.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="request SHA"):
        stamp_scan_outputs(request_sha, [path])

    assert json.loads(path.read_text(encoding="utf-8")) == {}


@pytest.mark.parametrize("contents", ["[]", "not json"])
def test_stamp_scan_outputs_rejects_invalid_input(tmp_path, contents):
    path = tmp_path / "result.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        stamp_scan_outputs(REQUEST_SHA, [path])
