from unittest.mock import Mock, patch

import pytest

from saltbox_sdk.utilities.lua_script import LuaScript


@pytest.mark.parametrize('content', ['return 1', ''])
def test_script_is_read_lazily_and_cached(content: str) -> None:
    resource = Mock()
    resource.read_text.return_value = content
    with patch('saltbox_sdk.utilities.lua_script.files') as files:
        files.return_value.joinpath.return_value = resource
        script = LuaScript('utilities/lua/example.lua')
        files.assert_not_called()
        assert script.content == content
        assert script.content == content
        files.assert_called_once_with('saltbox_sdk')
        files.return_value.joinpath.assert_called_once_with('utilities/lua/example.lua')
        resource.read_text.assert_called_once_with(encoding='utf-8')


def test_failed_read_is_not_cached() -> None:
    resource = Mock()
    resource.read_text.side_effect = [FileNotFoundError('missing'), 'return 1']
    with patch('saltbox_sdk.utilities.lua_script.files') as files:
        files.return_value.joinpath.return_value = resource
        script = LuaScript('utilities/lua/example.lua')
        with pytest.raises(FileNotFoundError):
            _ = script.content
        assert script.content == 'return 1'
        assert script.content == 'return 1'
        assert resource.read_text.call_count == 2
