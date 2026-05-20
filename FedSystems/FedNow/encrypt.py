# aes_gcm.py
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives import hashes, serialization
import sys


def encrypt(infile, outfile, recipient_pub_pem):
    """Encrypt infile -> outfile (nonce + ciphertext) and write RSA-wrapped AES key to outfile + '.key.enc'.

    Args:
        infile: path to plaintext file
        outfile: path to write encrypted file
        recipient_pub_pem: path to recipient's RSA public key in PEM format
    """
    # generate AES-256-GCM key
    key = os.urandom(32)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)

    with open(infile, 'rb') as f:
        data = f.read()

    ct = aesgcm.encrypt(nonce, data, None)
    with open(outfile, 'wb') as f:
        f.write(nonce + ct)

    # load recipient public key: try PEM, then OpenSSH format
    with open(recipient_pub_pem, 'rb') as f:
        key_data = f.read()
    try:
        pub = serialization.load_pem_public_key(key_data)
    except Exception:
        pub = serialization.load_ssh_public_key(key_data)

    enc_key = pub.encrypt(
        key,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    keyfile = outfile + '.key.enc'
    with open(keyfile, 'wb') as f:
        f.write(enc_key)

    print('Encrypted ->', outfile, 'wrapped-key ->', keyfile)


def decrypt(infile, outfile, recipient_priv_pem, keyfile_enc):
    """Decrypt infile using RSA-unwrapped AES key.

    Args:
        infile: path to encrypted file (nonce + ct)
        outfile: path to write decrypted plaintext
        recipient_priv_pem: path to recipient's RSA private key in PEM format
        keyfile_enc: path to RSA-wrapped AES key file
    """
    # load wrapped AES key
    with open(keyfile_enc, 'rb') as f:
        enc_key = f.read()

    # load private key: try PEM, then OpenSSH private key format
    with open(recipient_priv_pem, 'rb') as f:
        key_data = f.read()
    try:
        priv = serialization.load_pem_private_key(key_data, password=None)
    except Exception:
        priv = serialization.load_ssh_private_key(key_data, password=None)

    key = priv.decrypt(
        enc_key,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    with open(infile, 'rb') as f:
        blob = f.read()
    nonce, ct = blob[:12], blob[12:]

    aesgcm = AESGCM(key)
    pt = aesgcm.decrypt(nonce, ct, None)
    with open(outfile, 'wb') as f:
        f.write(pt)

    print('Decrypted ->', outfile)


def _usage_and_exit():
    print('Usage: encrypt.py enc infile outfile recipient_pub.pub')
    print('       encrypt.py dec infile outfile recipient_priv keyfile.xml.enc.key.enc')
    sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        _usage_and_exit()
    cmd = sys.argv[1]
    if cmd == 'enc':
        if len(sys.argv) != 5:
            _usage_and_exit()
        encrypt(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'dec':
        if len(sys.argv) != 6:
            _usage_and_exit()
        decrypt(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        _usage_and_exit()