"""Uninstall / upgrade: every IrisClick process from this install is closed, nothing else."""

import sys

import pytest

from app import process_cleanup


@pytest.fixture
def install(tmp_path):
    (tmp_path / "runtime").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "runtime" / "python.exe").write_bytes(b"")
    return tmp_path


def test_an_orphaned_eye_tracking_process_is_closed(install):
    runtime = install / "runtime"
    running = [
        (10, str(runtime / "pythonw.exe")),          # orphaned eye tracking (its server crashed)
        (11, str(runtime / "python.exe")),           # the stop step itself
        (12, r"C:\Windows\explorer.exe"),            # not IrisClick
        (13, r"C:\Python312\pythonw.exe"),           # someone else's Python
    ]
    killed = []
    closed = process_cleanup.stop_leftovers(install / "server", running=lambda: running, kill=killed.append,
                                            executable=runtime / "python.exe", me=11)
    assert closed == killed == [10]


def test_case_and_slashes_do_not_matter(install):
    runtime = install / "runtime"
    upper = str(runtime / "pythonw.exe").upper()
    assert process_cleanup.leftovers(runtime, [(5, upper)], me=1) == [5]


def test_a_look_alike_folder_is_not_touched(install):
    runtime = install / "runtime"
    sibling = str(runtime) + "-old\\pythonw.exe"   # "runtime-old" is not "runtime"
    assert process_cleanup.leftovers(runtime, [(5, sibling)], me=1) == []


def test_development_python_is_never_touched(install):
    killed = []
    closed = process_cleanup.stop_leftovers(install / "server", running=lambda: [(7, sys.executable)],
                                            kill=killed.append, executable=sys.executable, me=1)
    assert closed == [] and killed == []


@pytest.mark.skipif(sys.platform != "win32", reason="lists Windows processes")
def test_this_test_process_is_listed():
    import os
    assert any(pid == os.getpid() for pid, _path in process_cleanup._running())
