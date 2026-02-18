from __future__ import annotations

import base64
import json
import os
from typing import Any, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import JsonValue

from saltbox_core.config import SETTINGS, logger
from saltbox_core.pillars.exceptions import (
    PillarCryptoException,
    PillarEncryptionKeyNotConfiguredException,
    PillarInvalidEncryptionPayloadException,
)
from saltbox_core.pillars.schemas import PillarTgtType
from saltbox_sdk.db.mongo.schemas_base import PyObjectId


class PillarCryptoService:
    """Pillars encrypt-at-rest helper.

    Implements local envelope encryption (KEK/DEK) without KMS:
    - KEK (from config) is used to wrap (encrypt) a random DEK
    - DEK is used to encrypt the actual JSON payload
    """

    _ENC_MARKER_KEY = '$enc'
    _ENC_FORMAT_VERSION = 1

    @staticmethod
    def _b64e(data: bytes) -> str:
        return base64.b64encode(data).decode('ascii')

    @staticmethod
    def _b64d(data_b64: str) -> bytes:
        try:
            return base64.b64decode(data_b64.encode('ascii'), validate=True)
        except Exception as e:
            raise PillarCryptoException() from e

    @classmethod
    def _get_enc_payload(cls, value: JsonValue) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        payload = value.get(cls._ENC_MARKER_KEY)
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _get_kek(cls) -> bytes:
        if not SETTINGS.pillars_kek_b64:
            raise PillarEncryptionKeyNotConfiguredException()

        key = cls._b64d(SETTINGS.pillars_kek_b64)
        if len(key) != 32:
            msg = 'Invalid pillars_kek_b64 length (expected 32 bytes for AES-256-GCM).'
            raise PillarCryptoException(detail=msg)
        return key

    @staticmethod
    def _generate_dek() -> bytes:
        # 32 bytes for AES-256-GCM
        return os.urandom(32)

    @staticmethod
    def _wrap_aad(*, kid: str, data_aad: str) -> str:
        # Separate AAD namespace for DEK wrapping.
        return f'pillars-dek:{kid}:{data_aad}'

    @staticmethod
    def _canonical_json(value: JsonValue) -> bytes:
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')

    @staticmethod
    def build_aad(*, name: str, pillarenv: str, tgt_type: PillarTgtType, tgt_id: PyObjectId | None) -> str:
        # Stable context binding; if any of these change, decrypt will fail.
        return f'pillars:{tgt_type}:{tgt_id}:{pillarenv}:{name}'

    def is_encrypted_value(self, value: JsonValue) -> bool:
        payload = self._get_enc_payload(value)
        logger.debug('Checking if value is encrypted: has_payload=%s', payload is not None)
        return payload is not None

    def encrypt_json_value(self, value: JsonValue, *, aad: str) -> dict[str, Any]:
        kek = self._get_kek()
        kid = SETTINGS.pillars_kid

        dek = self._generate_dek()

        data_aesgcm = AESGCM(dek)
        data_nonce = os.urandom(12)
        plaintext = self._canonical_json(value)

        ciphertext = data_aesgcm.encrypt(data_nonce, plaintext, aad.encode('utf-8'))

        wrap_aesgcm = AESGCM(kek)
        wrap_nonce = os.urandom(12)
        dek_wrapped = wrap_aesgcm.encrypt(
            wrap_nonce,
            dek,
            self._wrap_aad(kid=kid, data_aad=aad).encode('utf-8'),
        )

        return {
            self._ENC_MARKER_KEY: {
                'v': self._ENC_FORMAT_VERSION,
                'alg': 'A256GCM',
                'kid': kid,
                'nonce_b64': self._b64e(data_nonce),
                'ct_b64': self._b64e(ciphertext),
                'dek_wrap_alg': 'A256GCM',
                'dek_wrap_nonce_b64': self._b64e(wrap_nonce),
                'dek_wrapped_b64': self._b64e(dek_wrapped),
            }
        }

    def decrypt_json_value(self, value: JsonValue, *, aad: str) -> JsonValue:
        if not self.is_encrypted_value(value):
            return value

        if not isinstance(value, dict):
            msg = 'Invalid encrypted value type'
            raise PillarCryptoException(detail=msg)

        try:
            payload = self._get_enc_payload(value)
            if payload is None:
                raise PillarInvalidEncryptionPayloadException()

            version = payload.get('v')
            if version != self._ENC_FORMAT_VERSION:
                raise PillarInvalidEncryptionPayloadException()

            kid = payload.get('kid')
            if not isinstance(kid, str):
                raise PillarInvalidEncryptionPayloadException()
            if kid != SETTINGS.pillars_kid:
                msg = f'Unknown pillars kid: {kid}'
                raise PillarCryptoException(detail=msg)

            nonce_b64 = payload.get('nonce_b64')
            ct_b64 = payload.get('ct_b64')
            wrap_nonce_b64 = payload.get('dek_wrap_nonce_b64')
            dek_wrapped_b64 = payload.get('dek_wrapped_b64')
            if (
                not isinstance(nonce_b64, str)
                or not isinstance(ct_b64, str)
                or not isinstance(wrap_nonce_b64, str)
                or not isinstance(dek_wrapped_b64, str)
            ):
                raise PillarInvalidEncryptionPayloadException()

            nonce = self._b64d(nonce_b64)
            ciphertext = self._b64d(ct_b64)
            wrap_nonce = self._b64d(wrap_nonce_b64)
            dek_wrapped = self._b64d(dek_wrapped_b64)

            kek = self._get_kek()
            wrap_aesgcm = AESGCM(kek)
            dek = wrap_aesgcm.decrypt(
                wrap_nonce,
                dek_wrapped,
                self._wrap_aad(kid=kid, data_aad=aad).encode('utf-8'),
            )

            data_aesgcm = AESGCM(dek)
            plaintext = data_aesgcm.decrypt(nonce, ciphertext, aad.encode('utf-8'))
            decrypted = json.loads(plaintext.decode('utf-8'))
            return cast(JsonValue, decrypted)
        except PillarEncryptionKeyNotConfiguredException:
            raise
        except Exception as e:
            raise PillarCryptoException() from e

    def encrypt_if_needed(
        self,
        *,
        value: JsonValue,
        is_secret: bool,
        name: str,
        pillarenv: str,
        tgt_type: PillarTgtType,
        tgt_id: PyObjectId | None,
    ) -> JsonValue:
        if not is_secret or self.is_encrypted_value(value):
            return value

        aad = self.build_aad(name=name, pillarenv=pillarenv, tgt_type=tgt_type, tgt_id=tgt_id)
        encrypted: dict[str, Any] = self.encrypt_json_value(value, aad=aad)
        return encrypted

    def decrypt_if_needed(
        self,
        *,
        value: JsonValue,
        is_secret: bool,
        name: str,
        pillarenv: str,
        tgt_type: PillarTgtType,
        tgt_id: PyObjectId | None,
    ) -> JsonValue:
        if not is_secret and not self.is_encrypted_value(value):
            return value

        aad = self.build_aad(name=name, pillarenv=pillarenv, tgt_type=tgt_type, tgt_id=tgt_id)
        return self.decrypt_json_value(value, aad=aad)


def get_pillar_crypto_service() -> PillarCryptoService:
    return PillarCryptoService()
