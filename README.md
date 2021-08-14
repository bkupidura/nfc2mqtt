## nfc2mqtt
nfc2mqtt reads NFC tags with [nfcpy](https://nfcpy.readthedocs.io/en/latest/overview.html) and push them to MQTT.
nfc2mqtt stores all data in encrypted form on NFC tag. Because of that, `nfcpy` should be able to write [NDEF](https://ndeflib.readthedocs.io/en/latest/ndef.html) on used tags.
For more information about tag payload please see [nfc2mqtt tag payload](#nfc2mqtt-tag-payload).

nfc2mqtt is **NOT** "simple" bridge between NFC and MQTT. It is not suposed to scan tag ID and send it to MQTT.
It stores encrypted payload on tag/card, and send this payload to MQTT after reading (if valid).

nfc2mqtt **dosen't** store list of valid tags, tag is valid when encrypted content is valid (can be decrypted and its not expired).
Because of that, scan process is longer (~1-2s) (we need not only to `sense` nfc tag, we also need to read tag data).

### Instalation
#### Python
Python3 and pip3 should be installed and working.

```
$ pip3 install nfc2mqtt
```
#### Docker
There is ready nfc2mqtt docker image. Just pull `bkupidura/nfc2mqtt:latest`.

### Usage
#### Python
```
$ nfc2mqtt -c /etc/nfc2mqtt.yaml
```
#### Docker
You will need to discover NFC reader [usb path](https://nfcpy.readthedocs.io/en/latest/topics/get-started.html#open-a-local-device), and probably blacklist some kernel modules (`sudo modprobe -r pn533_usb`).
```
$ docker run --rm -d --name nfc2mqtt -v /data/config.yaml:/config.yaml --device /dev/bus/usb/003/009 bkupidura/nfc2mqtt:latest
```

### nfc2mqtt tag payload
All data written by `nfc2mqtt` on tag is encrypted. Its stored as `NDEF TextRecord`.
NFC tag ID can't be trusted. nfc2mqtt will **NOT use ID to identify tags**.

As nfc2mqtt stores everything in encrypted form, plenty of tag user bytes are wasted for encryption. Ex. simple payload `AnGP7 0` (`{"id": "AnGP7", "valid_till": 0}`) which without encryption is 7 bytes long, after encryption is 100 bytes long.

**Encryption of tags CAN'T be disabled.**

#### Payload
```
tag_id valid_till [data]
```
##### tag_id
Its "random" string generated during writing tag.
By default it contains `[a-zA-Z0-9]` and it is `5` character long.
##### valid_till
Stores time since `epoch` (UTC) (not valid after).
By default its set to `0`, tag is valid always (don't expire).
To generate `valid_till` from linux box use `date -d '2020-12-27T23:59:59' +%s`
##### data
Data can be used to store any user/application data.
By default it is not set.

### MQTT endpoints
#### nfc2mqtt/write_tag
Expect `empty` message or JSON message.

If `empty` message is received, next tag connected to NFC reader will be written with default payload. (random `tag_id`, 0 as `valid_till`).

If JSON message is received, next tag conneccted to NFC reader will be written as described in JSON.
Supported JSON properties:
* id - `tag_id`, if missing `tag_id` will be auto generated.
* valid_till - `valid_till`, if missing `valid_till` will be set to `0`
* data - `data`
* authenticate_password - if provided, this password will be used to authenticate to tag. For more information please see [nfcpy](https://nfcpy.readthedocs.io/en/latest/modules/tag.html#nfc.tag.Tag.authenticate). This should be used only when tags were already protected by password not known to `nfc2mqtt`.
##### Examples
Generate new tag with default values:

`$ mosquitto_pub ... -t 'nfc2mqtt/write_tag' -m ''`.

Generate new tag with known id:

`$ mosquitto_pub ... -t 'nfc2mqtt/write_tag' -m '{"id": "example"}'`

Generate new tag with valid_till:

`$ mosquitto_pub ... -t 'nfc2mqtt/write_tag' -m '{"valid_till": 1599947426}'`

Generate new tag with string data:

`$ mosquitto_pub ... -t 'nfc2mqtt/write_tag' -m '{"data": "string}'`

Generate new tag with JSON data:

`$ mosquitto_pub ... -t 'nfc2mqtt/write_tag' -m '{"data": {"json": true}}'`

Generate new tag with multiple fields:

`$ mosquitto_pub ... -t 'nfc2mqtt/write_tag' -m '{"id": "example", "valid_till": 1700000000, "data": {"field1": "value1", "field2": 1}}'`

#### nfc2mqtt/wipe_tag
Expect `empty` message.

When message is received, next tag connected to NFC reader will be formated. For more information please check [nfcpy](https://nfcpy.readthedocs.io/en/latest/modules/tag.html#nfc.tag.Tag.format).
##### Examples

`$ mosquitto_pub ... -t 'nfc2mqtt/wipe_tag' -m ''`

### MQTT publish
When valid tag is scanned, new message will be publish to `nfc2mqtt/tag/<tag_id>`.
#### Payload
`nfc2mqtt/tag/AnGP7` -> `{"status": 1, "id": "AnGP7", "valid_till": 0, "tag": {"product": "NXP NTAG213", "type": "Type2Tag", "id": "049962228b5f80"}}`

`nfc2mqtt/tag/Dj3dV` -> `{"status": 1, "id": "Dj3dV", "valid_till": 0, "data": {"custom": "value"}, "tag": {"product": "NXP NTAG213", "type": "Type2Tag", "id": "049962228b5f80"}}`

`nfc2mqtt/tag/h89u9` -> `{"status": 1, "id": "h89u9", "valid_till": 1700000000, "data": "string data", "valid_till_dt_utc": "2023-11-14 22:13:20", "tag": {"product": "NXP NTAG213", "type": "Type2Tag", "id": "049962228b5f80"}}`

### Scan tag status
* `Valid` - `1`, tag is valid and can be trusted
* `Invalid` - `2`, tag is invalid (unable to decrypt content)
* `UnknownPayloadType` - `3`, tag was readed (and decrypted) - but contains unknown payload
* `Expired` - `4`, tag already expired
* `ScanError` - `5`, nfc2mqtt was not able to scan this tag (ex. too fast removed from reader, or wrong authentication password)
* `NoNdef` - `6`, tag dosen't contains `NDEF` field used to store content (probably not formatted by nfc2mqtt, or not supporting `NDEF`)

### MQTT status
nfc2mqtt will use MQTT last will/birth message.

When it connects to MQTT broker, it will publish `1` to `nfc2mqtt/online`.
When nfc2mqtt will be disconnected, `nfc2mqtt/online` will be set to `0`.

### Hardware
I own one NFC reader (`ACR122U`), so all development is done on it.

Tags **NOT** supported by nfc2mqtt:
* All Mifare cards - nfcpy is not able to write on those tags (probably because of missing CRYPTO1 support)
* NTAG210 - expose just 48 bytes for user data, its too small for encryption

Tags supported by nfc2mqtt:
* NTAG212 - **NOT TESTED** but should work
* NTAG213 - works
* NTAG215 - **NOT TESTED** but should work
* NTAG216 - works (preferable choice, as they expose 888 user data bytes)

### Config
Before first run you should change `authenticate_password` and `encrypt_key`. New keys can be generated with [fernet token](#generate-fernet-token).

**Ensure that `encrypt_key` is different than `authenticate_password`.**

```yaml
nfc:
  reader: usb
  authenticate_password: pa2SB6ZC8NUFzX1IXBbA7OF9xj5cTrdAImkx3t9i0Fw=
  encrypt_key: Wv_o4fUMFrPFZv0Es02f361nW_kdpFLdXdTo7e7jo0c=
  id_length: 5
mqtt:
  server: localhost
  port: 1883
  keepalive: 30
  username: nfc2mqtt
  password: password
  topic: nfc2mqtt
logging:
  level: info
```

#### nfc
* reader - `nfcpy` readder path
* authenticate_password - password used to `authenticate` and `protect`. If you change that, you will need to rewrite **ALL** tags. For `write_tag` MQTT endpoint please provide old `authenticate_password`. It can be generated with [fernet token](#generate-fernet-token).
* encrypt_key - Fernet token used to encrypt tag content. If you change that, nfc2mqtt will not be able to decrypt tags with previous `encrypt_key`. You will need to rewrite **ALL** tags. This can be helpfull if you lost tag with `valid_till: 0` . It can be generated with [fernet token](#generate-fernet-token).

### Security
All tags "created" by nfc2mqtt are protected from reading on NFC tag level. `authenticate_password` is used for that.
Tag probably still can be cloned and readed, but all data stored physicaly on tag is encrypted with [symmetric cipher](https://cryptography.io/en/latest/fernet/) and secure.

#### What does it mean
You should assume that any tag lost or passed to stranger can be cloned and used in malicious way.
Attacker will not be able to read decrypted content of yours NFC tag (`tag_id`, `valid_till`, `data`). Also attacker will not be able to change NFC tag content (he would need to know `encrypt_key`).

So if you give yours petsitter NFC tag, with `valid_till` set to ex. `utcnow()` + `1 week`, this tag will work only for `1 week`, not longer.

If you lost NFC tag with `valid_till: 0`, you should change `encrypt_key` in nfc2mqtt and rewrite all trusted tags with new `encrypt_key`.

Tags should be treated as physcial lock keys. If you lost tag for 2h (in the wild, not in yours apartment), you should assume that tag is copromised, and you should change `encrypt_key`.

### Generate fernet token
```
$ python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'
```

### Worth reading
* https://docs.onion.io/omega2-docs/using-rfid-nfc-expansion.html
* https://nfcpy.readthedocs.io/en/latest/overview.html
* https://pcsclite.apdu.fr/
* https://www.blackhat.com/docs/sp-14/materials/arsenal/sp-14-Almeida-Hacking-MIFARE-Classic-Cards-Slides.pdf
* http://nfc-tools.org/index.php
