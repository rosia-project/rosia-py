from typing import Any
import rerun as rr
import rerun.blueprint as rrb

import numpy as np
from PIL import Image

from rosia.time import Time
from rosia.config import RerunConfig


class RerunManager:
    def __init__(self):
        pass

    def set_rerun_config(self, rerun_config: RerunConfig):
        self.rerun_config = rerun_config

    def init(self):
        rr.init(
            self.rerun_config.name,
            recording_id=self.rerun_config.recording_id,
            spawn=True,
        )

    def send_blueprint(self) -> None:
        rr.send_blueprint(
            rrb.Blueprint(
                rrb.Spatial2DView(origin="/diagram", background=[255, 255, 255])
            )
        )

    def render_diagram(self, diagram: Image.Image) -> None:
        rr.log("/diagram", rr.Image(np.array(diagram)))

    def trace(
        self, node_name: str, logical_time: Time, physical_time: Time, message: Any
    ) -> None:
        rr.set_time("logical_time", duration=logical_time.to_unix_time())
        rr.set_time("physical_time", duration=physical_time.to_unix_time())
        rr.log(
            f"/trace/{node_name}",
            rr.TextLog(text=str(message), level="DEBUG"),
        )
