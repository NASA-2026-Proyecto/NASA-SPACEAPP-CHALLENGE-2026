"""El almacén de escenas: cuándo renueva, que no renueve dos veces a la vez y qué pasa si falla."""

import threading
import time

import pytest

from app.services.aerosol_scene import AerosolSource
from app.services.scenes import SceneStore
from tests.fakes import FakeGeosFp


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Spawner:
    """En lugar de lanzar un hilo, guarda la tarea para ejecutarla cuando el test quiera."""

    def __init__(self) -> None:
        self.tasks: list = []

    def __call__(self, task) -> None:
        self.tasks.append(task)

    def run_all(self) -> None:
        while self.tasks:
            self.tasks.pop(0)()


@pytest.fixture
def nasa() -> FakeGeosFp:
    return FakeGeosFp(n_times=10)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def spawner() -> Spawner:
    return Spawner()


@pytest.fixture
def store(nasa, clock, spawner) -> SceneStore:
    source = AerosolSource(nasa.client(), steps=2)
    return SceneStore(source, check_seconds=900, retry_seconds=30, clock=clock, spawn=spawner)


def test_first_get_returns_nothing_and_starts_one_refresh(store, spawner):
    assert store.get() is None
    assert store.get() is None  # la segunda petición no lanza otra renovación
    assert len(spawner.tasks) == 1

    spawner.run_all()
    assert store.get().version == "20260228T0430Z"
    assert store.scene_id == "aerosol-latest"


def test_source_is_checked_again_only_after_the_interval(store, spawner, clock, nasa):
    store.get()
    spawner.run_all()
    nasa.requests.clear()

    clock.now += 899
    store.get()
    assert spawner.tasks == []  # aún no toca

    clock.now += 2
    store.get()
    assert len(spawner.tasks) == 1
    spawner.run_all()
    assert len(nasa.requests) == 1  # misma versión: solo la consulta barata


def test_after_a_failure_it_retries_sooner(store, spawner, clock, nasa):
    nasa.fail = True
    store.get()
    spawner.run_all()
    assert store.get() is None
    assert "NASA no responde" in store.error
    assert spawner.tasks == []  # acaba de fallar: no reintenta de inmediato

    nasa.fail = False
    clock.now += 31
    store.get()
    spawner.run_all()
    assert store.get() is not None
    assert store.error is None


def test_refresh_does_not_run_twice_at_once(store, spawner):
    store.get()  # una renovación reservada, aún sin ejecutar
    assert store.refresh() is False  # la manual no se cuela
    spawner.run_all()
    assert store.refresh() is True  # ya libre


def test_a_failure_to_start_the_background_task_does_not_block_the_store(nasa, clock):
    attempts = []

    def broken_spawn(task) -> None:
        attempts.append(task)
        raise RuntimeError("no se pueden crear más hilos")

    store = SceneStore(
        AerosolSource(nasa.client(), steps=2), retry_seconds=30, clock=clock, spawn=broken_spawn
    )
    assert store.get() is None
    clock.now += 31
    assert store.get() is None
    assert len(attempts) == 2  # tras la espera lo vuelve a intentar: no se quedó bloqueado
    assert store.refresh() is True


def test_an_error_that_is_not_an_exception_still_frees_the_store(nasa, clock, spawner):
    class Interrupted(BaseException):
        pass

    def interrupted_get(url: str) -> bytes:
        raise Interrupted

    from app.services.geosfp import GeosFpClient

    store = SceneStore(
        AerosolSource(GeosFpClient(url="https://example.test/x", get=interrupted_get), steps=2),
        clock=clock,
        spawn=spawner,
    )
    with pytest.raises(Interrupted):
        store.refresh()
    clock.now += 31
    store.get()
    assert len(spawner.tasks) == 1  # el turno quedó libre


def test_files_of_the_previous_version_stay_available(store, nasa):
    store.refresh()
    old = store.get()
    nasa.n_times = 11
    store.refresh()
    new = store.get()

    assert new.version != old.version
    assert store.file(old.version, "dust.f32") == old.files["dust.f32"]
    assert store.file(new.version, "dust.f32") == new.files["dust.f32"]
    assert store.file("20000101T0000Z", "dust.f32") is None
    assert store.file(new.version, "unknown.f32") is None


def test_real_background_thread_builds_the_scene_once(nasa):
    """Con el hilo de verdad: muchas peticiones simultáneas, una sola descarga."""
    release = threading.Event()
    original_get = nasa.get

    def slow_get(url: str) -> bytes:
        release.wait(timeout=5)
        return original_get(url)

    nasa.get = slow_get
    store = SceneStore(AerosolSource(nasa.client(), steps=2))

    results = [store.get() for _ in range(20)]  # todas mientras la primera descarga espera
    assert results == [None] * 20
    release.set()

    deadline = time.monotonic() + 5
    while store.get() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert store.get() is not None
    assert sum(url.endswith(".das") for url in nasa.requests) == 1
