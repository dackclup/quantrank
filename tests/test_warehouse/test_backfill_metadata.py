"""Offline tests for scripts.backfill_warehouse_metadata (Task 1).

Coverage matrix
---------------
BM1  _git_log_commits returns expected commit list format.
BM2  _git_show_file returns None gracefully on subprocess failure.
BM3  _derive_run_date uses last_update_utc when present and well-formed.
BM4  _derive_run_date falls back to committer_date when last_update_utc absent.
BM5  _derive_run_date falls back to committer_date when last_update_utc malformed.
BM6  _existing_run_dates returns the set of already-written run_dates.
BM7  run_backfill_metadata: normal path — writes correct columns, one row per
     unique run_date, metadata_json is verbatim JSON.
BM8  run_backfill_metadata: dedup — two commits with same derived run_date →
     only the newest (first) commit is written.
BM9  run_backfill_metadata: graceful skip on malformed JSON — no abort; other
     commits processed.
BM10 run_backfill_metadata: graceful skip when git_show returns None.
BM11 run_backfill_metadata: idempotent — re-run does not create duplicate rows.
BM12 run_backfill_metadata: --force overwrites existing partition.
BM13 derive_run_metadata_columns returns the canonical 6 columns.
BM14 warehouse_schema_check: run_metadata schema in sync after --update.
BM15 Partition column types are all large_string in the written Parquet.
"""

from __future__ import annotations

import json
from unittest.mock import (
    MagicMock,
    patch,
)

# ---------------------------------------------------------------------------
# Helpers: synthetic git history + metadata blobs
# ---------------------------------------------------------------------------

def _make_metadata_json(
    version: str = "0.10.29-phase8pilot",
    universe: str = "SP1500",
    last_update_utc: str = "2026-06-21T07:00:00Z",
) -> str:
    """Build a minimal metadata JSON blob resembling the real metadata.json."""
    return json.dumps({
        "version": version,
        "last_update_utc": last_update_utc,
        "next_update_utc": "2026-06-22T22:00:00Z",
        "universe": universe,
        "universe_size": 1504,
        "compute_run_id": "test-run-001",
        "git_commit": "abc1234",
        "tier2_enabled": True,
    })


def _fake_commits() -> list[dict[str, str]]:
    """Simulate two commits touching metadata.json on different dates."""
    return [
        {"sha": "aaa0001" * 5 + "aa", "committer_date": "2026-06-24"},
        {"sha": "bbb0002" * 5 + "bb", "committer_date": "2026-06-23"},
    ]


def _fake_commits_same_day() -> list[dict[str, str]]:
    """Two commits that both resolve to the same run_date (same-day re-run)."""
    return [
        {"sha": "ccc0003" * 5 + "cc", "committer_date": "2026-06-24"},
        {"sha": "ddd0004" * 5 + "dd", "committer_date": "2026-06-24"},
    ]


# ---------------------------------------------------------------------------
# BM1 — _git_log_commits format
# ---------------------------------------------------------------------------

class TestGitLogCommits:
    """BM1: _git_log_commits returns the expected [{sha, committer_date}] list."""

    def test_BM1_parses_valid_output(self):
        """BM1: well-formed git log output → list of dicts."""
        from scripts.backfill_warehouse_metadata import _git_log_commits

        fake_stdout = (
            "abc123def456abc123def456abc123def456abc123de 2026-06-24\n"
            "111222333444111222333444111222333444111222333 2026-06-23\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_stdout, returncode=0)
            result = _git_log_commits("frontend/public/data/metadata.json")

        assert len(result) == 2
        assert result[0]["sha"] == "abc123def456abc123def456abc123def456abc123de"
        assert result[0]["committer_date"] == "2026-06-24"
        assert result[1]["sha"] == "111222333444111222333444111222333444111222333"
        assert result[1]["committer_date"] == "2026-06-23"

    def test_BM1_empty_output_returns_empty_list(self):
        """BM1: empty git log (no commits) → empty list, no exception."""
        from scripts.backfill_warehouse_metadata import _git_log_commits

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = _git_log_commits("frontend/public/data/metadata.json")

        assert result == []


# ---------------------------------------------------------------------------
# BM2 — _git_show_file graceful failure
# ---------------------------------------------------------------------------

class TestGitShowFile:
    """BM2: _git_show_file returns None on subprocess failure."""

    def test_BM2_returns_none_on_called_process_error(self):
        """BM2: CalledProcessError → None (not raised)."""
        import subprocess

        from scripts.backfill_warehouse_metadata import _git_show_file

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")):
            result = _git_show_file("deadbeef" * 5, "some/file.json")

        assert result is None

    def test_BM2_returns_none_on_timeout(self):
        """BM2: TimeoutExpired → None (not raised)."""
        import subprocess

        from scripts.backfill_warehouse_metadata import _git_show_file

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 30),
        ):
            result = _git_show_file("deadbeef" * 5, "some/file.json")

        assert result is None


# ---------------------------------------------------------------------------
# BM3–BM5 — _derive_run_date
# ---------------------------------------------------------------------------

class TestDeriveRunDate:
    """BM3–BM5: run_date derivation from metadata dict."""

    def test_BM3_uses_last_update_utc_when_present(self):
        """BM3: well-formed last_update_utc → date part extracted."""
        from scripts.backfill_warehouse_metadata import _derive_run_date

        meta = {"last_update_utc": "2026-06-22T09:21:42Z"}
        result = _derive_run_date(meta, "2026-06-23")
        assert result == "2026-06-22"

    def test_BM4_falls_back_to_committer_date_when_absent(self):
        """BM4: no last_update_utc key → committer_date used."""
        from scripts.backfill_warehouse_metadata import _derive_run_date

        meta: dict = {}
        result = _derive_run_date(meta, "2026-06-21")
        assert result == "2026-06-21"

    def test_BM5_falls_back_on_malformed_utc(self):
        """BM5: last_update_utc present but not a valid date prefix → committer_date."""
        from scripts.backfill_warehouse_metadata import _derive_run_date

        meta = {"last_update_utc": "not-a-date-at-all"}
        result = _derive_run_date(meta, "2026-06-20")
        assert result == "2026-06-20"

    def test_BM3_handles_date_only_last_update_utc(self):
        """BM3: last_update_utc that is just a date string (no time) → used as-is."""
        from scripts.backfill_warehouse_metadata import _derive_run_date

        meta = {"last_update_utc": "2026-06-22"}
        result = _derive_run_date(meta, "2026-06-23")
        assert result == "2026-06-22"


# ---------------------------------------------------------------------------
# BM6 — _existing_run_dates
# ---------------------------------------------------------------------------

class TestExistingRunDates:
    """BM6: _existing_run_dates reads the on-disk partition set."""

    def test_BM6_empty_when_dir_absent(self, tmp_path):
        """BM6: non-existent run_metadata dir → empty set."""
        from scripts.backfill_warehouse_metadata import _existing_run_dates

        result = _existing_run_dates(tmp_path / "run_metadata_nonexistent")
        assert result == set()

    def test_BM6_finds_written_run_dates(self, tmp_path):
        """BM6: after writing a partition, its run_date appears in the set."""
        from scripts.backfill_warehouse_metadata import _existing_run_dates

        rm_dir = tmp_path / "run_metadata"
        # Create the expected Hive partition structure.
        part_dir = rm_dir / "year=2026" / "run_date=2026-06-21"
        part_dir.mkdir(parents=True)
        (part_dir / "part-0.parquet").write_bytes(b"dummy")

        result = _existing_run_dates(rm_dir)
        assert "2026-06-21" in result

    def test_BM6_ignores_non_run_date_dirs(self, tmp_path):
        """BM6: directories not named run_date=... are ignored."""
        from scripts.backfill_warehouse_metadata import _existing_run_dates

        rm_dir = tmp_path / "run_metadata"
        # A directory without the run_date= prefix should not appear.
        other_dir = rm_dir / "year=2026" / "2026-06-21"
        other_dir.mkdir(parents=True)
        (other_dir / "part-0.parquet").write_bytes(b"dummy")

        result = _existing_run_dates(rm_dir)
        assert "2026-06-21" not in result


# ---------------------------------------------------------------------------
# BM7 — Normal path: correct columns, one row per unique run_date
# ---------------------------------------------------------------------------

class TestRunBackfillMetadata:
    """BM7–BM12: core run_backfill_metadata behaviours."""

    def _setup_mocks(
        self,
        commits: list[dict[str, str]],
        metadata_jsons: dict[str, str],
    ):
        """Context manager setting up git_log_commits and git_show_file mocks."""
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            with patch(
                "scripts.backfill_warehouse_metadata._git_log_commits",
                return_value=commits,
            ), patch(
                "scripts.backfill_warehouse_metadata._git_show_file",
                side_effect=lambda sha, path: metadata_jsons.get(sha),
            ):
                yield

        return _ctx()

    def test_BM7_writes_correct_columns_one_row_per_run_date(self, tmp_path):
        """BM7: normal path — partition has all required columns, one row per date."""
        import pyarrow.parquet as pq

        from scripts.backfill_warehouse_metadata import (
            RUN_METADATA_COLUMNS,
            run_backfill_metadata,
        )

        commits = _fake_commits()
        sha_a = commits[0]["sha"]
        sha_b = commits[1]["sha"]
        json_a = _make_metadata_json(
            version="0.10.31-phase8pilot",
            universe="SP1500",
            last_update_utc="2026-06-24T09:21:42Z",
        )
        json_b = _make_metadata_json(
            version="0.10.29-phase8pilot",
            universe="SP1500",
            last_update_utc="2026-06-23T04:44:04Z",
        )

        with self._setup_mocks(commits, {sha_a: json_a, sha_b: json_b}):
            wh_dir = tmp_path / "warehouse"
            result = run_backfill_metadata(warehouse_dir=wh_dir)

        assert result["commits_found"] == 2
        assert result["written"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == 0

        # Verify partitions exist.
        part_24 = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        )
        part_23 = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-23" / "part-0.parquet"
        )
        assert part_24.exists(), "Partition for 2026-06-24 must exist"
        assert part_23.exists(), "Partition for 2026-06-23 must exist"

        # Verify columns.
        table = pq.ParquetFile(str(part_24)).read()
        for col in RUN_METADATA_COLUMNS:
            assert col in table.schema.names, f"Column {col!r} missing from partition"
        assert table.num_rows == 1

    def test_BM7_metadata_json_is_verbatim(self, tmp_path):
        """BM7: metadata_json column contains the raw JSON string."""
        import pyarrow.parquet as pq

        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = [_fake_commits()[0]]
        sha = commits[0]["sha"]
        raw_json = _make_metadata_json(last_update_utc="2026-06-24T09:21:42Z")

        with self._setup_mocks(commits, {sha: raw_json}):
            wh_dir = tmp_path / "warehouse"
            run_backfill_metadata(warehouse_dir=wh_dir)

        part = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        )
        row = pq.ParquetFile(str(part)).read().to_pydict()
        stored_json = row["metadata_json"][0]

        # The stored JSON must parse back to the original dict.
        original = json.loads(raw_json)
        stored = json.loads(stored_json)
        assert stored["version"] == original["version"]
        assert stored["universe"] == original["universe"]

    def test_BM7_row_provenance_is_metadata_backfill(self, tmp_path):
        """BM7: row_provenance is always 'metadata_backfill'."""
        import pyarrow.parquet as pq

        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = [_fake_commits()[0]]
        sha = commits[0]["sha"]

        with self._setup_mocks(commits, {sha: _make_metadata_json(last_update_utc="2026-06-24T10:00:00Z")}):
            wh_dir = tmp_path / "warehouse"
            run_backfill_metadata(warehouse_dir=wh_dir)

        part = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        )
        row = pq.ParquetFile(str(part)).read().to_pydict()
        assert row["row_provenance"][0] == "metadata_backfill"

    def test_BM7_source_commit_is_sha(self, tmp_path):
        """BM7: source_commit column contains the git SHA."""
        import pyarrow.parquet as pq

        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = [_fake_commits()[0]]
        sha = commits[0]["sha"]

        with self._setup_mocks(commits, {sha: _make_metadata_json(last_update_utc="2026-06-24T10:00:00Z")}):
            wh_dir = tmp_path / "warehouse"
            run_backfill_metadata(warehouse_dir=wh_dir)

        part = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        )
        row = pq.ParquetFile(str(part)).read().to_pydict()
        assert row["source_commit"][0] == sha


# ---------------------------------------------------------------------------
# BM8 — Dedup: two commits on the same day → only newest written
# ---------------------------------------------------------------------------

class TestDedupSameDay:
    """BM8: multiple commits for the same calendar day → only the newest is written."""

    def test_BM8_oldest_commit_skipped(self, tmp_path):
        """BM8: two commits with the same derived run_date → 1 written, 1 skipped."""
        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = _fake_commits_same_day()
        sha_new = commits[0]["sha"]  # git log: newest first
        sha_old = commits[1]["sha"]

        json_new = _make_metadata_json(last_update_utc="2026-06-24T10:00:00Z")
        json_old = _make_metadata_json(last_update_utc="2026-06-24T07:00:00Z")

        with patch(
            "scripts.backfill_warehouse_metadata._git_log_commits",
            return_value=commits,
        ), patch(
            "scripts.backfill_warehouse_metadata._git_show_file",
            side_effect=lambda sha, path: {sha_new: json_new, sha_old: json_old}.get(sha),
        ):
            wh_dir = tmp_path / "warehouse"
            result = run_backfill_metadata(warehouse_dir=wh_dir)

        assert result["written"] == 1
        assert result["skipped"] == 1
        assert result["errors"] == 0


# ---------------------------------------------------------------------------
# BM9 — Graceful skip on malformed JSON
# ---------------------------------------------------------------------------

class TestGracefulSkipMalformed:
    """BM9: malformed JSON at one commit → skip it, process the rest."""

    def test_BM9_malformed_json_skipped(self, tmp_path):
        """BM9: one commit has bad JSON → errors=1, other commits still written."""
        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = _fake_commits()
        sha_good = commits[0]["sha"]  # 2026-06-24
        sha_bad = commits[1]["sha"]   # 2026-06-23

        json_good = _make_metadata_json(last_update_utc="2026-06-24T09:00:00Z")
        bad_json = "{ this is not valid JSON !!!"

        with patch(
            "scripts.backfill_warehouse_metadata._git_log_commits",
            return_value=commits,
        ), patch(
            "scripts.backfill_warehouse_metadata._git_show_file",
            side_effect=lambda sha, path: {sha_good: json_good, sha_bad: bad_json}.get(sha),
        ):
            wh_dir = tmp_path / "warehouse"
            result = run_backfill_metadata(warehouse_dir=wh_dir)

        assert result["written"] == 1   # only the good commit
        assert result["errors"] == 1    # the bad commit
        # Good partition must still exist.
        part = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        )
        assert part.exists(), "Good partition must be written despite bad commit"


# ---------------------------------------------------------------------------
# BM10 — Graceful skip when git_show returns None
# ---------------------------------------------------------------------------

class TestGracefulSkipGitShowNone:
    """BM10: git_show returns None → skip that commit gracefully."""

    def test_BM10_git_show_none_skipped(self, tmp_path):
        """BM10: None from git_show_file → errors=1, other commits processed."""
        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = _fake_commits()
        sha_good = commits[0]["sha"]

        json_good = _make_metadata_json(last_update_utc="2026-06-24T09:00:00Z")

        def _fake_show(sha: str, path: str) -> str | None:
            if sha == sha_good:
                return json_good
            return None  # simulate git show failure for any other sha

        with patch(
            "scripts.backfill_warehouse_metadata._git_log_commits",
            return_value=commits,
        ), patch(
            "scripts.backfill_warehouse_metadata._git_show_file",
            side_effect=_fake_show,
        ):
            wh_dir = tmp_path / "warehouse"
            result = run_backfill_metadata(warehouse_dir=wh_dir)

        assert result["written"] == 1
        assert result["errors"] == 1


# ---------------------------------------------------------------------------
# BM11 — Idempotence
# ---------------------------------------------------------------------------

class TestIdempotence:
    """BM11: re-running backfill does not create duplicate partitions."""

    def test_BM11_idempotent_rerun(self, tmp_path):
        """BM11: second run for same commits → 0 written (all skipped as existing)."""
        import pyarrow.parquet as pq

        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = [_fake_commits()[0]]
        raw_json = _make_metadata_json(last_update_utc="2026-06-24T09:00:00Z")

        wh_dir = tmp_path / "warehouse"

        with patch(
            "scripts.backfill_warehouse_metadata._git_log_commits",
            return_value=commits,
        ), patch(
            "scripts.backfill_warehouse_metadata._git_show_file",
            return_value=raw_json,
        ):
            r1 = run_backfill_metadata(warehouse_dir=wh_dir)
            r2 = run_backfill_metadata(warehouse_dir=wh_dir)

        assert r1["written"] == 1
        assert r2["written"] == 0  # already exists
        assert r2["skipped"] == 1

        # Partition has exactly 1 row.
        part = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        )
        table = pq.ParquetFile(str(part)).read()
        assert table.num_rows == 1


# ---------------------------------------------------------------------------
# BM12 — --force overwrites existing partition
# ---------------------------------------------------------------------------

class TestForceOverwrite:
    """BM12: --force=True overwrites existing partitions."""

    def test_BM12_force_overwrites(self, tmp_path):
        """BM12: second run with force=True → 1 written (overwrites existing)."""
        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = [_fake_commits()[0]]
        raw_json = _make_metadata_json(last_update_utc="2026-06-24T09:00:00Z")

        wh_dir = tmp_path / "warehouse"

        with patch(
            "scripts.backfill_warehouse_metadata._git_log_commits",
            return_value=commits,
        ), patch(
            "scripts.backfill_warehouse_metadata._git_show_file",
            return_value=raw_json,
        ):
            r1 = run_backfill_metadata(warehouse_dir=wh_dir, force=False)
            r2 = run_backfill_metadata(warehouse_dir=wh_dir, force=True)

        assert r1["written"] == 1
        assert r2["written"] == 1  # force=True — re-writes
        assert r2["skipped"] == 0


# ---------------------------------------------------------------------------
# BM13 — derive_run_metadata_columns canonical column set
# ---------------------------------------------------------------------------

class TestDeriveRunMetadataColumns:
    """BM13: derive_run_metadata_columns returns the 6 canonical columns."""

    def test_BM13_returns_six_columns(self):
        """BM13: exactly 6 columns, all typed 'str | None'."""
        from compute.warehouse.warehouse_schema_check import derive_run_metadata_columns

        cols = derive_run_metadata_columns()
        assert len(cols) == 6, f"Expected 6 columns, got {len(cols)}"
        for col, dtype in cols.items():
            assert dtype == "str | None", (
                f"Column {col!r} has dtype {dtype!r} (expected 'str | None')"
            )

    def test_BM13_required_columns_present(self):
        """BM13: all required column names present."""
        from compute.warehouse.warehouse_schema_check import derive_run_metadata_columns

        cols = derive_run_metadata_columns()
        required = {
            "run_date", "schema_version", "universe",
            "source_commit", "row_provenance", "metadata_json",
        }
        assert required.issubset(set(cols.keys())), (
            f"Missing required columns: {required - set(cols.keys())}"
        )

    def test_BM13_columns_are_sorted_alphabetically(self):
        """BM13: column dict is sorted alphabetically for stable JSON output."""
        from compute.warehouse.warehouse_schema_check import derive_run_metadata_columns

        cols = derive_run_metadata_columns()
        keys = list(cols.keys())
        assert keys == sorted(keys), "derive_run_metadata_columns must return sorted keys"


# ---------------------------------------------------------------------------
# BM14 — warehouse_schema_check round-trip
# ---------------------------------------------------------------------------

class TestSchemaCheckRoundTrip:
    """BM14: --update then plain check passes for run_metadata snapshot."""

    def test_BM14_update_then_verify_passes(self, tmp_path, monkeypatch):
        """BM14: warehouse_schema_check --update writes the run_metadata snapshot;
        plain check then passes."""
        import compute.warehouse.warehouse_schema_check as wsc

        # Redirect all snapshot paths to tmp_path to avoid touching the real files.
        monkeypatch.setattr(wsc, "SNAPSHOT_PATH", tmp_path / "warehouse_schema.json")
        monkeypatch.setattr(wsc, "FILING_INDEX_SNAPSHOT_PATH", tmp_path / "filing_index_schema.json")
        monkeypatch.setattr(
            wsc, "PORTFOLIO_PARTITION_SNAPSHOT_PATH",
            tmp_path / "portfolio_partition_schema.json",
        )
        monkeypatch.setattr(
            wsc, "PORTFOLIO_MANIFEST_SNAPSHOT_PATH",
            tmp_path / "portfolio_manifest_schema.json",
        )
        monkeypatch.setattr(
            wsc, "RUN_METADATA_SNAPSHOT_PATH",
            tmp_path / "run_metadata_schema.json",
        )

        # --update must succeed.
        assert wsc.main(["--update"]) == 0
        assert (tmp_path / "run_metadata_schema.json").exists(), (
            "run_metadata_schema.json must be created on --update"
        )

        # Plain verify must pass (round-trip).
        assert wsc.main([]) == 0

    def test_BM14_drift_detected_when_snapshot_tampered(self, tmp_path, monkeypatch):
        """BM14: tampering with run_metadata_schema.json → check_run_metadata_schema exits 1."""
        import compute.warehouse.warehouse_schema_check as wsc

        monkeypatch.setattr(wsc, "SNAPSHOT_PATH", tmp_path / "warehouse_schema.json")
        monkeypatch.setattr(wsc, "FILING_INDEX_SNAPSHOT_PATH", tmp_path / "filing_index_schema.json")
        monkeypatch.setattr(
            wsc, "PORTFOLIO_PARTITION_SNAPSHOT_PATH",
            tmp_path / "portfolio_partition_schema.json",
        )
        monkeypatch.setattr(
            wsc, "PORTFOLIO_MANIFEST_SNAPSHOT_PATH",
            tmp_path / "portfolio_manifest_schema.json",
        )
        monkeypatch.setattr(
            wsc, "RUN_METADATA_SNAPSHOT_PATH",
            tmp_path / "run_metadata_schema.json",
        )

        # First --update to get a valid baseline.
        assert wsc.main(["--update"]) == 0

        # Tamper: add a phantom column.
        rm_path = tmp_path / "run_metadata_schema.json"
        data = json.loads(rm_path.read_text())
        data["columns"]["__phantom__"] = "str | None"
        rm_path.write_text(json.dumps(data))

        # Plain verify must fail.
        rc = wsc.main([])
        assert rc == 1, f"Expected exit 1 after tampering, got {rc}"


# ---------------------------------------------------------------------------
# BM15 — Parquet column types are all large_string
# ---------------------------------------------------------------------------

class TestParquetColumnTypes:
    """BM15: all columns in the written Parquet are large_string (str | None)."""

    def test_BM15_all_columns_large_string(self, tmp_path):
        """BM15: Parquet schema for the run_metadata partition uses large_string."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        from scripts.backfill_warehouse_metadata import run_backfill_metadata

        commits = [_fake_commits()[0]]
        raw_json = _make_metadata_json(last_update_utc="2026-06-24T09:00:00Z")

        with patch(
            "scripts.backfill_warehouse_metadata._git_log_commits",
            return_value=commits,
        ), patch(
            "scripts.backfill_warehouse_metadata._git_show_file",
            return_value=raw_json,
        ):
            wh_dir = tmp_path / "warehouse"
            run_backfill_metadata(warehouse_dir=wh_dir)

        part = (
            wh_dir / "run_metadata" / "year=2026" / "run_date=2026-06-24" / "part-0.parquet"
        )
        schema = pq.ParquetFile(str(part)).schema_arrow

        for field in schema:
            assert field.type == pa.large_string(), (
                f"Column {field.name!r} has type {field.type!r} "
                "(expected large_string — all run_metadata columns are textual)"
            )
