from pydantic import BaseModel
from datetime import datetime
import rerun as rr
from rosia.logging import Logger
import rerun.blueprint as rrb
from typing import Optional


class RerunConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str = "rosia_rerun"
    recording_id: str = (
        str(rr.get_recording_id()) if rr.get_recording_id() is not None else datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    blueprint: Optional[rrb.Blueprint] = None
    # Reuse the same recording id if it is already set


class ExecutionConfig(BaseModel):
    trace: bool = False
    log_level: int = Logger.INFO
