import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from common.exceptions import ConflictError
from missions.services import join_file_transfer
from transfers.models import FileTransfer
from transfers.services import cleanup_transfers, create_transfer

SHA = hashlib.sha256(b"hello").hexdigest()
SDP = "v=0\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n"


class TransferTests(TestCase):
    def setUp(self):
        self.sender = User.objects.create_user("sender", password="pw")
        self.receiver = User.objects.create_user("receiver", password="pw")
        self.other = User.objects.create_user("other", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.sender)
        self.payload = {"name": "hello.txt", "size": 5, "sha256": SHA, "token": "a" * 64}

    def create(self):
        response = self.client.post("/api/file-transfers/", self.payload, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.session = response.json()
        self.url = f"/api/file-transfers/{self.session['id']}/"
        return response

    def op(self, action="poll", token="b" * 64, **kwargs):
        return self.client.post(self.url, {"action": action, "token": token, **kwargs}, format="json")

    def join(self, user=None):
        self.client.force_authenticate(user or self.receiver)
        return self.client.post("/api/file-transfers/join/", {"code": self.session["code"], "token": "b" * 64}, format="json")

    def ready(self):
        self.create()
        self.assertEqual(self.join().status_code, 200)
        self.assertEqual(self.op("accept").json()["status"], "accepted")
        self.client.force_authenticate(self.sender)
        self.assertEqual(self.op("offer", token="a" * 64, sdp=SDP).status_code, 200)
        self.client.force_authenticate(self.receiver)
        self.assertEqual(self.op("answer", sdp=SDP).status_code, 200)

    def test_verified_completion_and_no_file_storage(self):
        self.ready()
        result = self.op("complete", sha256=SHA)
        self.assertEqual(result.json()["status"], "completed")
        record = FileTransfer.objects.get()
        self.assertEqual(record.received_sha256, SHA)
        self.assertEqual(record.offer, "")
        self.assertEqual(record.answer, "")
        self.assertNotEqual(record.sender_token, "a" * 64)
        self.assertNotEqual(record.code_digest, self.session["code"])
        self.assertEqual(self.op("complete", sha256=SHA).json()["status"], "completed")
        self.assertEqual(self.op("cancel").json()["status"], "completed")
        self.client.force_authenticate(self.sender)
        self.assertEqual(self.op(token="a" * 64).json()["received_sha256"], SHA)

    def test_checksum_mismatch_fails(self):
        self.ready()
        result = self.op("complete", sha256="0" * 64).json()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "checksum_mismatch")

    def test_same_account_requires_distinct_page_token(self):
        self.create()
        self.assertEqual(self.join(self.sender).status_code, 200)
        self.assertEqual(self.op().json()["role"], "receiver")
        self.assertEqual(self.op(token="a" * 64).json()["role"], "sender")
        self.assertEqual(self.op("accept", token="a" * 64).status_code, 409)
        self.assertEqual(self.op("accept").status_code, 200)

    def test_no_access_without_both_identity_and_token(self):
        self.create()
        self.assertEqual(self.op().status_code, 403)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.op(token="a" * 64).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.op(token="a" * 64).status_code, 403)
        self.assertEqual(self.client.post("/api/file-transfers/", self.payload, format="json").status_code, 403)

    def test_pairing_is_exclusive_and_retry_idempotent(self):
        self.create()
        self.assertEqual(self.join().status_code, 200)
        self.assertEqual(self.join().status_code, 200)
        self.assertEqual(self.join(self.other).status_code, 409)

    def test_accept_required_and_role_restrictions(self):
        self.create()
        self.assertEqual(self.op("offer", token="a" * 64, sdp=SDP).status_code, 409)
        self.join()
        self.assertEqual(self.op("answer", sdp=SDP).status_code, 409)
        self.op("accept")
        self.assertEqual(self.op("offer", sdp=SDP).status_code, 409)
        self.assertEqual(self.op("complete", sha256=SHA).status_code, 409)

    def test_sdp_limits_and_immutable_signaling(self):
        self.ready()
        self.assertEqual(self.op("answer", sdp=SDP).status_code, 200)
        self.assertEqual(self.op("answer", sdp=SDP + "a=changed\r\n").status_code, 409)
        self.assertEqual(self.op("answer", sdp="x" * 17000).status_code, 400)
        self.assertEqual(self.op("answer", sdp=SDP + "m=audio 9\r\n").status_code, 400)

    def test_cancel_and_failure_are_terminal(self):
        self.ready()
        self.assertEqual(self.op("cancel").json()["status"], "cancelled")
        self.assertEqual(self.op("complete", sha256=SHA).json()["status"], "cancelled")
        self.assertEqual(FileTransfer.objects.get().offer, "")

    def test_expiry_and_cleanup(self):
        self.create()
        FileTransfer.objects.update(pair_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.op(token="a" * 64).json()["status"], "expired")
        self.assertEqual(self.join().status_code, 409)
        FileTransfer.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(cleanup_transfers(), 1)
        self.assertFalse(FileTransfer.objects.exists())

    def test_inactive_peer_cancels(self):
        self.ready()
        self.sender.is_active = False
        self.sender.save()
        self.assertEqual(self.op().json()["status"], "cancelled")

    def test_validation_and_capacity(self):
        for changes in [{"size": 100 * 1024 * 1024 + 1}, {"sha256": "invalid"}, {"name": "../escape"}, {"file": "bytes"}]:
            response = self.client.post("/api/file-transfers/", {**self.payload, **changes}, format="json")
            self.assertEqual(response.status_code, 400, response.content)
        for _ in range(3):
            self.create()
        self.assertEqual(self.client.post("/api/file-transfers/", self.payload, format="json").status_code, 409)

    def test_csrf_required_even_with_page_token(self):
        self.create()
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.sender)
        self.assertEqual(client.post(self.url, {"token": "a" * 64}, format="json").status_code, 403)


class TransferConcurrencyTests(TransactionTestCase):
    def test_only_one_receiver_can_claim_code(self):
        sender = User.objects.create_user("sender")
        receivers = [User.objects.create_user(f"receiver{i}") for i in range(2)]
        session = create_transfer(actor=sender, name="hello", size=5, sha256=SHA, token="a" * 64)
        barrier = Barrier(2)

        def join(index):
            close_old_connections()
            try:
                actor = User.objects.get(pk=receivers[index].pk)
                barrier.wait(timeout=10)
                try:
                    join_file_transfer(actor=actor, code=session["code"], token=str(index) * 64)
                    return "joined"
                except ConflictError:
                    return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(join, range(2)))
        self.assertCountEqual(results, ["joined", "conflict"])
