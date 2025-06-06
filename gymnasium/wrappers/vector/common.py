"""Wrapper that tracks the cumulative rewards and episode lengths."""
from __future__ import annotations

import time
from collections import deque

import numpy as np

from gymnasium.core import ActType, ObsType
from gymnasium.vector.vector_env import ArrayType, VectorEnv, VectorWrapper


__all__ = ["RecordEpisodeStatistics"]


class RecordEpisodeStatistics(VectorWrapper):
    """This wrapper will keep track of cumulative rewards and episode lengths.

    At the end of any episode within the vectorized env, the statistics of the episode
    will be added to ``info`` using the key ``episode``, and the ``_episode`` key
    is used to indicate the environment index which has a terminated or truncated episode.

        >>> infos = {  # doctest: +SKIP
        ...     ...
        ...     "episode": {
        ...         "r": "<array of cumulative reward for each done sub-environment>",
        ...         "l": "<array of episode length for each done sub-environment>",
        ...         "t": "<array of elapsed time since beginning of episode for each done sub-environment>"
        ...     },
        ...     "_episode": "<boolean array of length num-envs>"
        ... }

    Moreover, the most recent rewards and episode lengths are stored in buffers that can be accessed via
    :attr:`wrapped_env.return_queue` and :attr:`wrapped_env.length_queue` respectively.

    Attributes:
        return_queue: The cumulative rewards of the last ``deque_size``-many episodes
        length_queue: The lengths of the last ``deque_size``-many episodes

    Example:
        >>> from pprint import pprint
        >>> import gymnasium as gym
        >>> envs = gym.make_vec("CartPole-v1", num_envs=3)
        >>> envs = RecordEpisodeStatistics(envs)
        >>> obs, info = envs.reset(123)
        >>> _ = envs.action_space.seed(123)
        >>> end = False
        >>> while not end:
        ...     obs, rew, term, trunc, info = envs.step(envs.action_space.sample())
        ...     end = term.any() or trunc.any()
        ...
        >>> envs.close()
        >>> pprint(info) # doctest: +SKIP
        {'_episode': array([ True, False, False]),
         '_final_info': array([ True, False, False]),
         '_final_observation': array([ True, False, False]),
         'episode': {'l': array([11,  0,  0], dtype=int32),
                     'r': array([11.,  0.,  0.], dtype=float32),
                     't': array([0.007812, 0.      , 0.      ], dtype=float32)},
         'final_info': array([{}, None, None], dtype=object),
         'final_observation': array([array([ 0.11448676,  0.9416149 , -0.20946532, -1.7619033 ], dtype=float32),
               None, None], dtype=object)}
    """

    def __init__(self, env: VectorEnv, deque_size: int = 100):
        """This wrapper will keep track of cumulative rewards and episode lengths.

        Args:
            env (Env): The environment to apply the wrapper
            deque_size: The size of the buffers :attr:`return_queue` and :attr:`length_queue`
        """
        super().__init__(env)

        self.episode_count = 0

        self.episode_start_times: np.ndarray = np.zeros(())
        self.episode_returns: np.ndarray = np.zeros(())
        self.episode_lengths: np.ndarray = np.zeros(())

        self.return_queue = deque(maxlen=deque_size)
        self.length_queue = deque(maxlen=deque_size)

    def reset(
        self,
        seed: int | list[int] | None = None,
        options: dict | None = None,
    ):
        """Resets the environment using kwargs and resets the episode returns and lengths."""
        obs, info = super().reset(seed=seed, options=options)

        self.episode_start_times = np.full(
            self.num_envs, time.perf_counter(), dtype=np.float32
        )
        self.episode_returns = np.zeros(self.num_envs, dtype=np.float32)
        self.episode_lengths = np.zeros(self.num_envs, dtype=np.int32)

        return obs, info

    def step(
        self, actions: ActType
    ) -> tuple[ObsType, ArrayType, ArrayType, ArrayType, dict]:
        """Steps through the environment, recording the episode statistics."""
        (
            observations,
            rewards,
            terminations,
            truncations,
            infos,
        ) = self.env.step(actions)

        assert isinstance(
            infos, dict
        ), f"`info` dtype is {type(infos)} while supported dtype is `dict`. This may be due to usage of other wrappers in the wrong order."

        self.episode_returns += rewards
        self.episode_lengths += 1

        dones = np.logical_or(terminations, truncations)
        num_dones = np.sum(dones)

        if num_dones:
            if "episode" in infos or "_episode" in infos:
                raise ValueError(
                    "Attempted to add episode stats when they already exist"
                )
            else:
                infos["episode"] = {
                    "r": np.where(dones, self.episode_returns, 0.0),
                    "l": np.where(dones, self.episode_lengths, 0),
                    "t": np.where(
                        dones,
                        np.round(time.perf_counter() - self.episode_start_times, 6),
                        0.0,
                    ),
                }
                infos["_episode"] = dones

            self.episode_count += num_dones

            for i in np.where(dones):
                self.return_queue.extend(self.episode_returns[i])
                self.length_queue.extend(self.episode_lengths[i])

            self.episode_lengths[dones] = 0
            self.episode_returns[dones] = 0
            self.episode_start_times[dones] = time.perf_counter()

        return (
            observations,
            rewards,
            terminations,
            truncations,
            infos,
        )
