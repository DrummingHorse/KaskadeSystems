"""Known-answer and cross-implementation tests for the standard-library crypto."""
import hashlib
import os
import random
import shutil
import subprocess
import tempfile
import unittest

from prospektor import eip712
from prospektor import secp256k1 as ec
from prospektor.keccak import keccak256, sponge256

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec as cec
    from cryptography.hazmat.primitives.asymmetric import utils as cutils
except (KeyboardInterrupt, SystemExit):
    raise
except BaseException:  # missing, or a broken binary build that panics on import
    cec = None

MAIL_TYPES = {
    "Person": [{"name": "name", "type": "string"}, {"name": "wallet", "type": "address"}],
    "Mail": [{"name": "from", "type": "Person"}, {"name": "to", "type": "Person"},
             {"name": "contents", "type": "string"}],
}
MAIL_DOMAIN = {"name": "Ether Mail", "version": "1", "chainId": 1,
               "verifyingContract": "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC"}
MAIL = {"from": {"name": "Cow", "wallet": "0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826"},
        "to": {"name": "Bob", "wallet": "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB"}, "contents": "Hello, Bob!"}


class KeccakTests(unittest.TestCase):
    def test_published_vectors(self):
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_permutation_matches_hashlib_sha3(self):
        rng = random.Random(8183)
        lengths = list(range(0, 280)) + [rng.randrange(280, 3000) for _ in range(40)]
        for n in lengths:
            msg = rng.randbytes(n)
            self.assertEqual(sponge256(msg, 0x06), hashlib.sha3_256(msg).digest(), n)


class EIP712Tests(unittest.TestCase):
    """The test vector published with EIP-712 (assets/eip-712/Example.js)."""

    def test_spec_vector(self):
        self.assertEqual(eip712.encode_type("Mail", MAIL_TYPES),
                         "Mail(Person from,Person to,string contents)Person(string name,address wallet)")
        self.assertEqual(eip712.type_hash("Mail", MAIL_TYPES).hex(),
                         "a0cedeb2dc280ba39b857546d74f5549c3a1d7bdc2dd96bf881f76108e23dac2")
        self.assertEqual(eip712.hash_struct("Mail", MAIL, MAIL_TYPES).hex(),
                         "c52c0ee5d84264471806290a3f2c4cecfc5490626bf912d01f240d7a274b371e")
        self.assertEqual(eip712.domain_separator(MAIL_DOMAIN).hex(),
                         "f2cee375fa42b42143804025fc449deafd50cc031ca257e0b194a650a912090f")
        digest = eip712.digest(MAIL_DOMAIN, "Mail", MAIL, MAIL_TYPES)
        self.assertEqual(digest.hex(), "be609aee343fb3c4b28e1df9e632fca64fcfaede20f02e86244efddf30957bd2")
        priv = int.from_bytes(keccak256(b"cow"), "big")
        self.assertEqual(ec.address_of(ec.public_key(priv)).lower(), "0xcd2a3d9f938e13cd947ec05abc7fe734df8dd826")
        v, r, s = ec.sign(digest, priv)
        self.assertEqual(v, 28)
        self.assertEqual(r, 0x4355c47d63924e8a72e509b65029052eb6c299d53a04e167c5775fd466751c9d)
        self.assertEqual(s, 0x07299936d304c153f6443dfa05f40ff007d72911b6f72307f996231605b91562)

    def test_rejects_bad_values(self):
        types = {"T": [{"name": "a", "type": "uint8"}]}
        for bad in (256, -1, True, "1"):
            with self.assertRaises((ValueError, TypeError)):
                eip712.hash_struct("T", {"a": bad}, types)
        with self.assertRaises(ValueError):
            eip712.hash_struct("T", {"a": 1, "extra": 2}, types)


class Secp256k1Tests(unittest.TestCase):
    def test_known_addresses_and_checksums(self):
        self.assertEqual(ec.address_of(ec.public_key(1)), "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf")
        self.assertEqual(ec.address_of(ec.public_key(2)), "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF")
        for a in ("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
                  "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB", "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb"):
            self.assertEqual(ec.to_checksum_address(bytes.fromhex(a[2:])), a)

    def test_sign_recover_roundtrip_low_s(self):
        rng = random.Random(42)
        for _ in range(40):
            priv = rng.randrange(1, ec.N)
            digest = rng.randbytes(32)
            v, r, s = ec.sign(digest, priv)
            self.assertIn(v, (27, 28))
            self.assertLessEqual(s, ec.HALF_N)
            self.assertEqual(ec.recover(digest, v, r, s), ec.public_key(priv))
            self.assertTrue(ec.verify(digest, ec.public_key(priv), r, s))
            other = bytes([digest[0] ^ 1]) + digest[1:]
            self.assertNotEqual(ec.recover_address(other, v, r, s), ec.address_of(ec.public_key(priv)))

    def test_malleable_and_malformed_signatures_rejected(self):
        priv, digest = 12345, bytes(range(32))
        v, r, s = ec.sign(digest, priv)
        with self.assertRaises(ec.SignatureError):
            ec.recover(digest, 55 - v, r, ec.N - s)  # the high-s twin (EIP-2)
        for args in ((26, r, s), (v, 0, s), (v, r, 0), (v, ec.N, s)):
            with self.assertRaises(ec.SignatureError):
                ec.recover(digest, *args)

    def test_deterministic(self):
        self.assertEqual(ec.sign(b"\x07" * 32, 99), ec.sign(b"\x07" * 32, 99))

    @unittest.skipIf(cec is None, "cryptography not installed")
    def test_signatures_verify_in_openssl_via_cryptography(self):
        rng = random.Random(7)
        for _ in range(25):
            priv = rng.randrange(1, ec.N)
            digest = rng.randbytes(32)
            _, r, s = ec.sign(digest, priv)
            key = cec.EllipticCurvePublicKey.from_encoded_point(cec.SECP256K1(), ec.pubkey_bytes(ec.public_key(priv)))
            key.verify(cutils.encode_dss_signature(r, s), digest, cec.ECDSA(cutils.Prehashed(hashes.SHA256())))
            other = cec.derive_private_key(priv, cec.SECP256K1()).public_key().public_numbers()
            self.assertEqual((other.x, other.y), ec.public_key(priv))

    @unittest.skipIf(shutil.which("openssl") is None, "openssl command not available")
    def test_signatures_verify_in_openssl_cli(self):
        priv, digest = ec.demo_private_key("openssl-cli"), hashlib.sha256(b"assay").digest()
        _, r, s = ec.sign(digest, priv)

        def der_int(v):
            b = v.to_bytes((v.bit_length() + 8) // 8, "big")
            return b"\x02" + bytes([len(b)]) + b

        sig = der_int(r) + der_int(s)
        with tempfile.TemporaryDirectory() as d:
            files = {"k": os.path.join(d, "k.der"), "m": os.path.join(d, "m"), "s": os.path.join(d, "s")}
            spki = bytes.fromhex("3056301006072a8648ce3d020106052b8104000a034200") + ec.pubkey_bytes(ec.public_key(priv))
            for key, data in (("k", spki), ("m", digest), ("s", b"\x30" + bytes([len(sig)]) + sig)):
                with open(files[key], "wb") as fh:
                    fh.write(data)
            cmd = ["openssl", "pkeyutl", "-verify", "-pubin", "-keyform", "DER", "-inkey", files["k"],
                   "-in", files["m"], "-sigfile", files["s"]]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
