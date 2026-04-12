from django.test import SimpleTestCase

from system.services.legacy_markers import extract_legacy_meta, strip_legacy_meta, upsert_legacy_meta


class LegacyMarkersTests(SimpleTestCase):
    def test_upsert_and_extract_legacy_meta(self):
        text = "Observacao original"
        payload = {"source": "legacy", "imported": True, "status": "problem", "issues": ["CPF ausente"]}

        with_marker = upsert_legacy_meta(text, payload)

        extracted = extract_legacy_meta(with_marker)
        self.assertEqual(extracted["source"], "legacy")
        self.assertTrue(extracted["imported"])
        self.assertEqual(extracted["status"], "problem")
        self.assertEqual(extracted["issues"], ["CPF ausente"])

    def test_strip_legacy_meta_preserves_user_notes(self):
        payload = {"source": "legacy", "imported": True, "status": "ok", "issues": []}
        text = "Linha 1\nLinha 2"
        with_marker = upsert_legacy_meta(text, payload)

        self.assertEqual(strip_legacy_meta(with_marker), text)
