from pydantic import BaseModel
from datetime import datetime
import rerun as rr


class RerunConfig(BaseModel):
    name: str = "rosia_rerun"
    recording_id: str = (
        str(rr.get_recording_id())
        if rr.get_recording_id() is not None
        else datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    # Reuse the same recording id if it is already set


class ExecutionConfig(BaseModel):
    trace: bool = False
