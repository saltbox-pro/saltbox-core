import pytest

from salt_box_core.settings.schemas.sls_repos_schemas import validate_gitfs_root


def test_gitfs_root_validator() -> None:
    assert validate_gitfs_root('states/') == 'states'
    assert validate_gitfs_root('states/test/') == 'states/test'
    assert validate_gitfs_root('./states/') == 'states'
    assert validate_gitfs_root('./states/') == 'states'
    assert validate_gitfs_root('./') == ''
    assert validate_gitfs_root('.') == ''
    assert validate_gitfs_root('./root/.././states/') == 'states'

    try:
        assert validate_gitfs_root(r'./..\/./states/')
    except ValueError:
        pytest.fail('False-positive validation error')

    with pytest.raises(ValueError):
        validate_gitfs_root('./.././states/')
        pytest.fail('Path leads to upper directory')

    # Absolute
    with pytest.raises(ValueError):
        assert validate_gitfs_root('//./.././states/') == 'states'
    with pytest.raises(ValueError):
        validate_gitfs_root('//')
    with pytest.raises(ValueError):
        assert validate_gitfs_root('/states/') == 'states'
