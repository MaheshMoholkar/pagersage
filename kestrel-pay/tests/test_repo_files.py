import yaml
from conftest import ROOT, load_script

repo_files = load_script("scripts/repo_files.py")


def _services() -> list[str]:
    topo = yaml.safe_load((ROOT / "company" / "topology.yaml").read_text())
    return [s["name"] for s in topo["services"]]


def test_one_folder_per_service():
    folders = {p.name for p in (ROOT / "services").iterdir() if p.is_dir()}
    assert folders == set(_services())
    for name in folders:
        folder = ROOT / "services" / name
        assert (folder / "README.md").is_file()
        assert isinstance(yaml.safe_load((folder / "config.yaml").read_text()), dict)


def test_payments_db_has_pool_size():
    cfg = yaml.safe_load((ROOT / "services" / "payments-db" / "config.yaml").read_text())
    assert cfg["max_pool_size"] == 200


def test_generated_files_are_fresh():
    stale = repo_files.stale()
    assert not stale, f"run scripts/repo_files.py: {[str(p) for p in stale]}"
