import pytest

from empirical_core.calls import CallLog
from empirical_core.corrections import Corrections
from empirical_core.event_ast import Occurrences, ProcessStructures
from empirical_core.experience import ExperienceLog
from empirical_core.memory import MemoryLayer
from empirical_core.registry import PackageRegistry
from empirical_core.store import Store
from empirical_core.valve import MemoryValve


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "process_integration: launches test-owned subprocesses to check crash recovery; requires experiment runners",
    )


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "kb.sqlite3"))
    yield s
    s.close()


@pytest.fixture
def experiences(store):
    return ExperienceLog(store)


@pytest.fixture
def registry(store, experiences):
    return PackageRegistry(store, experiences)


@pytest.fixture
def memory(store, experiences):
    return MemoryLayer(store, experiences)


@pytest.fixture
def valve(store, experiences):
    return MemoryValve(store, experiences)


@pytest.fixture
def calls(store, experiences, registry, valve):
    return CallLog(store, experiences, registry, valve)


@pytest.fixture
def corrections(store, experiences):
    return Corrections(store, experiences)


@pytest.fixture
def structures(store, experiences):
    return ProcessStructures(store, experiences)


@pytest.fixture
def occurrences(store, experiences, structures, valve):
    return Occurrences(store, experiences, structures, valve)
