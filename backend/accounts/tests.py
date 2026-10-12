from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import RegistrationRequest, RegistrationStatus, User

REGISTER_URL = "/api/auth/register/"
STRONG_PASSWORD = "Str0ngPass!23"


class RegistrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=False)
        self.admin = User.objects.create_user("admin", password="pw", is_staff=True)

    def register(self, **overrides):
        payload = {
            "username": "newbie",
            "password": STRONG_PASSWORD,
            "email": "newbie@example.com",
            "display_name": "New Bie",
        }
        payload.update(overrides)
        return self.client.post(REGISTER_URL, payload, format="json")

    def test_register_creates_pending_request_without_creating_user(self):
        response = self.register()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], RegistrationStatus.PENDING)
        self.assertNotIn("password", response.json())
        self.assertNotIn("password_hash", response.json())
        self.assertFalse(User.objects.filter(username="newbie").exists())
        self.assertTrue(
            RegistrationRequest.objects.filter(
                username="newbie", status=RegistrationStatus.PENDING
            ).exists()
        )

    def test_register_rejects_existing_username(self):
        User.objects.create_user("taken", password="pw")

        response = self.register(username="taken")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "username_taken")

    def test_register_rejects_second_pending_request_for_same_username(self):
        self.register()

        response = self.register(email="other@example.com")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "registration_pending")

    def test_register_rejects_weak_password(self):
        response = self.register(password="123")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_admin_approve_creates_active_user_who_can_log_in(self):
        self.register()
        registration = RegistrationRequest.objects.get()

        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/admin/registrations/{registration.id}/approve/", {}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], RegistrationStatus.APPROVED)
        user = User.objects.get(username="newbie")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(STRONG_PASSWORD))

        fresh = APIClient(enforce_csrf_checks=False)
        login = fresh.post(
            "/api/auth/login/",
            {"username": "newbie", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertFalse(login.json()["is_staff"])

    def test_approve_is_single_shot(self):
        self.register()
        registration = RegistrationRequest.objects.get()
        self.client.force_authenticate(self.admin)

        first = self.client.post(
            f"/api/admin/registrations/{registration.id}/approve/", {}, format="json"
        )
        second = self.client.post(
            f"/api/admin/registrations/{registration.id}/approve/", {}, format="json"
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "registration_already_reviewed")

    def test_admin_reject_records_note_and_creates_no_user(self):
        self.register()
        registration = RegistrationRequest.objects.get()

        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/admin/registrations/{registration.id}/reject/",
            {"note": "资料不完整"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], RegistrationStatus.REJECTED)
        self.assertEqual(response.json()["review_note"], "资料不完整")
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_list_can_filter_by_status(self):
        self.register(username="pending_one")
        approved = self.register(username="pending_two")
        registration = RegistrationRequest.objects.get(username="pending_two")
        self.client.force_authenticate(self.admin)
        self.client.post(
            f"/api/admin/registrations/{registration.id}/approve/", {}, format="json"
        )
        self.assertEqual(approved.status_code, 201)

        listing = self.client.get("/api/admin/registrations/?status=Pending")

        self.assertEqual(listing.status_code, 200)
        usernames = [row["username"] for row in listing.json()["results"]]
        self.assertEqual(usernames, ["pending_one"])


class AdminApiPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=False)
        self.member = User.objects.create_user("member", password="pw")

    def test_anonymous_cannot_access_admin_api(self):
        self.assertEqual(self.client.get("/api/admin/registrations/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/users/").status_code, 403)

    def test_non_staff_cannot_access_admin_api(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get("/api/admin/registrations/").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/users/").status_code, 403)

    def test_me_exposes_is_staff_flag(self):
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_staff"])

    def test_admin_can_list_members(self):
        admin = User.objects.create_user("admin", password="pw", is_staff=True)
        self.client.force_authenticate(admin)
        response = self.client.get("/api/admin/users/")
        self.assertEqual(response.status_code, 200)
        usernames = {row["username"] for row in response.json()["results"]}
        self.assertEqual(usernames, {"admin", "member"})


class MemberListApiTests(TestCase):
    """``GET /api/members/`` powers the reviewer picker for any team member."""

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=False)
        self.member = User.objects.create_user("member", password="pw")

    def test_anonymous_is_rejected(self):
        self.assertIn(self.client.get("/api/members/").status_code, (401, 403))

    def test_member_lists_only_active_members_without_sensitive_fields(self):
        User.objects.create_user("alice", password="pw", first_name="Alice")
        ghost = User.objects.create_user("ghost", password="pw")
        ghost.is_active = False
        ghost.save(update_fields=["is_active"])

        self.client.force_authenticate(self.member)
        response = self.client.get("/api/members/")

        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual([row["username"] for row in rows], ["alice", "member"])
        self.assertEqual(set(rows[0]), {"id", "username", "display_name"})
        self.assertEqual(rows[0]["display_name"], "Alice")
