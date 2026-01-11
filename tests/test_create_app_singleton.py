import threading

import pytest

import backend as backend_mod


@pytest.fixture(autouse=True)
def reset_app():
    # Ensure a clean state for each test
    backend_mod._app = None
    yield
    backend_mod._app = None


def test_singleton_returns_same_instance():
    a1 = backend_mod.create_app()
    a2 = backend_mod.create_app()
    assert a1 is a2


def test_test_config_creates_fresh_instance():
    a1 = backend_mod.create_app()
    a_test = backend_mod.create_app(test_config={"TESTING": True})
    assert a_test is not a1


def test_module_app_points_to_singleton():
    a = backend_mod.create_app()
    assert backend_mod._app is a


def test_concurrent_creation_is_thread_safe():
    # Attempt concurrent calls to create_app and ensure all callers get the same instance
    n = 12
    results: list = [None] * n

    def worker(idx):
        results[idx] = backend_mod.create_app()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    first = results[0]
    assert all(r is first for r in results)
