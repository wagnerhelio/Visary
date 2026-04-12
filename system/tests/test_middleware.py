from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from system.middleware import VisaryRequestMiddleware


class VisaryRequestMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_sets_flags_when_session_empty(self):
        captured = {}

        def capture(req):
            captured["request"] = req
            return HttpResponse()

        middleware = VisaryRequestMiddleware(capture)
        request = self.factory.get("/")
        request.session = {}
        middleware(request)
        req = captured["request"]
        self.assertIsNone(req.visary_client_id)
        self.assertIsNone(req.visary_partner_id)
        self.assertFalse(req.visary_is_client_area)
        self.assertFalse(req.visary_is_partner_area)

    def test_sets_flags_from_session(self):
        captured = {}

        def capture(req):
            captured["request"] = req
            return HttpResponse()

        middleware = VisaryRequestMiddleware(capture)
        request = self.factory.get("/")
        request.session = {"client_id": 5, "partner_id": 9}
        middleware(request)
        req = captured["request"]
        self.assertEqual(req.visary_client_id, 5)
        self.assertEqual(req.visary_partner_id, 9)
        self.assertTrue(req.visary_is_client_area)
        self.assertTrue(req.visary_is_partner_area)
