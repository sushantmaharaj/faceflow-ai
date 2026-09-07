"""
Tests for fingerprint determinism and tamper detection.
"""

import pytest
from app.utils.canonical_json import canonicalize, sha256_fingerprint, fingerprint_record


class TestCanonicalization:
    def test_compact_output(self):
        out = canonicalize({"a": 1, "b": 2})
        assert " " not in out, "canonical JSON must have no extra spaces"

    def test_keys_sorted(self):
        out = canonicalize({"z": 3, "a": 1, "m": 2})
        assert out == '{"a":1,"m":2,"z":3}'

    def test_field_order_independence(self):
        r1 = {"url": "https://example.com", "title": "Hello"}
        r2 = {"title": "Hello", "url": "https://example.com"}
        assert canonicalize(r1) == canonicalize(r2)

    def test_utf8_preserved(self):
        r = {"name": "Ångström"}
        out = canonicalize(r)
        assert "Ångström" in out

    def test_nested_sorted(self):
        r = {"outer": {"z": 1, "a": 2}}
        out = canonicalize(r)
        assert out == '{"outer":{"a":2,"z":1}}'

    def test_valid_json_roundtrip(self):
        import json
        r = {"schema_version": "1", "face_similarity": 0.84, "source_url": "https://x.com"}
        out = canonicalize(r)
        parsed = json.loads(out)
        assert parsed == r


class TestFingerprintDeterminism:
    def test_same_record_same_hash(self):
        record = {
            "schema_version": "1",
            "source_url": "https://example.com",
            "face_similarity": 0.84,
        }
        h1 = sha256_fingerprint(canonicalize(record))
        h2 = sha256_fingerprint(canonicalize(record))
        assert h1 == h2

    def test_different_field_different_hash(self):
        r1 = {"title": "Original Post", "url": "https://example.com"}
        r2 = {"title": "Modified Post", "url": "https://example.com"}
        _, fp1 = fingerprint_record(r1)
        _, fp2 = fingerprint_record(r2)
        assert fp1 != fp2

    def test_field_order_same_hash(self):
        r1 = {"a": 1, "b": 2}
        r2 = {"b": 2, "a": 1}
        _, fp1 = fingerprint_record(r1)
        _, fp2 = fingerprint_record(r2)
        assert fp1 == fp2

    def test_fingerprint_is_hex64(self):
        r = {"x": 1}
        _, fp = fingerprint_record(r)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_numeric_type_matters(self):
        """0.84 and 0.840 should produce the same JSON, but '0.84' (string) differs."""
        r_float  = {"similarity": 0.84}
        r_string = {"similarity": "0.84"}
        _, fp_float  = fingerprint_record(r_float)
        _, fp_string = fingerprint_record(r_string)
        assert fp_float != fp_string

    def test_known_fingerprint(self):
        """Regression: fixed input must always produce the same hash."""
        import hashlib, json
        record = {"face_similarity": 0.84, "schema_version": "1", "source_url": "https://example.com"}
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        _, actual = fingerprint_record(record)
        assert actual == expected
