"""Phase 0 smoke test: the package imports and exposes its version."""


def test_navigator_imports():
    import navigator

    assert navigator.__version__
