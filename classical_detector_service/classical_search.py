"""Algoritmo clásico utilizado para localizar valores anómalos."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right


def run_classical_search(normalized_values: list[float]) -> dict[str, object]:
    """Busca de forma clásica los índices fuera del intervalo normalizado [0, 1].

    Se mantiene el contrato de respuesta del detector cuántico para que el agregador
    pueda cambiar entre alternativas sin cambiar su código de negocio.
    """
    total_states = len(normalized_values)
    if total_states == 0:
        raise ValueError("El lote no puede estar vacío.")

    num_qubits = max(1, math.ceil(math.log2(total_states)))
    # La alternativa clásica conserva exactamente la misma definición de anomalía
    # y el mismo contrato que la implementación cuántica para permitir sustitución.
    # La lista puede llegar desordenada. Se ordena conservando la posición original
    # y se aplican búsquedas binarias sobre los dos límites del intervalo [0,1].
    ordered = sorted((value, index) for index, value in enumerate(normalized_values))
    values = [value for value, _ in ordered]
    lower_end = bisect_left(values, 0.0)
    upper_start = bisect_right(values, 1.0)
    marked_indices = sorted(index for _,index in ordered[:lower_end] + ordered[upper_start:])
    marked_states = [format(index, f"0{num_qubits}b") for index in marked_indices]

    if not marked_indices:
        return {
            "status": "normal",
            "marked_indices": [],
            "marked_states": [],
            "measured_state": None,
            "detected_index": None,
            "grover_iterations": 0,
            "counts": {},
            "num_qubits": num_qubits,
            "circuit_depth": 0,
            "circuit_text": "Búsqueda clásica: no se localizaron anomalías.",
        }

    detected_index = marked_indices[0]
    measured_state = format(detected_index, f"0{num_qubits}b")
    return {
        "status": "anomaly_detected",
        "marked_indices": marked_indices,
        "marked_states": marked_states,
        "measured_state": measured_state,
        "detected_index": detected_index,
        "grover_iterations": 0,
        "counts": {state: 1 for state in marked_states},
        "num_qubits": num_qubits,
        "circuit_depth": 0,
        "circuit_text": "Búsqueda binaria sobre valores ordenados compatible con /detect.",
    }
