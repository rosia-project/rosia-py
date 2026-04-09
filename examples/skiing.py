"""Atari Skiing with a heuristic agent using Rosia.

Pipeline:
  Environment <-> Agent

The Environment wraps gymnasium's Skiing-v5.
The Agent uses a simple angle-tracking heuristic to steer through gates.

Based on: https://github.com/ercardenas/ski-master/blob/master/train_heuristic.py

Requirements:
pip install 'gymnasium[atari]' 'ale-py' 'autorom[accept-rom-license]'
"""

import numpy as np
import gymnasium as gym
import ale_py


import rerun as rr
import rerun.blueprint as rrb

from rosia import InputPort, OutputPort, reaction, Node, Application, request_shutdown, log
from rosia.config import RerunConfig
from rosia.time import s

gym.register_envs(ale_py)

# Colors in RGB
PLAYER_COLOR = np.array([214, 92, 92])
RED_FLAG_COLOR = np.array([184, 50, 50])
BLUE_FLAG_COLOR = np.array([66, 72, 200])
THETA_DIFF_THRESHOLD = 0.015
SEED = 42


@Node
class Environment:
    observation = OutputPort[np.ndarray]()
    action_in = InputPort[int]()

    def __init__(self, render: bool = True):
        self.render = render
        self.observation.set_STAT(0 * s)
        self.dt = 1 * s / 15
        render_mode = "rgb_array" if self.render else None
        self.env = gym.make("ALE/Skiing-v5", render_mode=render_mode)
        self.env.action_space.seed(SEED)

    def start(self):
        frame, _ = self.env.reset(seed=SEED)
        log.info("Game started")
        self.observation(frame, STAT=self.dt)

    @reaction([action_in], eager=True)
    def on_action(self):
        frame, _, terminated, truncated, _ = self.env.step(self.action_in)
        done = terminated or truncated
        if done:
            log.info("Game over!")
            request_shutdown()
        else:
            yield self.dt
            self.observation(frame, STAT=self.dt)

    def shutdown(self):
        self.env.close()


@Node
class Agent:
    observation_in = InputPort[np.ndarray]()
    action_out = OutputPort[int]()

    def __init__(self):
        self.prev_theta = 0.0

    def find_position(self, frame: np.ndarray, color: np.ndarray) -> tuple[float, float] | None:
        """Find mean position of pixels matching color. Returns (row, col) or None."""
        mask = np.all(frame == color, axis=2)
        positions = np.argwhere(mask)
        if len(positions) == 0:
            return None
        return float(positions[:, 0].mean()), float(positions[:, 1].mean())

    @reaction([observation_in])
    def decide(self):
        frame = self.observation_in
        player_pos = self.find_position(frame, PLAYER_COLOR)
        cropped = frame[:200]
        flag_pos = self.find_position(cropped, RED_FLAG_COLOR) or self.find_position(cropped, BLUE_FLAG_COLOR)

        if player_pos is None or flag_pos is None:
            # Can't see player or flag, go straight
            self.action_out(0)
            return

        player_row, player_col = player_pos
        flag_row, flag_col = flag_pos

        theta = np.arctan2(flag_row - player_row, flag_col - player_col)
        theta_diff = theta - self.prev_theta
        self.prev_theta = theta

        if theta_diff > THETA_DIFF_THRESHOLD:
            action = 2  # LEFT
        elif theta_diff < -THETA_DIFF_THRESHOLD:
            action = 1  # RIGHT
        else:
            action = 0  # NOOP

        log.rerun(rr.Image(frame), rerun_subpath="game")
        self.action_out(action)


if __name__ == "__main__":
    app = Application()
    env = app.create_node(Environment(render=True))
    agent = app.create_node(Agent())

    env.observation >>= agent.observation_in
    agent.action_out >>= env.action_in

    app.diagram()
    app.execute(
        rerun_config=RerunConfig(
            name="skiing",
            blueprint=rrb.Blueprint(rrb.Spatial2DView()),
        )
    )
