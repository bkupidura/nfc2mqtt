import logging
import sys
import signal
import time
import json

from threading import Event
from datetime import datetime
from enum import Enum

import nfc

from ndef import TextRecord
from argparse import ArgumentParser
from cryptography.fernet import Fernet, InvalidToken

from nfc2mqtt import utils
from nfc2mqtt import mqtt

class TagStatus(int, Enum):
    # Tag is valid and can be trusted
    Valid = 1
    # Tag is invalid (unable to decrypt content or invalid content)
    Invalid = 2
    # Tag was readed and decrypted, but contains not supported payload
    UnknownPayloadType = 3
    # Tag was readed and decrypted, but it expired
    Expired = 4
    # We were not able to scan tag (ex. too fast removed from reader or wrong authentication password)
    ScanError = 5
    # Tag dosent contain ndef used to store content
    NoNdef = 6


class Service(mqtt.Mqtt):
    def __init__(self, **args):
        super(Service, self).__init__()

        args_mqtt = args.get('mqtt', dict())
        args_nfc = args.get('nfc', dict())

        assert args_nfc.get('encrypt_key') is not None, 'Config nfc.encrypt_key must be set'

        self.mqtt_config = {
            'server': args_mqtt.get('server', 'localhost'),
            'port': args_mqtt.get('port', 1883),
            'keepalive': args_mqtt.get('keepalive', 60),
            'username': args_mqtt.get('username', None),
            'password': args_mqtt.get('password', None),
            'topic': args_mqtt.get('topic', 'nfc2mqtt')
        }
        self.nfc_config = {
            'authenticate_password': args_nfc.get('authenticate_password', None),
            'encrypt_key': args_nfc['encrypt_key'],
            'id_length': args_nfc.get('id_length', 5),
            'reader': args_nfc.get('reader', 'usb')
        }

        self.nfc_cf = nfc.ContactlessFrontend(self.nfc_config['reader'])
        self.write_tag_queue = list()

        write_topic = '{}/write_tag'.format(self.mqtt_config['topic'])
        wipe_topic = '{}/wipe_tag'.format(self.mqtt_config['topic'])

        self.connect(subscribe_to=[write_topic, wipe_topic])

        self.mqtt.message_callback_add(write_topic, self._on_write_tag_message)
        self.mqtt.message_callback_add(wipe_topic, self._on_wipe_tag_message)

    def _encrypt(self, data):
        f = Fernet(self.nfc_config['encrypt_key'])
        return f.encrypt(data)

    def _decrypt(self, token):
        f = Fernet(self.nfc_config['encrypt_key'])
        return f.decrypt(token)

    def _on_wipe_tag_message(self, client, userdata, msg):
        write_tag_payload = {
            'action': 'wipe'
        }
        LOG.info('Adding new payload %s to write tag queue', write_tag_payload)
        self.write_tag_queue.append(write_tag_payload)

    def _on_write_tag_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except json.decoder.JSONDecodeError:
            payload = dict()

        authenticate_password = payload.get('authenticate_password')

        if payload.get('data') is not None:
            payload['data'] = json.dumps(payload['data'])

        tag_payload = {
            'id': payload.get('id', utils.gen_random_string(length=self.nfc_config['id_length'])),
            'valid_till': payload.get('valid_till', 0),
            'data': payload.get('data')
        }

        write_tag_paylod = {
            'tag_payload': tag_payload,
            'action': 'write',
            'authenticate_password': authenticate_password
        }
        
        LOG.info('Adding new payload %s to write tag queue', write_tag_paylod)
        self.write_tag_queue.append(write_tag_paylod)

    def _wipe_tag(self, tag):
        LOG.info('Wiping tag')

        if self.nfc_config['authenticate_password'] is not None:
            try:
                if tag.authenticate(bytes(self.nfc_config['authenticate_password'], 'ascii')) is False:
                    LOG.warning('Unable to authenticate')
                    return False
            except (nfc.tag.tt2.Type2TagCommandError, ValueError, IndexError) as e:
                LOG.warning('Unable to authenticate: %s', e)
                return False

        try:
            if tag.format(wipe=255) is False:
                LOG.warning('Unable to format tag')
                return False
        except nfc.tag.tt2.Type2TagCommandError:
             LOG.warning('Unable to format tag')
             return False

        LOG.info('Tag wiped successfuly')
        return True

    def _write_tag(self, tag, payload, authenticate_password):
        LOG.info('Writing to tag %s', payload)

        if authenticate_password is not None:
            try:
                if tag.authenticate(bytes(authenticate_password, 'ascii')) is False:
                    LOG.warning('Authenticate password provided, but unable to authenticate')
                    return False
            except (nfc.tag.tt2.Type2TagCommandError, ValueError, IndexError) as e:
                LOG.warning('Authenticate password provided, but unable to authenticate: %s', e)
                return False
        
        if self.nfc_config['authenticate_password'] is not None:
            try:
                tag.protect(bytes(self.nfc_config['authenticate_password'], 'ascii'), read_protect=True)
            except nfc.tag.tt2.Type2TagCommandError:
                # Already protected?
                pass

        if self._wipe_tag(tag) is False:
            return False

        if tag.ndef is not None:
            try:
                if payload['data'] is not None:
                    payload_formatted = '{id} {valid_till} {data}'.format(**payload)
                else:
                    payload_formatted = '{id} {valid_till}'.format(**payload)

                encrypted_payload = self._encrypt(bytes(payload_formatted, 'utf-8'))
                LOG.info('Plain text length %d, encrypted text length %d', len(payload_formatted), len(encrypted_payload))
                tag.ndef.records = [TextRecord(encrypted_payload)]
            except ValueError:
                LOG.warning('Unable to write content, too long?')
                return False
        else:
            LOG.warning('Tag dosent have ndef after format')
            return False

        LOG.info('Tag written successfuly')
        return True

    def _process_tag(self, tag):
        if len(self.write_tag_queue) > 0:
            payload = self.write_tag_queue.pop(0)
            status = False
            if payload['action'] == 'write':
                status = self._write_tag(tag, payload['tag_payload'], payload['authenticate_password'])
            elif payload['action'] == 'wipe':
                status = self._wipe_tag(tag)
            if status is True:
                self.beep(times=1)
            else:
                self.beep(times=5)
            return False

        tag.n2m = {
            'status': TagStatus.ScanError,
            'tag': {
                'product': tag.product,
                'type': tag.type,
                'id': tag.identifier.hex()
            }
        }

        if self.nfc_config['authenticate_password'] is not None:
            if tag.authenticate(bytes(self.nfc_config['authenticate_password'], 'ascii')) is False:
                return False

        if tag.ndef is None:
            tag.n2m['status'] = TagStatus.NoNdef
            return False

        try:
            payload_encrypted = tag.ndef.records[0]
        except IndexError:
            return False
         
        try:
            payload = self._decrypt(bytes(payload_encrypted.text, 'utf-8'))
        except InvalidToken:
            tag.n2m['status'] = TagStatus.Invalid
            return False

        payload_array = payload.decode().split(' ', 2)

        if len(payload_array) not in [2, 3]:
            tag.n2m['status'] = TagStatus.UnknownPayloadType
            return False

        try:
            tag.n2m['id'] = payload_array[0]
            tag.n2m['valid_till'] = int(payload_array[1])
            if len(payload_array) == 3:
                data = payload_array[2]
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.decoder.JSONDecodeError:
                        pass
                tag.n2m['data'] = data
        except ValueError:
            LOG.warning('Unable to parse tag payload: %s', payload_array)
            tag.n2m['status'] = TagStatus.UnknownPayloadType
            return False

        tag.n2m['status'] = TagStatus.Valid
        now = datetime.utcnow()

        if tag.n2m['valid_till'] != 0:
            valid_till_dt = datetime.utcfromtimestamp(tag.n2m['valid_till'])
            tag.n2m['valid_till_dt_utc'] = str(valid_till_dt)
            if (valid_till_dt - now).total_seconds() <= 0:
                tag.n2m['status'] = TagStatus.Expired

        return False

    def beep(self, times=1, sleep=3):
        for _ in range(times):
            self.nfc_cf.device.turn_on_led_and_buzzer()
            time.sleep(0.1)
        time.sleep(sleep)
        self.nfc_cf.device.turn_off_led_and_buzzer()

    def log_and_beep(self, logger_func, message, times=1, sleep=3):
        logger_func(message)
        self.beep(times=times, sleep=sleep)

    def run(self):
        LOG.info('Starting')
        self.loop_start()
        while True:
            self.resend_publish_queue()

            now = time.time()
            terminate = lambda: time.time() - now > 2

            tag = self.nfc_cf.connect(rdwr={'on-connect': self._process_tag, 'beep-on-connect': False}, terminate=terminate)
            if tag is None or not hasattr(tag, 'n2m'):
                continue

            if tag.n2m.get('id') is not None:
                tag_topic = '{}/tag/{}'.format(self.mqtt_config['topic'], tag.n2m['id'])
            else:
                tag_topic = '{}/tag'.format(self.mqtt_config['topic'])

            if tag.n2m['status'] == TagStatus.Valid:
                self.publish(tag_topic, tag.n2m)
                self.log_and_beep(LOG.info, 'Valid tag scanned {}'.format(tag.n2m), times=1, sleep=5)
            elif tag.n2m['status'] == TagStatus.ScanError:
                self.log_and_beep(LOG.info, 'Unable to scan tag', times=2, sleep=3)
            elif tag.n2m['status'] == TagStatus.NoNdef:
                self.log_and_beep(LOG.info, 'No ndef on tag, try to format tag', times=2, sleep=3)
            elif tag.n2m['status'] == TagStatus.Invalid:
                self.log_and_beep(LOG.info, 'Invalid tag scanned, try to format tag', times=3, sleep=5)
            elif tag.n2m['status'] == TagStatus.UnknownPayloadType:
                self.log_and_beep(LOG.info, 'Unknown payload type', times=3, sleep=5)
            elif tag.n2m['status'] == TagStatus.Expired:
                self.log_and_beep(LOG.info, 'Expired tag scanned {}'.format(tag.n2m), times=3, sleep=5)


LOG = logging.getLogger(__name__)
logging.getLogger('nfc.clf').setLevel(logging.CRITICAL)
logging.getLogger('nfc.tag').setLevel(logging.CRITICAL)

signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))

def main():
    parser = ArgumentParser(description='nfc2mqtt reads NFC tags and push them to MQTT')
    parser.add_argument('--config', '-c', required=True, help='config file path')
    args = parser.parse_args()

    config = utils.load_config(args.config)

    utils.create_logger(config.get('logging', dict()))

    service = Service(**config)
    service.run()

if __name__ == '__main__':
    main()
