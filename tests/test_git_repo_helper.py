from pathlib import Path

import pytest

from salt_box_core.settings.schemas.sls_repos_schemas import validate_path_bounds


def test_path_bounds_validator() -> None:
    assert validate_path_bounds(Path('states/')) == Path('states')
    assert validate_path_bounds(Path('states/test/')) == Path('states/test')
    assert validate_path_bounds(Path('./states/')) == Path('states')
    assert validate_path_bounds(Path('./')) == Path()
    assert validate_path_bounds(Path()) == Path()
    assert validate_path_bounds(Path('./root/.././states/')) == Path('states')

    try:
        assert validate_path_bounds(Path(r'./..\/./states/'))
    except ValueError:
        pytest.fail('False-positive validation error')

    with pytest.raises(ValueError):
        validate_path_bounds(Path('./.././states/'))
        pytest.fail('Path leads to upper directory')
