"""API del detector clásico de anomalías."""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from classical_detector_service.classical_search import run_classical_search
from classical_detector_service.observability import ObservabilityPublisher
from shared.models import QuantumBatch, QuantumDetectionResult

SIMULATED_EXECUTION_TIME = float(os.getenv("SIMULATED_EXECUTION_TIME", "1000"))
SIMULATED_RELIABILITY = float(os.getenv("SIMULATED_RELIABILITY", "0.10"))
SIMULATED_AVAILABILITY = float(os.getenv("SIMULATED_AVAILABILITY", "24"))
SIMULATED_COST = float(os.getenv("SIMULATED_COST", "0.35"))
SIMULATED_RESPONSE_TIME_MS = float(os.getenv("SIMULATED_RESPONSE_TIME_MS", "150"))
OBSERVABILITY_URL = os.getenv("OBSERVABILITY_URL", "")
APPLICATION_ID = os.getenv("APPLICATION_ID", "default")
SERVICE_ID = os.getenv("SERVICE_ID", "classical-detector")



class SimulationRequest(BaseModel):
    """Define los parámetros de una simulación temporal de incumplimiento."""
    failed: bool | None = None
    execution_time: float | None = None
    reliability: float | None = None
    availability: float | None = None
    cost: float | None = None
    response_time_ms: float | None = None
    reason: str | None = None
    recover_after_seconds: float | None = None


class SimulationState(BaseModel):
    """Conserva el estado temporal de una simulación de fallo."""
    failed: bool = False
    execution_time: float = SIMULATED_EXECUTION_TIME
    reliability: float = SIMULATED_RELIABILITY
    availability: float = SIMULATED_AVAILABILITY
    cost: float = SIMULATED_COST
    response_time_ms: float = SIMULATED_RESPONSE_TIME_MS
    reason: str | None = None
    recover_at: float | None = None


state = SimulationState()
observability = ObservabilityPublisher(OBSERVABILITY_URL, SERVICE_ID)


DEFAULT_SIMULATION_VALUES = {
    "failed": False,
    "execution_time": SIMULATED_EXECUTION_TIME,
    "reliability": SIMULATED_RELIABILITY,
    "availability": SIMULATED_AVAILABILITY,
    "cost": SIMULATED_COST,
    "response_time_ms": SIMULATED_RESPONSE_TIME_MS,
}


def recover_if_needed() -> None:
    """Restaura automáticamente los fallos temporales después de 10-15 segundos.

    Esto permite simular degradaciones transitorias, como ocurriría en servicios externos reales.
    El reinicio/redespliegue real sigue existiendo, pero la avería inyectada no queda permanente.
    """
    recover_at = getattr(state, "recover_at", None)
    if recover_at is None or time.time() < float(recover_at):
        return
    state.failed = False
    state.execution_time = DEFAULT_SIMULATION_VALUES["execution_time"]
    state.reliability = DEFAULT_SIMULATION_VALUES["reliability"]
    state.availability = DEFAULT_SIMULATION_VALUES["availability"]
    state.cost = DEFAULT_SIMULATION_VALUES["cost"]
    state.response_time_ms = DEFAULT_SIMULATION_VALUES["response_time_ms"]
    if hasattr(state, "failure_reason"):
        state.failure_reason = None
    if hasattr(state, "reason"):
        state.reason = None
    state.recover_at = None
    append_event({"type": "temporary_failure_recovered", "message": "Detector clásico vuelve automáticamente a estado correcto tras fallo temporal."})


def now_iso() -> str:
    """Devuelve la fecha y hora actual en formato ISO 8601 y zona UTC."""
    return datetime.now(timezone.utc).isoformat()


def append_event(event: dict[str, Any], *, severity: str = "info") -> None:
    """Emite el evento por stdout y lo publica en el almacén central de observabilidad."""
    payload = {"time": now_iso(), "service": SERVICE_ID, **event}
    print(f"[CLASSICAL] {json.dumps(payload, ensure_ascii=False)}", flush=True)
    observability.publish_later(
        category="operational",
        event_type=str(event.get("type", "detector_event")),
        payload=payload,
        application_id=APPLICATION_ID,
        severity=severity,
        service_id=SERVICE_ID,
        timestamp=payload["time"],
    )

def fail_if_simulated() -> None:
    """Aplica el retraso o error configurado por una simulación activa."""
    recover_if_needed()
    if state.failed:
        raise HTTPException(
            status_code=503,
            detail=state.reason or "Fallo simulado del detector clásico.",
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Gestiona el arranque y apagado mediante la API vigente de FastAPI."""
    append_event({"type": "service_started", "backend": "classical-search", "mode": "CPU"})
    try:
        yield
    finally:
        append_event({"type": "service_stopped"})


app = FastAPI(title="Detector clásico", version="1.2.0", lifespan=lifespan)


from classical_detector_service.qos_signal import Signal
qos_signal = Signal()

@app.get("/health")
async def health() -> dict[str, Any]:
    """Devuelve el estado de salud del componente para comprobaciones externas."""
    fail_if_simulated()
    return {
        "status": "ok",
        "backend": "classical-search",
        "mode": "CPU",
    }


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    """Devuelve las métricas operativas expuestas por el componente."""
    recover_if_needed()
    return qos_signal.decorate({
        "status": "failed" if state.failed else "ok",
        "mode": "CPU",
        "execution_time": state.execution_time,
        "reliability": state.reliability,
        "availability": state.availability,
        "cost": state.cost,
        "response_time_ms": state.response_time_ms,
    })


@app.post("/admin/simulate")
async def simulate(request: SimulationRequest) -> dict[str, Any]:
    """Activa una simulación temporal con los parámetros recibidos."""
    if request.failed is not None:
        state.failed = request.failed
    if request.execution_time is not None:
        state.execution_time = request.execution_time
    if request.reliability is not None:
        state.reliability = request.reliability
    if request.availability is not None:
        state.availability = request.availability
    if request.cost is not None:
        state.cost = request.cost
    if request.response_time_ms is not None:
        state.response_time_ms = request.response_time_ms
    if request.reason is not None:
        state.reason = request.reason
    if request.recover_after_seconds is not None:
        state.recover_at = time.time() + max(0.0, float(request.recover_after_seconds))
    append_event({"type": "simulation_updated", "simulation": state.model_dump()})
    return {"status": "updated", "simulation": state.model_dump()}


@app.post("/admin/relaunch")
async def relaunch() -> dict[str, Any]:
    """Simula relanzar el servicio: limpia únicamente el fallo de disponibilidad.

    Las métricas de coste y tiempo de respuesta no se resetean para que el
    monitor pueda distinguir entre una caída puntual y un servicio que sigue
    siendo ineficiente tras relanzarlo.
    """
    state.failed = False
    state.execution_time = DEFAULT_SIMULATION_VALUES["execution_time"]
    state.reliability = DEFAULT_SIMULATION_VALUES["reliability"]
    state.availability = DEFAULT_SIMULATION_VALUES["availability"]
    state.cost = DEFAULT_SIMULATION_VALUES["cost"]
    state.response_time_ms = DEFAULT_SIMULATION_VALUES["response_time_ms"]
    state.recover_at = None
    state.reason = "Servicio relanzado por el monitor."
    append_event({"type": "service_relaunched", "state": state.model_dump()})
    return {"status": "relaunched", "state": state.model_dump()}


@app.post("/detect", response_model=QuantumDetectionResult)
async def detect(batch: QuantumBatch) -> QuantumDetectionResult:
    """Analiza un lote de valores y devuelve las anomalías encontradas."""
    fail_if_simulated()
    normalized_values = [
        reading.normalized_temperature for reading in batch.readings
    ]

    try:
        result = run_classical_search(normalized_values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if result["status"] == "normal":
        message = (
            f"El lote {batch.batch_id} no contiene temperaturas fuera del "
            f"intervalo [{batch.safe_min_c}, {batch.safe_max_c}] °C."
        )
    else:
        detected_index = int(result["detected_index"])
        reading = batch.readings[detected_index]
        message = (
            f"La búsqueda clásica localizó el índice {detected_index} "
            f"({result['measured_state']}): {reading.sensor_id}, "
            f"zona={reading.zone}, temperatura={reading.temperature_c:.3f} °C."
        )

    return QuantumDetectionResult(
        batch_id=batch.batch_id,
        status=result["status"],
        marked_indices=result["marked_indices"],
        marked_states=result["marked_states"],
        measured_state=result["measured_state"],
        detected_index=result["detected_index"],
        grover_iterations=result["grover_iterations"],
        counts=result["counts"],
        num_qubits=result["num_qubits"],
        circuit_depth=result["circuit_depth"],
        message=message,
        circuit_text=result["circuit_text"],
    )
