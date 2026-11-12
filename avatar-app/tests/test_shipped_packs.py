from pathlib import Path

import pytest

from avatar.pack import discover_packs, load_pack

PACKS = Path(__file__).resolve().parent.parent / "packs"
EXPECTED = {"default": "Claude mascot"}


@pytest.mark.parametrize("folder,name", EXPECTED.items())
def test_every_shipped_pack_loads_with_its_name(folder, name):
    pack = load_pack(PACKS / folder)
    assert pack.name == name


def test_the_avatar_menu_would_list_them_all():
    assert {p.name for p in discover_packs(PACKS)} >= set(EXPECTED.values())
