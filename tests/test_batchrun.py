"""The batch coordinator, flown against a paper sky: transport stubbed, logic real."""

import json
import threading
import unittest
from unittest import mock

from sanzaru import batchrun
from sanzaru.batchrun import BatchCoordinator


def paper_sky(fail_first_for=None):
    """Stub transport: every batch completes instantly and echoes its prompt."""
    state = {"uploads": {}, "batches": 0, "failed_once": set()}

    def upload(lines, key):
        fid = f"file-{len(state['uploads'])}"
        state["uploads"][fid] = [json.loads(l) for l in lines]
        return fid

    def api(path, key, data=None, content_type=None):
        if path == "/batches":
            state["batches"] += 1
            fid = json.loads(data)["input_file_id"]
            return {"id": f"batch-{fid}", "status": "completed",
                    "output_file_id": f"out-{fid}"}
        if path.startswith("/batches/"):
            raise AssertionError("completed on create; no polling expected")
        raise AssertionError(path)

    def api_raw(path, key):
        fid = path.split("/files/out-")[1].split("/content")[0]
        rows = []
        for item in state["uploads"][fid]:
            content = item["body"]["messages"][-1]["content"]
            cid = item["custom_id"]
            if fail_first_for and content == fail_first_for and content not in state["failed_once"]:
                state["failed_once"].add(content)
                rows.append(json.dumps({"custom_id": cid,
                                        "response": {"status_code": 500},
                                        "error": {"message": "rain"}}))
            else:
                rows.append(json.dumps({"custom_id": cid, "response": {
                    "status_code": 200,
                    "body": {"choices": [{"message": {"content": f"echo {content}"}}]}}}))
        return "\n".join(rows).encode()

    return upload, api, api_raw, state


class BatchCoordinatorTests(unittest.TestCase):
    def _fly(self, fail_first_for=None, asks=6):
        upload, api, api_raw, state = paper_sky(fail_first_for)
        with mock.patch.object(batchrun, "_upload_jsonl", upload), \
             mock.patch.object(batchrun, "_api", api), \
             mock.patch.object(batchrun, "_api_raw", api_raw):
            coordinator = BatchCoordinator("k", gather_seconds=0.1,
                                           poll_seconds=0.01, log=lambda *_: None)
            replies = {}
            def one(n):
                replies[n] = coordinator.ask(
                    {"model": "m", "messages": [{"role": "user", "content": f"q{n}"}]})
            threads = [threading.Thread(target=one, args=(n,)) for n in range(asks)]
            for t in threads: t.start()
            for t in threads: t.join(timeout=10)
            coordinator.close()
            return replies, state

    def test_every_ask_comes_home_and_flights_are_shared(self):
        replies, state = self._fly()
        self.assertEqual(len(replies), 6)
        for n, reply in replies.items():
            self.assertEqual(reply, f"echo q{n}")
        self.assertLessEqual(state["batches"], 3)  # trays shared, not one per ask

    def test_a_failed_item_rides_the_next_tray(self):
        replies, state = self._fly(fail_first_for="q2")
        self.assertEqual(replies[2], "echo q2")
        self.assertGreaterEqual(state["batches"], 2)
