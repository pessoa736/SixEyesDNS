"""Testes da fonte opcional de domínios externos do gerador (sem dnspython)."""

import ast
import importlib.util
import random
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "docker" / "generator" / "external_domains.py"


def load_module():
    spec = importlib.util.spec_from_file_location("external_domains", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


external_domains = load_module()


def write_ranking(path: Path, lines: list[str], newline: str = "\n") -> Path:
    path.write_text(newline.join(lines) + newline, encoding="utf-8")
    return path


def test_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert external_domains.load_external_domains(tmp_path / "ausente.csv", 100) == []


def test_limit_keeps_the_best_ranked_domains(tmp_path: Path) -> None:
    ranking = write_ranking(
        tmp_path / "top.csv", [f"{rank},site{rank}.com" for rank in range(1, 6)]
    )
    assert external_domains.load_external_domains(ranking, 3) == [
        "site1.com",
        "site2.com",
        "site3.com",
    ]
    assert len(external_domains.load_external_domains(ranking, 100)) == 5
    assert external_domains.load_external_domains(ranking, 0) == []
    assert external_domains.load_external_domains(ranking, -1) == []


def test_domains_follow_rank_order_even_if_file_is_unsorted(tmp_path: Path) -> None:
    ranking = write_ranking(tmp_path / "top.csv", ["3,c.com", "1,a.com", "2,b.com"])
    assert external_domains.load_external_domains(ranking, 10) == ["a.com", "b.com", "c.com"]


def test_duplicates_keep_the_best_ranked_occurrence(tmp_path: Path) -> None:
    ranking = write_ranking(
        tmp_path / "top.csv", ["1,Exemplo.com", "2,outro.com", "3,exemplo.com", "4,EXEMPLO.COM."]
    )
    assert external_domains.load_external_domains(ranking, 10) == ["exemplo.com", "outro.com"]


def test_names_are_normalized_to_lowercase_without_trailing_dot(tmp_path: Path) -> None:
    ranking = write_ranking(
        tmp_path / "top.csv", ["1,  Sub.Exemplo.COM. ", "2,xn--exemplo-jqb.com"]
    )
    assert external_domains.load_external_domains(ranking, 10) == [
        "sub.exemplo.com",
        "xn--exemplo-jqb.com",
    ]


@pytest.mark.parametrize(
    "invalid_line",
    [
        "rank,domain",
        "1",
        "abc,exemplo.com",
        "0,exemplo.com",
        "1,",
        "1,-exemplo.com",
        "1,exemplo-.com",
        "1,exem plo.com",
        "1,exemplo_um.com",
        "1,exemplo..com",
        "1,.exemplo.com",
        "1,exémplo.com",
        "1,exemplo.com/caminho",
        "1," + "a" * 45 + ".com",
    ],
)
def test_invalid_entries_are_discarded(tmp_path: Path, invalid_line: str) -> None:
    ranking = write_ranking(tmp_path / "top.csv", [invalid_line, "2,valido.com"])
    assert external_domains.load_external_domains(ranking, 10) == ["valido.com"]


def test_length_limit_is_48_characters(tmp_path: Path) -> None:
    longest_valid = "a" * 44 + ".com"
    too_long = "a" * 45 + ".com"
    assert len(longest_valid) == external_domains.MAX_DOMAIN_LENGTH
    ranking = write_ranking(tmp_path / "top.csv", [f"1,{too_long}", f"2,{longest_valid}"])
    assert external_domains.load_external_domains(ranking, 10) == [longest_valid]


def test_bom_and_windows_line_endings_are_accepted(tmp_path: Path) -> None:
    ranking = tmp_path / "top.csv"
    ranking.write_bytes(b"\xef\xbb\xbf1,primeiro.com\r\n2,segundo.com\r\n")
    assert external_domains.load_external_domains(ranking, 10) == ["primeiro.com", "segundo.com"]


def test_pick_is_deterministic_per_seed_and_index() -> None:
    domains = [f"site{number}.com" for number in range(50)]
    first = [external_domains.pick_external_domain(domains, 42, index) for index in range(200)]
    second = [external_domains.pick_external_domain(domains, 42, index) for index in range(200)]
    other_seed = [external_domains.pick_external_domain(domains, 7, index) for index in range(200)]
    assert first == second
    assert first != other_seed
    assert len(set(first)) > 20


def test_pick_covers_the_whole_list() -> None:
    domains = [f"site{number}.com" for number in range(20)]
    picked = {external_domains.pick_external_domain(domains, 42, index) for index in range(2000)}
    assert picked == set(domains)


def test_pick_and_rate_never_touch_the_global_random_state() -> None:
    domains = ["a.com", "b.com", "c.com"]
    random.seed(1234)
    state = random.getstate()
    for index in range(100):
        external_domains.pick_external_domain(domains, 42, index)
        external_domains.is_external_index(42, index, 0.15)
    assert random.getstate() == state


def test_pick_requires_at_least_one_domain() -> None:
    with pytest.raises(ValueError, match="vazia"):
        external_domains.pick_external_domain([], 42, 0)


def test_external_index_rate_matches_the_requested_fraction() -> None:
    total = 10_000
    selected = [external_domains.is_external_index(42, index, 0.15) for index in range(total)]
    assert 0.13 < sum(selected) / total < 0.17
    assert selected == [
        external_domains.is_external_index(42, index, 0.15) for index in range(total)
    ]
    assert not any(external_domains.is_external_index(42, index, 0.0) for index in range(total))
    assert all(external_domains.is_external_index(42, index, 1.0) for index in range(total))


def test_module_only_imports_the_standard_library() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported <= sys.stdlib_module_names


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
