from pathlib import Path
from typing import cast

from gnupg import GPG, GenKey, ListKeys, Sign  # type: ignore

from salt_box_core.config import SETTINGS


class SaltBoxCrypt:
    _gpg: GPG = None
    _pubkey: str | None = None
    _pubkey_path: Path | None = None
    _keyid: str | None = None
    _fingerprint: str | None = None

    def __init__(self, pubkey_path: Path | None = None) -> None:
        if pubkey_path:
            self._pubkey_path = pubkey_path

        self.load_key(self.pubkey_path)

    @property
    def gpg(self) -> GPG:
        if self._gpg:
            return self._gpg

        # Prepare dir
        gnupg_home_path = Path(SETTINGS.var_dir).joinpath('gpg')
        if not gnupg_home_path.exists():
            gnupg_home_path.mkdir(parents=True, exist_ok=True)
        gnupg_home_path.chmod(0o700)

        # Init GPG
        gpg = GPG(gnupghome=gnupg_home_path.as_posix())
        gpg.encoding = 'utf-8'

        self._gpg = gpg
        return self._gpg

    @property
    def pubkey_path(self) -> Path:
        if self._pubkey_path is None:
            self._pubkey_path = Path(self.gpg.gnupghome).joinpath('saltbox_core_pubkey.gpg')

        return self._pubkey_path

    @property
    def pubkey(self) -> str:
        if self._pubkey:
            return self._pubkey

        raise KeyError

    def load_key(self, path: Path | None = None) -> None:
        if path is None:
            path = self.pubkey_path

        if path.exists():
            with self.pubkey_path.open('r') as key_file:
                self._pubkey = key_file.read()
                self.gpg.import_keys(self._pubkey)
        else:
            uid = self.get_uid()
            existed_keys: ListKeys = cast(ListKeys, self.gpg.list_keys())

            for key in existed_keys:
                keyid = key['keyid']
                fingerprint = key['fingerprint']
                if key['type'] == 'pub':
                    if key['length'] == str(SETTINGS.gpg_key_length) and uid in key['uids']:
                        self._pubkey = cast(str, self.gpg.export_keys(keyid))
                        self._keyid = keyid
                        self._fingerprint = fingerprint
                        with path.open('w') as key_file:
                            key_file.write(self._pubkey)
                    else:
                        self.gpg.delete_keys(fingerprint)

            if not self._pubkey:
                input_data: str = self.get_key_input_data()
                self.gen_key(input_data=input_data)
                self.load_key(path=path)

    def get_key_input_data(self) -> str:
        return cast(
            str,
            self.gpg.gen_key_input(
                **{
                    'key-type': 'RSA',
                    'key-length': SETTINGS.gpg_key_length,
                    'name-real': SETTINGS.gog_key_name_real,
                    'name-comment': SETTINGS.gpg_key_comment,
                    'name-email': SETTINGS.gpg_key_email,
                    'expire-date': 0,
                    'passphrase': None,
                }
            ),
        )

    def get_uid(self) -> str:
        return f'{SETTINGS.gog_key_name_real} ({SETTINGS.gpg_key_comment}) <{SETTINGS.gpg_key_email}>'

    def gen_key(self, input_data: str) -> str:
        gen_result: GenKey = cast(GenKey, self.gpg.gen_key(input=input_data))
        return str(gen_result.fingerprint)

    # def encrypt_str(self, value: str) -> str:
    #     return cast(str, self.gpg.encrypt(value, self.get_uid()))

    # def decrypt_str(self, value: str) -> str:
    #     return cast(str, self.gpg.decrypt(value))

    def sign_str(self, message: str) -> str:
        sign_result: Sign = cast(Sign, self.gpg.sign(message=message, **{'detach': True}))
        return str(sign_result)

    # def verify_str(self, value: str) -> bool:
    #     return cast(bool, self.gpg.verify(input=value))
