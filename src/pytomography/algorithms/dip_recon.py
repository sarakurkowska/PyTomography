from __future__ import annotations
import torch
import torch.nn as nn
import numpy as np
from pytomography.projectors import SystemMatrix
import abc
import pytomography
from pytomography.priors import Prior
from pytomography.likelihoods import Likelihood
from pytomography.callbacks import Callback
from pytomography.transforms.shared import KEMTransform
from pytomography.transforms.SPECT import CutOffTransform
from pytomography.projectors.shared import KEMSystemMatrix
from pytomography.utils import check_if_class_contains_method
from collections.abc import Callable
from .preconditioned_gradient_ascent import OSEM

class DIPRecon:
    r"""Implementation of the Deep Image Prior reconstruction technique (see https://ieeexplore.ieee.org/document/8581448). This reconstruction technique requires an instance of a user-defined ``prior_network`` that implements two functions: (i) a ``fit`` method that takes in an ``object`` (:math:`x`) which the network ``f(z;\theta)`` is subsequently fit to, and (ii) a ``predict`` function that returns the current network prediction :math:`f(z;\theta)`. For more details, see the Deep Image Prior tutorial.

        Args:
            projections (torch.tensor): projection data :math:`g` to be reconstructed
            system_matrix (SystemMatrix): System matrix :math:`H` used in :math:`g=Hf`.
            prior_network (nn.Module): User defined prior network that implements the neural network ``f(z;\theta)``
            rho (float, optional): Value of :math:`\rho` used in the optimization procedure. Defaults to 1.
            scatter (torch.tensor | float, optional): Projection space scatter estimate. Defaults to 0.
            precompute_normalization_factors (bool, optional): Whether to precompute :math:`H_m^T 1` and store on GPU in the OSEM network before reconstruction. Defaults to True.
        """
    def __init__(
        self,
        likelihood: Likelihood,
        prior_network: nn.Module,
        rho: float = 3e-3,
        EM_algorithm = OSEM,
    ) -> None:
        self.EM_algorithm = EM_algorithm(
            likelihood,
            object_initial = nn.ReLU()(prior_network.predict().clone())
            )
        self.likelihood = likelihood
        self.prior_network = prior_network
        self.rho = rho
        
    def _compute_callback(self, n_iter: int, n_subset: int):
        """Method for computing callbacks after each reconstruction iteration

        Args:
            n_iter (int): Number of iterations
            n_subset (int): Number of subsets
        """
        self.callback.run(self.object_prediction, n_iter, n_subset)
        
    def __call__(
        self,
        n_iters,
        subit1,
        n_subsets_osem=1,
        callback=None,
    ):  
        r"""Implementation of Algorithm 1 in https://ieeexplore.ieee.org/document/8581448. This implementation gives the additional option to use ordered subsets. The quantity SubIt2 specified in the paper is controlled by the user-defined ``prior_network`` class.

        Args:
            n_iters (int): Number of iterations (MaxIt in paper)
            subit1 (int): Number of OSEM iterations before retraining neural network (SubIt1 in paper)
            n_subsets_osem (int, optional): Number of subsets to use in OSEM reconstruction. Defaults to 1.

        Returns:
            torch.Tensor: Reconstructed image
        """
        self.callback = callback
        # Initialize quantities
        mu = 0 
        norm_BP = self.likelihood.system_matrix.compute_normalization_factor()
        x = self.prior_network.predict()
        x_network = x.clone()
        for _ in range(n_iters):
            for j in range(subit1):
                for k in range(n_subsets_osem):
                    self.EM_algorithm.object_prediction = nn.ReLU()(x.clone())
                    x_EM = self.EM_algorithm(n_iters = 1, n_subsets = n_subsets_osem, n_subset_specific=k)
                    x = 0.5 * (x_network - mu - norm_BP / self.rho) + 0.5 * torch.sqrt((x_network - mu - norm_BP / self.rho)**2 + 4 * x_EM * norm_BP / self.rho)
            self.prior_network.fit(x + mu)
            x_network = self.prior_network.predict()
            mu += x - x_network
            self.object_prediction = nn.ReLU()(x_network)
            # evaluate callback
            if self.callback is not None:
                self._compute_callback(n_iter = _, n_subset=None)
        return self.object_prediction