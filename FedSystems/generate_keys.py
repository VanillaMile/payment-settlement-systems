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
    """Parse .env file and extract BANK* entries."""
    banks = {}
    if not os.path.exists(env_file):
        print(f"ERROR: {env_file} not found")
        return banks
    
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('BANK') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
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
    
    print("Done.")


if __name__ == '__main__':
    main()
