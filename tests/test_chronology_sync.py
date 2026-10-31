import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sync_chronology import read_source_directory, sync


EXAMPLE = """<?xml version="1.0"?>
<content>
 <header level="0" type="chapter" name="3900"><p>Visible human chronology remains unchanged</p></header>
 <chronology_data version="1" calendar="AM">
  <events>
   <event id="one" label="First event" kind="birth" subject="A"/>
   <event id="two" label="Second event" kind="death" subject="B"/>
  </events>
  <claims>
   <claim id="date-one" kind="source-claim" event_id="one" year_min="-3" year_max="5" title="Dated event" status="needs-verification">
    <source author="Author" work="Book" location="Chapter" url="https://github.com/example/source"><review>Uncertain</review></source>
   </claim>
   <claim id="age-one" kind="source-claim" event_id="two" metric="age_at_accession" value="47" title="Age" status="quoted">
    <source author="Author" work="Book" location="Chapter" url="https://github.com/example/source"/>
   </claim>
  </claims>
  <constraints>
   <constraint id="link" kind="reported-relation" lhs_event="two" rhs_event="one" relation="same-year" delta_years="0" label="same" default_active="false" status="unproven">
    <evidence work="Book" url="https://github.com/example/source" review="Not verified"/>
   </constraint>
  </constraints>
  <derived_examples>
   <example id="computed" kind="computed-example" base_claim_id="date-one" age_claim_id="age-one" status="arithmetic-example"/>
  </derived_examples>
 </chronology_data>
</content>"""


class ChronologySyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "sources"
        self.output = Path(self.tmp.name) / "data"
        self.source.mkdir()
        (self.source / "0000.xml").write_text(EXAMPLE, encoding="utf-8")
        (self.source / "info.xml").write_text("<info/>", encoding="utf-8")
        (self.source / "9000.xml").write_text("<content/>", encoding="utf-8")

    def test_collects_every_xml_file_and_preserves_human_content(self):
        before = (self.source / "0000.xml").read_bytes()
        result = read_source_directory(self.source)
        self.assertEqual(len(result["events.json"]["events"]), 2)
        self.assertEqual(result["claims.json"]["claims"][1]["year"], {"min": -3, "max": 5})
        self.assertFalse(result["constraints.json"]["constraints"][0]["defaultActive"])
        self.assertEqual(before, (self.source / "0000.xml").read_bytes())

    def test_idempotence_and_check(self):
        self.assertEqual(sync(self.source, self.output, check=True), ["claims.json", "constraints.json", "events.json"])
        self.assertEqual(sync(self.source, self.output, check=False), ["claims.json", "constraints.json", "events.json"])
        self.assertEqual(sync(self.source, self.output, check=True), [])
        self.assertEqual(sync(self.source, self.output, check=False), [])

    def test_second_file_is_included(self):
        other = EXAMPLE.replace('id="one"', 'id="three"').replace('id="two"', 'id="four"')
        other = other.replace('id="date-one"', 'id="date-three"').replace('id="age-one"', 'id="age-three"').replace('id="link"', 'id="link-three"').replace('id="computed"', 'id="computed-three"')
        other = other.replace('event_id="one"', 'event_id="three"').replace('event_id="two"', 'event_id="four"')
        other = other.replace('lhs_event="two"', 'lhs_event="four"').replace('rhs_event="one"', 'rhs_event="three"')
        other = other.replace('base_claim_id="date-one"', 'base_claim_id="date-three"').replace('age_claim_id="age-one"', 'age_claim_id="age-three"')
        (self.source / "9000.xml").write_text(other, encoding="utf-8")
        result = read_source_directory(self.source)
        self.assertEqual(len(result["events.json"]["events"]), 4)

    def test_duplicate_identifier_fails_without_overwriting_existing_json(self):
        sync(self.source, self.output, check=False)
        old = (self.output / "events.json").read_bytes()
        (self.source / "9000.xml").write_text(EXAMPLE, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sync(self.source, self.output, check=False)
        self.assertEqual((self.output / "events.json").read_bytes(), old)

    def test_invalid_relation_or_source_fails(self):
        text = EXAMPLE.replace('relation="same-year"', 'relation="later-than"')
        (self.source / "0000.xml").write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported relation"):
            read_source_directory(self.source)
        text = EXAMPLE.replace('https://github.com/example/source', 'javascript:alert(1)')
        (self.source / "0000.xml").write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "https"):
            read_source_directory(self.source)

    def test_missing_machine_data_cannot_erase_site(self):
        (self.source / "0000.xml").write_text("<content><p>text only</p></content>", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "No <chronology_data>"):
            sync(self.source, self.output, check=False)


if __name__ == "__main__":
    unittest.main()
