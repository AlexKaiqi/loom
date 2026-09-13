"""Mandatory independent-observer negative controls; never substitute a fake E."""
import asyncio
import json
import os
from pathlib import Path
import unittest
from receipt_preparation import run
class ReceiptPreparation(unittest.IsolatedAsyncioTestCase):
    async def test_actual_facility_and_full_binding(self):
        root=os.environ.get("LORE_E_EVIDENCE_DIR")
        self.assertTrue(root,"explicit evidence directory required")
        result=await asyncio.wait_for(run(Path(root)/"receipt-authority-controls"),40)
        self.assertEqual(result["status"],"PREPARATION_PASS",result["errors"])
        ids=[check["id"] for check in result["checks"]]
        expected=json.loads((Path(__file__).parent/"receipt-preparation-protocol.json").read_text())["required_check_ids"]
        self.assertEqual(len(ids),29);self.assertEqual(set(ids),set(expected))
        self.assertTrue(all(check["passed"] is True for check in result["checks"]))
