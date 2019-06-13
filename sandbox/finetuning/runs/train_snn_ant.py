import argparse
import itertools
import random

from rllab import config
from rllab.baselines.linear_feature_baseline import LinearFeatureBaseline
from rllab.envs.normalized_env import normalize
from rllab.misc.instrument import stub, run_experiment_lite
from sandbox.finetuning.algos.trpo_snn import TRPO_snn
from sandbox.finetuning.bonus_evaluators.grid_bonus_evaluator import GridBonusEvaluator
from sandbox.finetuning.envs.mujoco.old_ant_env import AntEnv
from sandbox.finetuning.policies.snn_mlp_policy import GaussianMLPPolicy_snn
from sandbox.finetuning.regressors.latent_regressor import Latent_regressor

stub(globals())

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--ec2', '-e', action='store_true', default=False, help="add flag to run in ec2")
    parser.add_argument('--local_docker', '-d', action='store_true', default=False,
                        help="add flag to run in local dock")
    parser.add_argument('--type', '-t', type=str, default='', help='set instance type')
    parser.add_argument('--price', '-p', type=str, default='', help='set betting price')
    parser.add_argument('--subnet', '-sn', type=str, default='', help='set subnet like us-west-1a')
    parser.add_argument('--name', '-n', type=str, default='', help='set exp prefix name and new file name')
    parser.add_argument('--message', '-m', type=str, default='', help='message to inclue in the docstring')
    args = parser.parse_args()

    # set the rewards
    reward_coef_grid_list = [100]  # how much of "intrinsic" bonus to add
    snn_H_bonus_list = [2, 1]  # coef for the snn_H bonus
    visitation_bonus_list = [0]  # coef for the visitation bonus
    survival_bonus_list = [5, 0]
    dist_from_reset_bonus_list = [0.05, 0]

    reward_coef_mi = 0
    reward_coef_kl = 0
    reward_coef_l2 = 0
    rewards_coefs = itertools.product(reward_coef_grid_list, snn_H_bonus_list,
                                      visitation_bonus_list, survival_bonus_list, dist_from_reset_bonus_list)

    # set other algorithm params
    bs = 50000
    pl = 400
    switch_lat_every_list = [400]  # this was 100
    start_bonus_after_list = [10]  # this was 10

    # ant the rest
    for bilinear in [True]:
        for reward_coef_grid, snn_H_bonus, visitation_bonus, survival_bonus, dist_from_reset_bonus in rewards_coefs:

            for switch_lat_every in switch_lat_every_list:
                for start_bonus_after in start_bonus_after_list:
                    for mesh_density in [10]:
                        for latent_dim in [6]:
                            for noisify_coef in [0.1]:
                                for no_contact in [True]:
                                    for rew_speed in [True]:
                                        # if reward_coef_grid == 100 and dist_from_reset_bonus == 0.01:
                                        #     pass
                                        # else:
                                        # env = normalize(SwimmerEnv(ego_obs=True, sparse_rew=True))
                                        env = normalize(AntEnv(ego_obs=True, sparse=False, no_contact=no_contact,
                                                               rew_speed=rew_speed))
                                        # env = normalize(SwimmerEnv(ego_obs=ego, sparse_rew=True))
                                        # env = normalize(SwimmerGatherEnv(coef_inner_rew=coef_inner_rew, ego_obs=ego))
                                        # env = normalize(AntMazeEnv(coef_inner_rew=coef_inner_rew, maze_id=9, length=1,
                                        #                            maze_size_scaling=3, ego_obs=True, no_contact=True,
                                        #                            sparse=False, rew_speed=True))

                                        policy = GaussianMLPPolicy_snn(
                                            env_spec=env.spec,
                                            latent_dim=latent_dim,
                                            latent_name='categorical',
                                            bilinear_integration=bilinear,  # concatenate also the outer product
                                            resample=False,
                                            hidden_sizes=(64, 64),  # (100, 50, 25),
                                            # output_nonlinearity=NL.tanh,  # new for KL control
                                            min_std=1e-6,
                                        )

                                        bonus_evaluator = []
                                        reward_coef_bonus = []
                                        reward_coef_bonus.append(reward_coef_grid)
                                        bonus_evaluator.append(GridBonusEvaluator(mesh_density=mesh_density,
                                                                                  visitation_bonus=visitation_bonus,
                                                                                  survival_bonus=survival_bonus,
                                                                                  snn_H_bonus=snn_H_bonus,
                                                                                  virtual_reset=True,
                                                                                  switch_lat_every=switch_lat_every,
                                                                                  dist_from_reset_bonus=dist_from_reset_bonus,
                                                                                  start_bonus_after=start_bonus_after))

                                        # reward_coef_bonus.append(reward_coef_hash)
                                        # bonus_evaluator.append(HashingBonusEvaluator(env_spec=env.spec))

                                        baseline = LinearFeatureBaseline(env_spec=env.spec)

                                        if latent_dim:
                                            latent_regressor = Latent_regressor(
                                                env_spec=env.spec,
                                                policy=policy,
                                                recurrent=False,
                                                predict_all=True,  # use all the predictions and not only the last
                                                obs_regressed='all',
                                                act_regressed=[],  # use [] for nothing or 'all' for all.
                                                use_only_sign=False,
                                                noisify_traj_coef=noisify_coef,
                                                optimizer=None,
                                                # this defaults to LBFGS, for first order, put 'fist_order'
                                                regressor_args={
                                                    'hidden_sizes': (32, 32),  # (100, 50, 25),
                                                    'name': 'latent_reg',
                                                    'use_trust_region': True,
                                                    # this is useless if using 'first_order'
                                                }
                                            )
                                        else:
                                            latent_regressor = None

                                        algo = TRPO_snn(
                                            env=env,
                                            policy=policy,
                                            baseline=baseline,
                                            self_normalize=True,  # this is only for the hallucinations
                                            log_individual_latents=True,
                                            # this will log the progress of every latent value!
                                            log_deterministic=True,
                                            log_hierarchy=True,
                                            # logged_MI=[dict(recurrent=recurrent_reg,  #it will copy all but this (if other to copy,
                                            #                 obs_regressed=[-3],         # code changes in npo_snn... to do)
                                            #                 act_regressed=[],
                                            #                 )
                                            #            ],  # for none use empty list [], for all use 'all_individual',
                                            # otherwise list of pairs, each entry a list of numbers ([obs],[acts])
                                            #### this sets a RECURRENT ONE!!
                                            # hallucinator=PriorHallucinator(env_spec=env.spec, policy=policy,
                                            #                                n_hallucinate_samples=0),
                                            latent_regressor=latent_regressor,
                                            bonus_evaluator=bonus_evaluator,  # is a list of bonus evaluators !
                                            reward_coef_bonus=reward_coef_bonus,
                                            # this also needs to be a list of same length!
                                            reward_coef_mi=reward_coef_mi,
                                            reward_coef_kl=reward_coef_kl,
                                            # KL_ub=100,
                                            reward_coef_l2=reward_coef_l2,
                                            # L2_ub=100,
                                            batch_size=bs,
                                            whole_paths=False,
                                            max_path_length=pl,
                                            n_itr=1000,
                                            discount=0.99,
                                            step_size=0.01,
                                            switch_lat_every=switch_lat_every,
                                        )

                                        for s in range(5, 20, 10):  # [55, 65, 75, 85, 95]:
                                            exp_prefix = 'snn-egoOldAnt-400pl'
                                            exp_name = exp_prefix + \
                                                       '_{}Switch_{}Mesh_{}H_{}Visit_{}Surv_{}dist_{}GridB_{}After_{}latent_Bil_{}bs_{}pl_{:04d}'.format(
                                                           switch_lat_every, mesh_density,
                                                           ''.join(str(snn_H_bonus).split('.')),
                                                           ''.join(str(visitation_bonus).split('.')),
                                                           ''.join(str(survival_bonus).split('.')),
                                                           ''.join(str(dist_from_reset_bonus).split('.')),
                                                           *[''.join(str(coef_bonus).split('.')) for coef_bonus in
                                                             reward_coef_bonus],
                                                           start_bonus_after,
                                                           latent_dim, bs, pl, s) + "_lowgear"

                                            if args.ec2:
                                                subnets = [
                                                    'us-east-2b', 'us-east-2a', 'ap-northeast-2a', 'ap-south-1a', 'us-east-2c', 'ap-south-1b', 'us-east-1d',
                                                    'us-west-1a'
                                                ]
                                                ec2_instance = args.type if args.type else 'c4.4xlarge'
                                                # configure instance
                                                info = config.INSTANCE_TYPE_INFO[ec2_instance]  # update config file!
                                                config.AWS_INSTANCE_TYPE = ec2_instance
                                                config.AWS_SPOT_PRICE = str(info["price"])
                                                n_parallel = int(info["vCPU"] / 2)  # make the default 4 if not using ec2

                                                print('Running on type {}, with price {}, parallel {} on the subnets: '.format(config.AWS_INSTANCE_TYPE,
                                                                                                                               config.AWS_SPOT_PRICE, n_parallel),
                                                      *subnets)

                                                # choose subnet
                                                subnet = random.choice(subnets)
                                                config.AWS_REGION_NAME = subnet[:-1]
                                                config.AWS_KEY_NAME = config.ALL_REGION_AWS_KEY_NAMES[
                                                    config.AWS_REGION_NAME]
                                                config.AWS_IMAGE_ID = config.ALL_REGION_AWS_IMAGE_IDS[
                                                    config.AWS_REGION_NAME]
                                                config.AWS_SECURITY_GROUP_IDS = \
                                                    config.ALL_REGION_AWS_SECURITY_GROUP_IDS[
                                                        config.AWS_REGION_NAME]
                                                config.AWS_NETWORK_INTERFACES = [
                                                    dict(
                                                        SubnetId=config.ALL_SUBNET_INFO[subnet]["SubnetID"],
                                                        Groups=config.AWS_SECURITY_GROUP_IDS,
                                                        DeviceIndex=0,
                                                        AssociatePublicIpAddress=True,
                                                    )
                                                ]

                                                run_experiment_lite(
                                                    stub_method_call=algo.train(),
                                                    mode='ec2',
                                                    use_cloudpickle=False,
                                                    # Number of parallel workers for sampling
                                                    n_parallel=n_parallel,
                                                    # Only keep the snapshot parameters for the last iteration
                                                    snapshot_mode="last",
                                                    seed=s,
                                                    # plot=True,
                                                    exp_prefix=exp_prefix,
                                                    exp_name=exp_name,
                                                    sync_s3_pkl=True,
                                                    # for sync the pkl file also during the training
                                                    sync_s3_png=True,
                                                    # # use this ONLY with ec2 or local_docker!!!
                                                    pre_commands=[
                                                        "which conda",
                                                        "which python",
                                                        "conda list -n rllab3",
                                                        "conda install -f numpy -n rllab3 -y",
                                                    ],
                                                )
                                            else:
                                                run_experiment_lite(
                                                    stub_method_call=algo.train(),
                                                    mode='local',
                                                    use_cloudpickle=False,
                                                    use_gpu=False,
                                                    n_parallel=10   ,
                                                    # Only keep the snapshot parameters for the last iteration
                                                    snapshot_mode="last",
                                                    seed=s,
                                                    # plot=True,
                                                    exp_prefix=exp_prefix,
                                                    exp_name=exp_name,
                                                )
