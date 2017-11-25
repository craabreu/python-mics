"""
.. module:: mixtures
   :platform: Unix, Windows
   :synopsis: a module for defining the class :class:`Mixture`.

.. moduleauthor:: Charlles R. A. Abreu <abreu@eq.ufrj.br>


"""

import numpy as np
import pandas as pd

import mics as mx
from mics.utils import genfunc
from mics.utils import info
from mics.utils import multimap
from mics.utils import overlapSampling


class mixture:
    """A mixture of independently collected samples (MICS)

        Args:
            samples (list or tuple):
                a list of samples.
            title (str, optional):
                a title.
            verbose (bool, optional):
                a verbosity tag.
            tol (float, optional):
                a tolerance.

    """

    # ======================================================================================
    def _definitions(self, samples, title, verbose):

        info(verbose, "Setting up %s case:" % type(self).__name__, title)

        m = self.m = len(samples)
        if m == 0:
            raise ValueError("list of samples is empty")
        info(verbose, "Number of samples:", m)

        if type(samples) is mx.pool:
            self.samples = samples.samples
            self.label = samples.label
        else:
            self.samples = samples
            self.label = ""
        self.title = title
        self.verbose = verbose

        names = self.names = list(samples[0].dataset.columns)
        if any(list(s.dataset.columns) != names for s in samples):
            raise ValueError("provided samples have distinct properties")
        info(verbose, "Properties:", ", ".join(names))

        n = self.n = np.array([s.dataset.shape[0] for s in samples])
        info(verbose, "Sample sizes:", str(self.n))

        neff = np.array([s.neff for s in samples])
        info(verbose, "Effective sample sizes:", neff)

        potentials = [s.potential for s in samples]
        self.u = [multimap(potentials, s.dataset) for s in samples]

        self.f = overlapSampling(self.u)
        info(verbose, "Initial free-energy guess:", self.f)

        self.frame = pd.DataFrame(index=np.arange(m) + 1)
        if self.label:
            self.states = ["%s = %s" % (self.label, s.label) for s in samples]
            self.frame[self.label] = [s.label for s in samples]
        else:
            self.states = ["state %d" % (i+1) for i in range(m)]

        return m, n, neff

    # ======================================================================================
    def free_energies(self):
        """
        Returns a data frame containing the relative free energies of the datasetd samples
        of a `mixture`, as well as their standard errors.

        """
        frame = self.frame.copy()
        frame['f'] = self.f
        frame['df'] = np.sqrt(np.diag(self.Theta) - 2*self.Theta[:, 0] + self.Theta[0, 0])
        return frame

    # ======================================================================================
    def reweighting(self,
                    potential,
                    properties,
                    combinations={},
                    conditions=pd.DataFrame(),
                    **kwargs):
        """
        Performs reweighting of the properties computed by `functions` from the mixture to
        the samples determined by the provided `potential` with all `parameter` values.

        Args:
            potential (function/string):
            properties (dict of functions/strings):
            combinations (dict of strings):
            parameter (pandas.DataFrame):
            **kwargs:

        """
        datasets = [s.dataset for s in self.samples]

        functions = [genfunc(p, self.names, **kwargs) for p in properties.values()]
        y = [multimap(functions, x) for x in datasets]

        N = len(conditions)
        yu = np.empty([N, len(properties)])
        dyu = np.empty([N, len(properties)])
        for j, row in conditions.iterrows():
            condition = row.to_dict()
            info(self.verbose, "Condition[%d]:" % j, condition)
            condition.update(kwargs)

            potfunc = genfunc(potential, self.names, **condition)
            u = [multimap([potfunc], x) for x in datasets]

            yu[j, :], Theta = self._reweight(u, y)
            dyu[j, :] = np.sqrt(Theta.diagonal())

        frame = conditions.copy()
        for (i, p) in enumerate(properties.keys()):
            frame[p] = yu[:, i]
            frame['d' + p] = dyu[:, i]

        return frame

    # ======================================================================================
    def fep(self, potential, conditions=pd.DataFrame(), **kwargs):
        """
        Performs free energy perturbation.

        Args:
            potential (function/string):
            conditions (pandas.DataFrame):
            **kwargs:

        """
        datasets = [s.dataset for s in self.samples]

        N = len(conditions)
        f = np.empty(N)
        df = np.empty(N)
        for j, row in conditions.iterrows():
            condition = row.to_dict()
            info(self.verbose, "Condition[%d]:" % j, condition)
            condition.update(kwargs)

            potfunc = genfunc(potential, self.names, **condition)
            u = [multimap([potfunc], x) for x in datasets]

            f[j], df[j] = self._perturbation(u)

        frame = conditions.copy()
        frame['f'] = f
        frame['df'] = df

        return frame

    # ======================================================================================
    def histograms(self, bins=100):
        u0 = self.u0
        u0min = min([np.amin(x) for x in u0])
        u0max = max([np.amax(x) for x in u0])
        center = [u0min + (u0max - u0min)*(i + 0.5)/bins for i in range(bins)]
        frame = pd.DataFrame({'u0': center})
        for i in range(self.m):
            frame[self.states[i]] = np.histogram(u0[i], bins, (u0min, u0max))[0]
        return frame
