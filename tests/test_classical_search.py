from classical_detector_service.classical_search import run_classical_search


def test_classical_search_finds_first_anomaly():
    result = run_classical_search([0.2, 0.5, 1.4, 0.7])
    assert result["status"] == "anomaly_detected"
    assert result["detected_index"] == 2
    assert result["measured_state"] == "10"


def test_classical_search_normal_batch():
    result = run_classical_search([0.2, 0.5, 0.8, 0.7])
    assert result["status"] == "normal"
    assert result["detected_index"] is None
