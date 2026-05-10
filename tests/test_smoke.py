"""Phase 0 smoke test — proves CI pipeline runs pytest successfully."""

from compute import config


def test_phase0_scaffold_imports() -> None:
    assert config.UNIVERSE == "SP500"
    assert config.SCHEMA_VERSION.startswith("0.5.0")


def test_phase0_paths_resolve() -> None:
    assert config.PROJECT_ROOT.exists()
    assert config.FRONTEND_DIR.name == "frontend"
    assert config.DATA_DIR.parts[-2:] == ("public", "data")
