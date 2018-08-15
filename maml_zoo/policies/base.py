from maml_zoo.utils.utils import remove_scope_from_name
from maml_zoo.utils import Serializable

import tensorflow as tf
from collections import OrderedDict


class Policy(Serializable):
    """
    A container for storing the current pre and post update policies
    Also provides functions for executing and updating policy parameters

    Note:
        the preupdate policy is stored as tf.Variables, while the postupdate
        policy is stored in numpy arrays and executed through tf.placeholders

    Args:
        obs_dim (int): dimensionality of the observation space -> specifies the input size of the policy
        action_dim (int): dimensionality of the action space -> specifies the output size of the policy
        name (str) : Name used for scoping variables in policy
        hidden_sizes (tuple) : size of hidden layers of network
        learn_std (bool) : whether to learn variance of network output
        hidden_nonlinearity (Operation) : nonlinearity used between hidden layers of network
        output_nonlinearity (Operation) : nonlinearity used after the final layer of network
    """
    def __init__(self,
                 obs_dim,
                 action_dim,
                 name='policy',
                 hidden_sizes=(32, 32),
                 learn_std=True,
                 hidden_nonlinearity=tf.tanh,
                 output_nonlinearity=None,
                 **kwargs
                 ):
        Serializable.quick_init(self, locals())

        self.param_assign_ops = None
        self.param_assign_placeholders = None

    def build_graph(self):
        """
        Builds computational graph for policy
        """
        raise NotImplementedError

    def get_action(self, observation):
        """
        Runs a single observation through the specified policy

        Args:
            observation (array) : single observation

        Returns:
            (array) : array of arrays of actions for each env
        """
        raise NotImplementedError

    def get_actions(self, observations):
        """
        Runs each set of observations through each task specific policy

        Args:
            observations (array) : array of arrays of observations generated by each task and env

        Returns:
            (tuple) : array of arrays of actions for each env (meta_batch_size) x (batch_size) x (action_dim)
                      and array of arrays of agent_info dicts 
        """
        raise NotImplementedError

    def reset(self, dones=None):
        pass

    def log_diagnostics(self, paths):
        """
        Log extra information per iteration based on the collected paths
        """
        pass

    @property
    def distribution(self):
        """
        Returns this policy's distribution

        Returns:
            (Distribution) : this policy's distribution
        """
        raise NotImplementedError

    def distribution_info_sym(self, obs_var, params=None):
        """
        Return the symbolic distribution information about the actions.

        Args:
            obs_var (placeholder) : symbolic variable for observations
            parmas (None or dict) : a dictionary of placeholders that contains information about the
            state of the policy at the time it received the observation

        Returns:
            (dict) : a dictionary of tf placeholders for the policy output distribution
        """
        raise NotImplementedError

    def distribution_info_keys(self, obs, state_infos):
        """
        Args:
            obs (placeholder) : symbolic variable for observations
            state_infos (dict) : a dictionary of placeholders that contains information about the
            state of the policy at the time it received the observation

        Returns:
            (dict) : a dictionary of tf placeholders for the policy output distribution
        """
        raise NotImplementedError


    """ --- methods for serialization --- """

    def get_params(self):
        """
        Get the tf.Variables representing the trainable weights of the network (symbolic)

        Returns:
            (dict) : a dict of all trainable Variables
        """
        return self.policy_params

    def get_param_values(self):
        """
        Gets a list of all the current weights in the network (in original code it is flattened, why?)

        Returns:
            (list) : list of values for parameters
        """
        param_values = tf.get_default_session().run(self.policy_params)
        return param_values

    def set_params(self, policy_params):
        """
        Sets the parameters for the graph

        Args:
            policy_params (dict): of variable names and corresponding parameter values
        """
        assert all([k1 == k2 for k1, k2 in zip(self.get_params().keys(), policy_params.keys())]), \
            "parameter keys must match with vrariable"

        assign_ops, feed_dict = [], {}
        for var, (param_name, var_value) in zip(self.get_params().values(), policy_params.items()):
            assign_placeholder = tf.placeholder(dtype=var.dtype)
            assign_op = tf.assign(var, assign_placeholder)
            assign_ops.append(assign_op)
            feed_dict[assign_placeholder] = var_value
        tf.get_default_session().run(assign_ops, feed_dict=feed_dict)


    def __getstate__(self):
        state = {
            'init_args': Serializable.__getstate__(self),
            'network_params': self.get_param_values()
        }
        return state

    def __setstate__(self, state):
        Serializable.__setstate__(self, state['init_args'])
        tf.get_default_session().run(tf.global_variables_initializer())
        self.set_params(state['network_params'])


class MetaPolicy(Policy):

    def __init__(self, *args, **kwargs):
        super(MetaPolicy, self).__init__(*args, **kwargs)
        self._pre_update_mode = True
        self.policies_params_vals = None

    def build_graph(self):
        """
        Also should create lists of variables and corresponding assign ops
        """
        raise NotImplementedError

    def _create_placeholders_for_vars(self, scopes, meta_batch_size=1, graph_keys=tf.GraphKeys.TRAINABLE_VARIABLES):
        assert isinstance(scopes, list) or isinstance(scopes, tuple)
        placeholders = []

        for scope in scopes:
            var_list = tf.get_collection(graph_keys, scope=scope)
            placeholders.append([OrderedDict([(remove_scope_from_name(var.name, scope),
                                              tf.placeholder(tf.float32, shape=var.shape))
                                             for var in var_list])
                                for _ in range(meta_batch_size)
                                 ])
        return placeholders

    def switch_to_pre_update(self):
        """
        Switches get_action to pre-update policy
        """
        self._pre_update_mode = True
        self.policies_params_vals = None

    def get_actions(self, observations):
        if self._pre_update_mode:
            return self._get_pre_update_actions(observations)
        else:
            return self._get_post_update_actions(observations)

    def _get_pre_update_actions(self, observations):
        """
        Args:
            observations (list): List of size meta-batch size with numpy arrays of shape batch_size x obs_dim
        """
        raise NotImplementedError

    def _get_post_update_actions(self, observations):
        """
        Args:
            observations (list): List of size meta-batch size with numpy arrays of shape batch_size x obs_dim
        """
        raise NotImplementedError

    def update_task_parameters(self, updated_policies_parameters):
        """
        Args:
            updated_policies_parameters (list): List of size meta-batch size. Each contains a dict with the policies
            parameters
        """
        self.policies_params_vals = updated_policies_parameters
        self._pre_update_mode = False

