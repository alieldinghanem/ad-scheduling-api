"""Automatically enable the ADEX scheduler performance patch.

Python imports ``sitecustomize`` automatically during normal interpreter
startup, so the optimization is applied both in the Uvicorn web process and in
the spawned scheduler worker process without changing the scheduler's public
API.
"""

from scheduler import SchedulingEngine
from scheduler_performance import install_scheduler_performance_patch

install_scheduler_performance_patch(SchedulingEngine)
