from __future__ import annotations

# This module reuses and extends detector/diagnostics acceptance tests.
from test_detector_diagnostics_contract import (  # noqa: F401
    test_no_import_side_effects,
    test_docx_bomb_xxe_and_ooxml_parts_limits,
    test_error_responses_do_not_leak_pii,
    test_repertorium_decyzja_and_csm_mode,
)

if __name__ == "__main__":
    test_no_import_side_effects()
    test_docx_bomb_xxe_and_ooxml_parts_limits()
    test_error_responses_do_not_leak_pii()
    test_repertorium_decyzja_and_csm_mode()
    print("OK: detector/diagnostics acceptance tests passed")
