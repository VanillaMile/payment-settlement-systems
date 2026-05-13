# ACH

## Table of contents

- [FRB, .ach, .ack](#frb-ach-ack)
- [How to start up the server](#how-to-start-up-the-server)
- [How to register a bank](#how-to-register-a-bank)
- [How to connect with your bank profile through SFTP](#how-to-connect-with-your-bank-profile-through-sftp)
- [SFTP overview](#sftp-overview)
- [How to manage banks SFTP accounts](#how-to-manage-banks-sftp-accounts)
- [Additional api](#additional-api)

## FRB, .ACH, .ACK

Default **FRB RTN: 090000515** (You can change it in `.env` but it must be a valid rtn number)

RTN must
- Be a nine-digit number
- Number must follow this condition:
    - (3(d<sub>1</sub> + d<sub>4</sub> + d<sub>7</sub>) + 7(d<sub>2</sub> + d<sub>5</sub> + d<sub>8</sub>) + (d<sub>3</sub> + d<sub>6</sub> + d<sub>9</sub>)) mod 10 = 0
    - For example for our default FRB RTN `090000515`, the values are:
        -  (3(0 + 0 + 5) + 7(9 + 0 + 1) + (0 + 0 + 5))
        - (15 + 70 + 5) mod 10 = 90 mod 10 = 0

1. Example of .ACH file (you can use https://validator.ach-pro.com/ to highlight what each value means):
```
101 090000515 0401040122604050900A094101FRB Miku               Baguette Bank                  
5220Baguette store                      1313131310PPDLEEK PAY        260406   1040104010000001
62201010101239               0000015075               Leek store              0040104010000001
822000000100010101010000000000000000000150751313131310                         040104010000001
9000001000001000000010001010101000000000000000000015075                                       
9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999
9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999
9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999
9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999
9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999
```
File has `.ach` extension.

Guide: https://achdevguide.nacha.org/ach-file-overview

2. Example of `.ack` file (this is what bank will get after `.ach` is checked, name will be the same as `.ach` but with `.ack` extension instead and inside banks `inbound` folder)

- Successful
    - [FH] -> header line:
        1. 1 - Formatting version
        2. LIVE - current environment
        3. {File ID Modifier} - File ID Modifier from ach file header (pos. 34)
    - [R] -> record line:
        1. 2 - no. blocks of 10
        2. 20 - number of lines (2 blocks * 10 lines)
```
FH,1,LIVE,{File ID Modifier}
R,2,20
```

- Failed formatting:
    - [FH] -> header line:
        1. 1 - Formatting version
        2. LIVE - current environment
        3. {File ID Modifier} - File ID Modifier from ach file header (pos. 34)
    - [E] -> Error line:
        1. F - Formatting error
        2. 0 - line where error occurred
        3. 9999 - error code
```
FH,1,LIVE,{File ID Modifier}
E,F,0,9999,File is incomplete or unreadable
```

- Line error:
    - [FH] -> header line:
        1. 1 - Formatting version
        2. LIVE - current environment
        3. {File ID Modifier} - File ID Modifier from ach file header (pos. 34)
    - [E] -> Error line:
        1. L - Line error
        2. 5 - line where error occurred
        3. 5000 - Error code
```
FH,1,LIVE,{File ID Modifier}
E,L,5,5000,Invalid Account
E,L,6,5000,Invalid Account
```

3. After each session banks will recive `.ach` file in `outbound` directory containing transactions directed to them or their clients.

## How to start up the server

Prerequisites:
- Python (3.14)
- Docker
- ssh-keygen (Usually included with git for windows, test `ssh-keygen` in terminal)

1. Open `.env` and fill in:
    - Postgres data
    - Banks SFTP accounts (Change the names to what you want or leave as is) (for adding or removing banks see [How to manage banks SFTP accounts](#how-to-manage-banks-sftp-accounts)) (Having more SFTP accounts than banks isn't a problem, for a bank to use ACH network a separate registration is required)

2. Start `start.bat` and select option 1. Generate SFTP keys (if not yet generated)

3. Start docker engine(Can by started by running docker desktop).

4. Start `start.bat` and select option 2. Start all services, or run `docker-compose up --build` from `./FedSystems`

## How to register a bank

0. Start the server [How to start up the server](#how-to-start-up-the-server)
1. Go to frontend control panel (default url is http://localhost:3000/ `REACT_PORT` in `.env`)
2. You should see `Fed Systems Dashboard` with a list of SFTP users.
3. In registered banks click `register new bank` and fill in the data.

## How to connect with your bank profile through SFTP

Your keys are in `FedSystems/SFTP_Keys/{yourbank sftp username}`

`id_rsa.pub` is your public key and has to stay in `/SFTP_Keys` folder, to be mounted in SFTP container.

`id_rsa` is your private key, use this to log into your SFTP account.

You can check sftp connection through filezilla or any SFTP client using the following connection details:
- Host: localhost
- Port: default 2221 (`SFTP_ACH_HOST_PORT` in `.env`)
- Username: (one of the bank names you set in the `.env` file, e.g. baguette-bank)
- Authentication: Use the corresponding private key from the `SFTP_Keys` directory that was generated by the script. Folder name is same as username.
- Alternatively, you can connect through command line or a dedicated library in your code. (e.g. paramiko for python)

Example of connection through command line:

```bash
sftp -oStrictHostKeyChecking=no -i id_rsa -P 2221 baguette-bank@localhost
```
- add `-oStrictHostKeyChecking=no` to avoid problems when host public key changes.
- `-i id_rsa` is your private key from `/SFTP_Keys`
- `-P 2221` is port `2221`
- `baguette-bank@localhost` `baguette-bank` username from `.env.example` and host

### SFTP overview

In your bank account SFTP home directory you'll find:
- `inbound` directory - This is where you leave your .ach files
- `outbound` directory - This is where you can find .ach and .ack files directed to you

## How to manage banks SFTP accounts

### How to add a new SFTP user

1. Add a new `.env` variable (increment) like:
```python
BANK0 = "baguette-bank"
BANK1 = "leek-bank"
BANK2 = "bank-of-the-onion"
BANK3 = "croissant-bank"
BANK4 = "new-bank" # <--- New bank
```

2. Add a new entries in 'docker-compose.yml' by adding
    - `- ./SFTP_Keys/${BANK4}/id_rsa.pub:/home/${BANK4}/.ssh/keys/id_rsa.pub:ro` to sftp volumes. There are 2 variables to change in this line: `SFTP_Keys/${BANK4}` and `home/${BANK4}` 
    - `${BANK4}::1004:1004:inbound,outbound` to envirement `SFTP_USERS` variable, separated by spaces, `1004:1004` increment by 1
```yml
volumes:
# Add new bank volumes here: ./SFTP_Keys/<name>/id_rsa.pub:/home/<username>/.ssh/keys/id_rsa.pub:ro
      - sftp_data:/home
      - ./SFTP_Keys/${BANK0}/id_rsa.pub:/home/${BANK0}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK1}/id_rsa.pub:/home/${BANK1}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK2}/id_rsa.pub:/home/${BANK2}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK3}/id_rsa.pub:/home/${BANK3}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK4}/id_rsa.pub:/home/${BANK4}/.ssh/keys/id_rsa.pub:ro
      - ./sftp_set_perms.sh:/etc/sftp.d/set_perms.sh:ro
environment:
# Add new banks here: <username>::<uid>:<gid>:inbound,outbound
    - SFTP_USERS=${BANK0}::1000:1000:inbound,outbound ${BANK1}::1001:1001:inbound,outbound ${BANK2}::1002:1002:inbound,outbound ${BANK3}::1003:1003:inbound,outbound ${BANK4}::1004:1004:inbound,outbound
```

3. Regenerate the keys

### How to remove an SFTP user

1. Remove an `.env` variable(make sure numbers are 0 -> n) like:
```python
BANK0 = "baguette-bank"
BANK1 = "leek-bank"
BANK2 = "bank-of-the-onion"
BANK3 = "croissant-bank"
# BANK4 = "new-bank" <--- Removed bank
```

2. Remove entries in 'docker-compose.yml' by removing the 
    - `- ./SFTP_Keys/${BANK4}/id_rsa.pub:/home/${BANK3}/.ssh/keys/id_rsa.pub:ro` to sftp volumes
    - `${BANK4}::1004:1004:inbound,outbound` to envirement `SFTP_USERS` variable, separated by spaces, `1004:1004` increment by 1
```yml
volumes:
# Add new bank volumes here: ./SFTP_Keys/<name>/id_rsa.pub:/home/<username>/.ssh/keys/id_rsa.pub:ro
      - sftp_data:/home
      - ./SFTP_Keys/${BANK0}/id_rsa.pub:/home/${BANK0}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK1}/id_rsa.pub:/home/${BANK1}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK2}/id_rsa.pub:/home/${BANK2}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK3}/id_rsa.pub:/home/${BANK3}/.ssh/keys/id_rsa.pub:ro
      - ./SFTP_Keys/${BANK4}/id_rsa.pub:/home/${BANK3}/.ssh/keys/id_rsa.pub:ro
      - ./sftp_set_perms.sh:/etc/sftp.d/set_perms.sh:ro
environment:
# Add new banks here: <username>::<uid>:<gid>:inbound,outbound
    - SFTP_USERS=${BANK0}::1000:1000:inbound,outbound ${BANK1}::1001:1001:inbound,outbound ${BANK2}::1002:1002:inbound,outbound ${BANK3}::1003:1003:inbound,outbound ${BANK4}::1004:1004:inbound,outbound
```

You don't need to keys regenerate here.

## Additional api

With default `.env.example`:

Backend api docs can be found at (http://localhost:8001/docs)

Frontend panel available at (http://localhost:3000/)