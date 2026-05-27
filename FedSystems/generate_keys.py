#!/usr/bin/env python3
"""
Generate SSH keys for banks based on .env configuration.
Reads bank names from .env file and creates RSA 4096 keypairs.
"""

import os
import re
import subprocess
from pathlib import Path


def parse_env(env_file):
    """Parse .env file and extract exact BANKN entries (e.g. BANK0, BANK1).

    This ignores keys like BANK0_RTN or BANK_NAME — only keys matching
    the regex ^BANK\d+$ are accepted.
    """
    banks = {}
    if not os.path.exists(env_file):
        print(f"ERROR: {env_file} not found")
        return banks

    pattern = re.compile(r'^BANK\d+$')
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            # skip empty lines and comments
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if pattern.fullmatch(key):
                banks[key] = value

    return banks


def sanitize_name(name):
    """Sanitize bank name for use as folder name."""
    # Remove leading/trailing whitespace
    name = name.strip()
    # Replace spaces with hyphens
    name = name.replace(' ', '-')
    # Remove invalid filesystem characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Convert to lowercase
    name = name.lower()
    return name


def create_key(bank_name, keys_dir):
    """Create SSH keypair for a bank."""
    sanitized = sanitize_name(bank_name)
    bank_dir = os.path.join(keys_dir, sanitized)
    
    # Create directory if it doesn't exist
    os.makedirs(bank_dir, exist_ok=True)
    
    key_file = os.path.join(bank_dir, 'id_rsa')
    
    # Skip if keys already exist
    if os.path.exists(key_file):
        print(f"Skipping {sanitized}: keys already exist.")
        return True
    
    # Check if ssh-keygen is available
    result = subprocess.run(['where', 'ssh-keygen'], 
                          capture_output=True)
    if result.returncode != 0:
        print("ERROR: ssh-keygen not found in PATH.")
        return False
    
    # Generate the key
    print(f"Generating 4096-bit RSA keypair for {sanitized}...")
    result = subprocess.run([
        'ssh-keygen',
        '-t', 'rsa',
        '-b', '4096',
        '-f', key_file,
        '-N', ''
    ], capture_output=True)
    
    if result.returncode != 0:
        print(f"Failed to generate key for {sanitized}.")
        return False
    else:
        print(f"Created {bank_dir}\\id_rsa and {bank_dir}\\id_rsa.pub")
        return True


def main():
    # TODO: Add option to prevent overwriting existing keys, or to force regeneration
    script_dir = Path(__file__).parent
    env_file = script_dir / '.env'
    keys_dir = script_dir / 'SFTP_Keys'
    
    # Create SFTP_Keys directory
    keys_dir.mkdir(exist_ok=True)
    
    # Parse .env
    banks = parse_env(str(env_file))
    
    if not banks:
        print("No banks found in .env file.")
        return
    
    # Generate keys for each bank
    for key in sorted(banks.keys()):
        bank_name = banks[key]
        create_key(bank_name, str(keys_dir))

    # Generate key for FRB
    frb_dir = keys_dir / 'frb'
    frb_dir.mkdir(exist_ok=True)
    frb_key_file = frb_dir / 'id_rsa'
    if not frb_key_file.exists():
        print("Generating 4096-bit RSA keypair for FRB...")
        result = subprocess.run([
            'ssh-keygen',
            '-t', 'rsa',
            '-b', '4096',
            '-f', str(frb_key_file),
            '-N', ''
        ], capture_output=True)
        
        if result.returncode != 0:
            print("Failed to generate key for FRB.")
        else:
            print(f"Created {frb_key_file} and {frb_key_file}.pub")
    
    print("Done.")


if __name__ == '__main__':
    main()
