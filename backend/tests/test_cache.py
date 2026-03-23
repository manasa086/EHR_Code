from services.cache_service import InMemoryCache


def make_cache():
    """Return a fresh isolated cache instance for each test."""
    return InMemoryCache()


def test_set_and_get_returns_stored_value():
    c = make_cache()
    c.set({"a": 1}, {"result": "ok"})
    assert c.get({"a": 1}) == {"result": "ok"}


def test_get_returns_none_for_missing_key():
    c = make_cache()
    assert c.get({"x": 99}) is None


def test_same_data_same_key():
    c = make_cache()
    data = {"patient": "A", "dose": 10}
    c.set(data, "result-1")
    assert c.get({"dose": 10, "patient": "A"}) == "result-1"   # different key order


def test_different_data_different_key():
    c = make_cache()
    c.set({"a": 1}, "first")
    c.set({"a": 2}, "second")
    assert c.get({"a": 1}) == "first"
    assert c.get({"a": 2}) == "second"


def test_clear_empties_all_entries():
    c = make_cache()
    c.set({"a": 1}, "x")
    c.set({"b": 2}, "y")
    c.clear()
    assert c.get({"a": 1}) is None
    assert c.get({"b": 2}) is None


def test_overwrite_existing_key():
    c = make_cache()
    c.set({"k": 1}, "old")
    c.set({"k": 1}, "new")
    assert c.get({"k": 1}) == "new"
