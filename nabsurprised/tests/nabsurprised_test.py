import datetime
import json
import unittest

import pytest
from asgiref.sync import async_to_sync

from nabd.tests.mock import MockWriter, NabdMockTestCase
from nabd.tests.utils import close_old_async_connections
from nabsurprised.nabsurprised import NabSurprised


class TestNativeSurpriseResponse(unittest.IsolatedAsyncioTestCase):
    async def test_voice_goes_straight_to_the_requested_audio(self):
        for kind in ("surprise", "autopromo", "carrot", "birthday"):
            with self.subTest(kind=kind):
                service = NabSurprised()
                service.writer = MockWriter()
                await service.process_nabd_packet(
                    {
                        "type": "asr_event",
                        "nlu": {"intent": f"nabsurprised/{kind}"},
                    }
                )
                self.assertEqual(len(service.writer.written), 1)
                packet = json.loads(service.writer.written[0])
                self.assertNotIn("signature", packet)
                directory = "" if kind == "surprise" else kind + "/"
                self.assertEqual(
                    packet["body"],
                    [{"audio": [f"nabsurprised/{directory}*.mp3"]}],
                )

    async def test_scheduled_response_keeps_its_signature(self):
        service = NabSurprised()
        service.writer = MockWriter()
        await service.perform(datetime.datetime(2018, 11, 1), None, None)
        packet = json.loads(service.writer.written[0])
        self.assertEqual(
            packet["signature"],
            {"audio": ["nabsurprised/respirations/*.mp3"]},
        )

    async def test_rfid_response_keeps_its_signature(self):
        service = NabSurprised()
        service.writer = MockWriter()
        await service.process_nabd_packet(
            {
                "type": "rfid_event",
                "event": "detected",
                "app": "nabsurprised",
                "data": "\x00\x01",
            }
        )
        packet = json.loads(service.writer.written[0])
        self.assertEqual(
            packet["signature"],
            {"audio": ["nabsurprised/respirations/*.mp3"]},
        )


@pytest.mark.django_db
class TestNabSurprised(unittest.TestCase):
    def tearDown(self):
        close_old_async_connections()

    def test_perform(self):
        service = NabSurprised()
        writer = MockWriter()
        service.writer = writer
        expiration = datetime.datetime(2018, 11, 1, 0, 0, 0)
        async_to_sync(service.perform)(expiration, None, None)
        self.assertEqual(len(writer.written), 1)
        packet = writer.written[0]
        packet_json = json.loads(packet.decode("utf8"))
        self.assertEqual(packet_json["type"], "message")
        self.assertTrue("signature" in packet_json)
        self.assertTrue("body" in packet_json)


@pytest.mark.django_db
class TestRfid(unittest.TestCase):
    def tearDown(self):
        close_old_async_connections()

    def test_detect_language(self):
        service = NabSurprised()
        writer = MockWriter()
        service.writer = writer
        nabd_packet = {
            "type": "rfid_event",
            "uid": "d0:02:1a:01:02:03:04:05",
            "event": "detected",
            "support": "formatted",
            "picture": 21,
            "app": "nabsurprised",
            "data": "\x07\x00",
        }
        async_to_sync(service.process_nabd_packet)(nabd_packet)
        self.assertEqual(len(writer.written), 1)
        packet = writer.written[0]
        packet_json = json.loads(packet.decode("utf8"))
        self.assertEqual(packet_json["type"], "message")
        self.assertTrue("signature" in packet_json)
        self.assertTrue("body" in packet_json)
        self.assertEqual(len(packet_json["body"]), 1)
        self.assertTrue("audio" in packet_json["body"][0])
        self.assertEqual(len(packet_json["body"][0]["audio"]), 1)
        self.assertEqual(
            packet_json["body"][0]["audio"][0], "ja_JP/nabsurprised/*.mp3"
        )

    def test_detect_surprise(self):
        service = NabSurprised()
        writer = MockWriter()
        service.writer = writer
        nabd_packet = {
            "type": "rfid_event",
            "uid": "d0:02:1a:01:02:03:04:05",
            "event": "detected",
            "support": "formatted",
            "picture": 21,
            "app": "nabsurprised",
            "data": "\x00\x01",
        }
        async_to_sync(service.process_nabd_packet)(nabd_packet)
        self.assertEqual(len(writer.written), 1)
        packet = writer.written[0]
        packet_json = json.loads(packet.decode("utf8"))
        self.assertEqual(packet_json["type"], "message")
        self.assertTrue("signature" in packet_json)
        self.assertTrue("body" in packet_json)
        self.assertEqual(len(packet_json["body"]), 1)
        self.assertTrue("audio" in packet_json["body"][0])
        self.assertEqual(len(packet_json["body"][0]["audio"]), 1)
        self.assertEqual(
            packet_json["body"][0]["audio"][0], "nabsurprised/carrot/*.mp3"
        )


@pytest.mark.django_db
class TestNabSurprisedRun(NabdMockTestCase):
    def tearDown(self):
        NabdMockTestCase.tearDown(self)
        close_old_async_connections()

    def test_connect(self):
        self.do_test_connect(NabSurprised)
