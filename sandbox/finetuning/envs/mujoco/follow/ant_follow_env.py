from sandbox.finetuning.envs.mujoco.follow.follow_env import FollowEnv
from sandbox.finetuning.envs.mujoco.ant_env import AntEnv


class AntFollowEnv(FollowEnv):
    MODEL_CLASS = AntEnv
    ORI_IND = 3

