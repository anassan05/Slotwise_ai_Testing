from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class ClinicService:
    id: str
    name: str
    duration_minutes: int


@dataclass(frozen=True)
class ClinicDoctor:
    id: str
    name: str
    specialty: str


CLINIC_OPEN = time(9, 0)
CLINIC_CLOSE = time(17, 0)
SLOT_INTERVAL_MINUTES = 5

SERVICES = (
    ClinicService("general_consultation", "General Consultation", 15),
    ClinicService("specialist_consultation", "Specialist Consultation", 30),
    ClinicService("follow_up_consultation", "Follow-up Consultation", 10),
    ClinicService("dental_consultation", "Dental Consultation", 30),
    ClinicService("vaccination", "Vaccination", 15),
    ClinicService("diagnostic_consultation", "Diagnostic Consultation", 30),
)

SERVICE_BY_ID = {service.id: service for service in SERVICES}
SERVICE_BY_NAME = {service.name.casefold(): service for service in SERVICES}

DOCTORS = (
    ClinicDoctor("dr_rao", "Dr. Kavya Rao", "General Medicine"),
    ClinicDoctor("dr_tanaka", "Dr. Haruto Tanaka", "Specialist Care"),
    ClinicDoctor("dr_mehta", "Dr. Rohan Mehta", "Dental & Diagnostics"),
)

DOCTOR_BY_ID = {doctor.id: doctor for doctor in DOCTORS}
