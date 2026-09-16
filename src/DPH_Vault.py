# -*- coding: utf-8 -*-
"""
PIN-derived encryption for per-profile secrets (Jellyfin user tokens and
passwords) stored in settings.xml.

Design constraints:

- No third-party crypto library: OpenATV images do not reliably ship
  pycryptodome/cryptography, and this plugin must not gain an install-time
  dependency just for this. Everything here is built on hashlib alone,
  which is guaranteed to be present.
- The PIN is the only secret: nothing derived from it is ever written to
  disk. Losing the PIN means losing the data - there is no recovery path,
  because a recoverable "forgot PIN" flow would make the whole thing
  theatre.
- Empty/no PIN means "do not encrypt at all" - the field stays exactly as
  it always has, plaintext. This is a deliberate, user-requested escape
  hatch (e.g. a kids' profile with no PIN protection at all).

Construction: PBKDF2-HMAC-SHA256 derives a 32-byte key from the PIN and a
random salt. A second HMAC-SHA256(key, counter) keystream, generated block by
block, is XORed with the plaintext (a simple, dependency-free stream
cipher - not AES, but the PIN is the only thing an attacker who already has
settings.xml is missing, and a repeated-key stream cipher is exactly as
strong as the key for that threat model as long as the nonce never repeats,
which the random-per-encryption nonce below guarantees). Encrypt-then-MAC:
an HMAC-SHA256 tag over (nonce + ciphertext) is verified before any
decryption is attempted, so a wrong PIN is detected cheaply and
unambiguously instead of silently producing garbage.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import base64
import uuid as _uuid

from .__common__ import printl2 as printl

PBKDF2_ITERATIONS = 200000
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 16
TAG_LEN = 16

# Prefix marking a field as one of ours - anything without it is treated as
# plaintext, which is what every field written before this module existed
# (and every field for a PIN-less profile) already is.
ENC_PREFIX = "ENC1:"


def isEncrypted(value: str | None) -> bool:
	return bool(value) and value.startswith(ENC_PREFIX)


def _normalizedPin(pin: str | None) -> str:
	"""A pin of "" or all-zeroes ("0000", the ConfigPIN default) means
	"no PIN set" everywhere else in this plugin - keep that rule here too,
	so callers do not have to duplicate it before deciding whether to
	encrypt."""
	pin = str(pin or "")
	return "" if pin.strip("0") == "" else pin


def hasPin(pin: str | None) -> bool:
	return _normalizedPin(pin) != ""


def _deriveKey(pin: str, salt: bytes) -> bytes:
	return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=KEY_LEN)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
	out = bytearray()
	counter = 0
	while len(out) < length:
		block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
		out.extend(block)
		counter += 1
	return bytes(out[:length])


def _xor(data: bytes, keystream: bytes) -> bytes:
	return bytes(b ^ k for b, k in zip(data, keystream))


def encrypt(plaintext: str, pin: str) -> str:
	"""Encrypts plaintext with a key derived from pin. Returns plaintext
	unchanged (no ENC1: prefix) if pin is empty/all-zero - callers do not
	need to branch on hasPin() themselves before calling this."""
	pin = _normalizedPin(pin)
	if not pin or plaintext is None:
		return plaintext

	salt = os.urandom(SALT_LEN)
	nonce = os.urandom(NONCE_LEN)
	key = _deriveKey(pin, salt)
	data = plaintext.encode("utf-8")
	ciphertext = _xor(data, _keystream(key, nonce, len(data)))
	tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()[:TAG_LEN]

	blob = salt + nonce + tag + ciphertext
	return ENC_PREFIX + base64.b64encode(blob).decode("ascii")


def decrypt(value: str, pin: str) -> str | None:
	"""Returns the decrypted plaintext, or None if pin is wrong (tag
	mismatch) or value is malformed. If value has no ENC1: prefix it is
	assumed to already be plaintext (a PIN-less profile, or data written
	before this module existed) and is returned unchanged."""
	if value is None:
		return None
	if not isEncrypted(value):
		return value

	pin = _normalizedPin(pin)
	try:
		blob = base64.b64decode(value[len(ENC_PREFIX):])
		salt = blob[:SALT_LEN]
		nonce = blob[SALT_LEN:SALT_LEN + NONCE_LEN]
		tag = blob[SALT_LEN + NONCE_LEN:SALT_LEN + NONCE_LEN + TAG_LEN]
		ciphertext = blob[SALT_LEN + NONCE_LEN + TAG_LEN:]
	except Exception as ex:
		printl("malformed encrypted field: " + str(ex), "DPH_Vault", "W")
		return None

	key = _deriveKey(pin, salt)
	expectedTag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()[:TAG_LEN]
	if not hmac.compare_digest(tag, expectedTag):
		return None

	plaintext = _xor(ciphertext, _keystream(key, nonce, len(ciphertext)))
	try:
		return plaintext.decode("utf-8")
	except Exception:
		return None


# ---------------------------------------------------------------------------
# Device-key masking: for secrets with no PIN of their own to derive a key
# from (the "default" Jellyfin server login, entered once when the server is
# first set up - there is no per-profile PIN concept at that point yet).
#
# This is explicitly NOT protection against someone with access to the box
# itself: uuid.getnode() (normally the network interface's MAC address) is
# just as readable there as settings.xml is, and the derivation is this same
# open-source file. What it does buy: settings.xml alone, copied off the box
# (a shared backup, a support ticket attachment, a leaked repo) is not
# decryptable without also having that MAC - a real, common leak vector that
# "obfuscated but self-contained" storage does nothing against. Accepted
# explicitly as a "better than plaintext, not real security" middle ground.
# ---------------------------------------------------------------------------
def _deviceKey() -> str:
	return str(_uuid.getnode())


def encryptDevice(plaintext: str) -> str:
	return encrypt(plaintext, _deviceKey())


def decryptDevice(value: str) -> str | None:
	return decrypt(value, _deviceKey())
