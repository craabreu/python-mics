"""
.. module:: mixtures
   :platform: Unix, Windows
   :synopsis: a module for defining the class :class:`Mixture`.

.. moduleauthor:: Charlles R. A. Abreu <abreu@eq.ufrj.br>


"""

import numpy as np
import pandas as pd
from numpy.linalg import multi_dot

import mics as mx
from mics.utils import cases
from mics.utils import genfunc
from mics.utils import info
from mics.utils import jacobian
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

        neff = self.neff = np.array([s.neff for s in samples])
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
    def free_energies(self, reference=0):
        """
        Returns a data frame containing the relative free energies of the datasetd samples
        of a `mixture`, as well as their standard errors.

        """
        frame = self.frame.copy()
        frame['f'] = self.f - self.f[reference]
        T = self.Theta
        frame['df'] = np.sqrt(np.diag(T) - 2*T[:, reference] + T[reference, reference])
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
        info(self.verbose, "Potential:", potential)

        functions = [genfunc(p, self.names, **kwargs) for p in properties.values()]
        y = [multimap(functions, s.dataset) for s in self.samples]

        names = list(properties.keys())
        try:
            func, Jac = jacobian(combinations.values(), names, kwargs)
            jacobian_needed = False
        except:
            jacobian_needed = True

        results = list()
        for constants in cases(potential, conditions, kwargs, self.verbose):
            potfunc = genfunc(potential, self.names, **constants)
            u = [multimap([potfunc], s.dataset) for s in self.samples]

            yu, Theta = self._reweight(u, y)
            dyu = np.sqrt(np.diagonal(Theta))

            if (combinations):
                if jacobian_needed:
                    func, Jac = jacobian(combinations.values(), names, constants)
                g = func(yu).flatten()
                J = Jac(yu)
                dg = np.sqrt(np.diagonal(multi_dot([J, Theta, J.T])))
                results.append(np.block([[yu, g], [dyu, dg]]).T.flatten())
            else:
                results.append(np.stack([yu, dyu]).T.flatten())

        header = sum([[p, 'd'+p] for p in names + list(combinations.keys())], [])
        frame = pd.DataFrame(results, columns=header)

        return pd.concat([conditions, frame], axis=1)

    # ======================================================================================
    def fep(self, potential, conditions=pd.DataFrame(), reference=0, **kwargs):
        """
        Performs free energy perturbation.

        Args:
            potential (function/string):
            conditions (pandas.DataFrame):
            **kwargs:

        """
        info(self.verbose, "Potential:", potential)
        results = list()
        for constants in cases(potential, conditions, kwargs, self.verbose):
            potfunc = genfunc(potential, self.names, **constants)
            u = [multimap([potfunc], s.dataset) for s in self.samples]
            results.append(self._perturbation(u, reference))
        frame = pd.DataFrame(results, columns=['f', 'df'])
        return pd.concat([conditions, frame], axis=1)

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
