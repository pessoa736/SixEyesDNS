"""Testes dos perfis sintéticos do gerador: anomalias sem atalho e normais variados."""

import collections
import csv
import importlib.util
import random
import re
from pathlib import Path

import pytest

from test_generator_tranco import load_generator

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "docker" / "generator"
LABEL = re.compile(r"[A-Za-z0-9_-]{1,63}")


@pytest.fixture(scope="module")
def profiles():
    spec = importlib.util.spec_from_file_location(
        "traffic_profiles", GENERATOR_DIR / "traffic_profiles.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def anomalies(profiles) -> list[tuple[str, str, str, str]]:
    rng = random.Random(42)
    return [
        profiles.anomalous_domain(rng, index)
        for index in range(len(profiles.ANOMALY_FAMILIES) * 500)
    ]


def test_no_anomaly_carries_the_old_fixed_suffix(anomalies) -> None:
    assert all("tunnel" not in domain for domain, *_ in anomalies)
    assert all(domain.endswith(".test") for domain, *_ in anomalies)


def test_every_anomaly_is_a_valid_dns_name(anomalies) -> None:
    for domain, *_ in anomalies:
        assert len(domain) <= 253
        assert all(LABEL.fullmatch(label) for label in domain.split("."))


def test_every_family_appears_and_none_collapses_into_a_few_domains(
    profiles, anomalies
) -> None:
    by_family = collections.defaultdict(list)
    for domain, family, _, profile in anomalies:
        assert family == profile
        by_family[family].append(domain)
    assert set(by_family) == set(profiles.ANOMALY_FAMILIES)
    for family, domains in by_family.items():
        # low_entropy gerava 8 domínios únicos em 989 linhas (razão 0,008).
        assert len(set(domains)) / len(domains) > 0.95, family


def test_zones_mix_names_that_imitate_normal_infrastructure_and_own_zones(
    profiles, anomalies
) -> None:
    domains = [domain for domain, *_ in anomalies]
    imitate = sum(
        any(
            domain.endswith(f".{service}.{platform}.test")
            for service in profiles.SERVICES
            for platform in profiles.PLATFORMS
        )
        for domain in domains
    )
    own = sum(
        any(domain.endswith(f".{zone}.test") for zone in profiles.ATTACKER_ZONES)
        for domain in domains
    )
    assert imitate / len(domains) > 0.5
    assert own / len(domains) > 0.2
    assert imitate + own >= len(domains)


def test_long_payloads_are_sometimes_split_across_two_labels(profiles) -> None:
    rng = random.Random(7)
    counts = {len(profiles.payload_labels(rng, "hex")) for _ in range(200)}
    assert counts == {1, 2}


def test_generation_is_deterministic_per_seed(profiles) -> None:
    first = [profiles.anomalous_domain(random.Random(42), i) for i in range(50)]
    again = [profiles.anomalous_domain(random.Random(42), i) for i in range(50)]
    other = [profiles.anomalous_domain(random.Random(43), i) for i in range(50)]
    assert first == again
    assert first != other


def test_unknown_family_is_rejected(profiles) -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        profiles.payload_labels(random.Random(1), "xyz")


def test_new_normal_profiles_are_legitimate_and_look_like_their_kind(profiles) -> None:
    for index in range(0, 400, 7):
        for domain, label, _, profile in (
            profiles.rare_word_domain(index),
            profiles.cdn_id_domain(42, index),
            profiles.uuid_like_domain(42, index),
        ):
            assert label == "normal" and profile in {"normal", "normal_hard"}
            assert domain.endswith(".test") and "tunnel" not in domain
            assert all(LABEL.fullmatch(part) for part in domain.split("."))
    cdn = profiles.cdn_id_domain(42, 17)[0].split(".")[0]
    assert len(cdn) == 14 and cdn[0] == "d"
    uuid = profiles.uuid_like_domain(42, 18)[0].split(".")[0]
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}", uuid)
    rare = {profiles.rare_word_domain(index)[0].split(".")[0] for index in range(0, 800, 5)}
    assert len({name.split("-")[0] for name in rare}) > 20


def test_generator_uses_the_new_profiles_end_to_end(
    profiles, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_generator(monkeypatch, tmp_path, "profiles", tmp_path / "sem-ranking.csv")
    module.main()
    with module.LABELS_PATH.open(newline="", encoding="utf-8") as labels_file:
        rows = list(csv.DictReader(labels_file))
    assert len(rows) == 400
    assert all("tunnel" not in row["query"] for row in rows)
    suspects = {row["family"] for row in rows if row["label"] == "suspeita"}
    assert suspects == set(profiles.ANOMALY_FAMILIES)
    normal_profiles = {row["profile"] for row in rows if row["label"] == "normal"}
    assert {"normal", "normal_hard", "normal_meme", "normal_jjk"} <= normal_profiles
    assert any(re.fullmatch(r"d[a-z2-7]{13}\.cdn\..+\.test", row["query"]) for row in rows)
