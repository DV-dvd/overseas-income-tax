from experiments.integrity_ablation import run_ablation


def test_integrity_layer_has_gain_on_synthetic_adversarial_cases():
    result = run_ablation()
    assert result["gate_passed"] is True
    assert result["with_integrity_passed"] == result["total"]
    assert result["without_integrity_passed"] < result["with_integrity_passed"]

