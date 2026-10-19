"""Render a demo brief from the fictional fixtures, with a stand-in for the LLM.

    python tests/fixtures/demo.py /tmp/demo-site

Useful for checking the page layout without network access or an API key.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]

import make_fixtures as fx_data                      # noqa: E402
from ceemea_brief import pipeline                    # noqa: E402
from ceemea_brief.config import load_config          # noqa: E402
from fake_llm import FakeClient          # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
with tempfile.TemporaryDirectory() as tmp:
    cfg_path = Path(tmp) / "c.yaml"
    cfg_path.write_text(fx_data.COUNTRIES)
    hist = Path(tmp) / "history"
    hist.mkdir()
    (hist / "2026-10-19.json").write_text(json.dumps(fx_data.PREVIOUS))
    pipeline.run(run_date="2026-10-20", raw=fx_data.raw_inputs(), cfg=load_config(cfg_path), use_llm=True,
                 out_dir=out, history_dir=hist, client=FakeClient(),
                 label="DEMO · fictional countries and headlines, scripted model replies")
print(out / "index.html")
