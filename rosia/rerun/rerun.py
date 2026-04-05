import rerun as rr
import rerun.blueprint as rrb

import numpy as np
from PIL import Image

from rosia.time import Time
from typing import TYPE_CHECKING
from collections.abc import Iterable
from rerun._baseclasses import AsComponents, DescribedComponentBatch


if TYPE_CHECKING:
    from rosia.config import RerunConfig


class RerunManager:
    def __init__(self):
        pass

    def init(self, rerun_config: "RerunConfig"):
        self.rerun_config = rerun_config
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
        rr.log("/diagram", rr.Image(np.array(diagram)), static=True)

    def log(
        self,
        entity_path: str,
        message: AsComponents | Iterable[DescribedComponentBatch],
        logical_time: Time,
        physical_time: Time,
    ) -> None:
        rr.set_time("logical_time", duration=logical_time.to_unix_time())
        rr.set_time("physical_time", duration=physical_time.to_unix_time())
        rr.log(f"/{entity_path}", message)

    def shutdown(self) -> None:
        rr.cleanup_if_forked_child()
        rr.disconnect()
