"""
Implement the `Prior` and `CombinedPrior` classes.
These define Bayesian priors together with coordinate transformations.
There are two sets of coordinates: "sampled" parameters and "standard"
parameters. Standard parameters are physically interesting, sampled
parameters are chosen to minimize correlations or have convenient
priors.
It is possible to define multiple simple priors, each for a small subset
of the variables, and combine them with `CombinedPrior`.
If separate coordinate systems are not desired, a mix-in class
`IdentityTransformMixin` is provided to short-circuit these transforms.
Another mix-in `UniformPriorMixin` is provided to automatically define
uniform priors.
"""

from abc import ABC, abstractmethod
import inspect
import numpy as np

from . import utils


class PriorError(Exception):
    """Base class for all exceptions in this module"""


class Prior(ABC):
    """"
    Abstract base class to define priors for Bayesian parameter
    estimation, together with coordinate transformations from "sampled"
    parameters to "standard" parameters.

    Schematically,
        lnprior(*sampled_par_vals, *conditioned_on_vals)
            = log P(sampled_par_vals | conditioned_on_vals)
    where P is the prior probability density in the space of sampled
    parameters;
        transform(*sampled_par_vals, *conditioned_on_vals)
            = standard_par_dic
    and
        inverse_transform(*standard_par_vals, *conditioned_on_vals)
            = sampled_par_dic.

    Subclassed by `CombinedPrior` and `FixedPrior`.

    Attributes
    ----------
    range_dic: Dictionary whose keys are sampled parameter names and
               whose values are pairs of floats defining their ranges.
               Needs to be defined by the subclass (either as a class
               attribute or instance attribute) before calling
               `Prior.__init__()`.
    sampled_params: List of sampled parameter names (keys of range_dic)
    standard_params: List of standard parameter names.
    conditioned_on: List of names of parameters on which this prior
                    is conditioned on. To combine priors, conditioned-on
                    parameters need to be among the standard parameters
                    of another prior.
    periodic_params: List of names of sampled parameters that are
                     periodic.
    periodic_inds: List of indices of sampled parameters that are
                   periodic.

    Methods
    -------
    lnprior: Method that takes sampled and conditioned-on parameters
             and returns a float with the natural logarithm of the prior
             probability density in the space of sampled parameters.
             Provided by the subclass.
    transform: Coordinate transformation, function that takes sampled
               parameters and conditioned-on parameters and returns a
               dict of standard parameters. Provided by the subclass.
    lnprior_and_transform: Take sampled parameters and return a tuple
                           with the result of (lnprior, transform).
    inverse_transform: Inverse coordinate transformation, function that
                       takes standard parameters and conditioned-on
                       parameters and returns a dict of sampled
                       parameters. Provided by the subclass.
    """

    periodic_params = []
    conditioned_on = []

    def __init__(self, **kwargs):

        self._check_range_dic()

        self.cubemin = np.array([rng[0] for rng in self.range_dic.values()])
        self.cubemax = np.array([rng[1] for rng in self.range_dic.values()])
        self.cubesize = self.cubemax - self.cubemin
        self.log_volume = np.log(np.prod(self.cubesize))

    @utils.ClassProperty
    def sampled_params(self):
        """List of sampled parameter names."""
        return list(self.range_dic)

    @utils.ClassProperty
    @abstractmethod
    def range_dic(self):
        """
        Dictionary whose keys are sampled parameter names and
        whose values are pairs of floats defining their ranges.
        Needs to be defined by the subclass.
        If the ranges are not known before class instantiation,
        define a class attribute as {'<par_name>': NotImplemented, ...}
        and populate the values at the subclass' `__init__()` before
        calling `Prior.__init__()`.
        """
        return {}

    @utils.ClassProperty
    @abstractmethod
    def standard_params(self):
        """
        List of standard parameter names.
        """
        return []

    @abstractmethod
    def lnprior(self, *par_vals, **par_dic):
        """
        Natural logarithm of the prior probability density.
        Take `self.sampled_params + self.conditioned_on` parameters and
        return a float.
        """

    @abstractmethod
    def transform(self, *par_vals, **par_dic):
        """
        Transform sampled parameter values to standard parameter values.
        Take `self.sampled_params + self.conditioned_on` parameters and
        return a dictionary with `self.standard_params` parameters.
        """

    @abstractmethod
    def inverse_transform(self, *par_vals, **par_dic):
        """
        Transform standard parameter values to sampled parameter values.
        Take `self.standard_params + self.conditioned_on` parameters and
        return a dictionary with `self.sampled_params` parameters.
        """

    def lnprior_and_transform(self, *par_vals, **par_dic):
        """
        Return a tuple with the results of `self.lnprior()` and
        `self.transform()`.
        The reason for this function is that for `CombinedPrior` it is
        already necessary to evaluate `self.transform()` in order to
        evaluate `self.lnprior()`. `CombinedPrior` overwrites this
        function so the user can get both `lnprior` and `transform`
        without evaluating `transform` twice.
        """
        return (self.lnprior(*par_vals, **par_dic),
                self.transform(*par_vals, **par_dic))

    def _check_range_dic(self):
        for key, value in self.range_dic.items():
            if not hasattr(value, '__len__') or len(value) != 2:
                raise PriorError(f'`range_dic` {self.range_dic} needs to have '
                                 'ranges defined as pair of floats.')
            self.range_dic[key] = np.asarray(value, dtype=np.float_)

    @staticmethod
    def get_init_dic():
        """
        Return dictionary with keyword arguments to reproduce the class
        instance. Subclasses should override this method if they require
        initialization parameters.
        """
        return {}

    def __init_subclass__(cls):
        """
        Check that subclasses that change the `__init__` signature also
        define their own `get_init_dic` method."""
        super().__init_subclass__()

        if (inspect.signature(cls.__init__)
                != inspect.signature(Prior.__init__)
                and cls.get_init_dic is Prior.get_init_dic):
            raise PriorError(
                f'{cls.__name__} must override `get_init_dic` method.')


    def __repr__(self):
        """
        Return a string of the form
        `Prior(sampled_params | conditioned_on) → standard_params`.
        """
        rep = self.__class__.__name__ + f'({", ".join(self.sampled_params)}'
        if self.conditioned_on:
            rep += f' | {", ".join(self.conditioned_on)}'
        rep += f') → [{", ".join(self.standard_params)}]'
        return rep

    @classmethod
    def get_fast_sampled_params(cls, fast_standard_params):
        """
        Return a list of parameter names that map to given "fast"
        standard parameters, useful for sampling fast-slow parameters.
        Updating fast sampling parameters is guaranteed to only
        change fast standard parameters.
        """
        if set(cls.standard_params) <= set(fast_standard_params):
            return cls.sampled_params
        return []


class CombinedPrior(Prior):
    """
    Make a new `Prior` subclass combining other `Prior` subclasses.

    Schematically, combine priors like [P(x), P(y|x)] → P(x, y).
    This class has a single abstract method `prior_classes` which is a
    list of `Prior` subclasses that we want to combine.
    Arguments to the `__init__` of the classes in `prior_classes` are
    passed by keyword, so it is important that those arguments have
    repeated names if and only if they are intended to have the same
    value.
    Also, the `__init__` of all classes in `prior_classes` need to
    accept `**kwargs` and forward them to `super().__init__()`.
    """
    @property
    @staticmethod
    @abstractmethod
    def prior_classes():
        """List of `Prior` subclasses with the priors to combine."""

    def __init__(self, *args, **kwargs):
        """
        Instantiate prior classes and define `range_dic`.
        """
        kwargs.update(dict(zip([par.name for par in self._init_parameters()],
                               args)))
        self.subpriors = [cls(**kwargs) for cls in self.prior_classes]
        for subprior in self.subpriors:
            self.range_dic.update(subprior.range_dic)

        super().__init__(**kwargs)

    def __init_subclass__(cls):
        """
        Define the following attributes from the combination of priors
        in `cls.prior_classes`:

            * `range_dic`
            * `standard_params`
            * `periodic_params`
            * `conditioned_on`
            * `lnprior_and_transform`
            * `lnprior`
            * `transform`
            * `inverse_transform`

        which are used to override the corresponding attributes and
        methods of the new `CombinedPrior` subclass.
        """
        super().__init_subclass__()

        sampled_params = [par for prior_class in cls.prior_classes
                          for par in prior_class.sampled_params]
        standard_params = [par for prior_class in cls.prior_classes
                           for par in prior_class.standard_params]
        periodic_params = [par for prior_class in cls.prior_classes
                           for par in prior_class.periodic_params]

        # Check that the provided prior_classes can be combined:
        if len(sampled_params) != len(set(sampled_params)):
            raise PriorError(
                f'Priors {cls.prior_classes} cannot be combined due to '
                f'repeated sampled parameters: {sampled_params}')
        if len(standard_params) != len(set(standard_params)):
            raise PriorError(
                f'Priors {cls.prior_classes} cannot be combined due to '
                f'repeated standard parameters: {standard_params}')
        for i, prior_class in enumerate(cls.prior_classes):
            for following in cls.prior_classes[i:]:
                for conditioned_par in prior_class.conditioned_on:
                    if conditioned_par in following.standard_params:
                        raise PriorError(
                            f'{following} defines {conditioned_par}, which'
                            f'{prior_class} requires. {following} should come '
                            f'before {prior_class}.')

        range_dic = {}
        for prior_class in cls.prior_classes:
            range_dic.update(prior_class.range_dic)

        conditioned_on = [par
                          for prior_class in cls.prior_classes
                          for par in prior_class.conditioned_on
                          if not par in standard_params]

        direct_params = sampled_params + conditioned_on
        inverse_params = standard_params + conditioned_on

        def transform(self, *par_vals, **par_dic):
            """
            Transform sampled parameter values to standard parameter values.
            Take `self.sampled_params + self.conditioned_on` parameters and
            return a dictionary with `self.standard_params` parameters.
            """
            par_dic.update(dict(zip(direct_params, par_vals)))
            for subprior in self.subpriors:
                input_dic = {par: par_dic[par]
                             for par in (subprior.sampled_params
                                         + subprior.conditioned_on)}
                par_dic.update(subprior.transform(**input_dic))
            return {par: par_dic[par] for par in standard_params}

        def inverse_transform(self, *par_vals, **par_dic):
            """
            Transform standard parameter values to sampled parameter values.
            Take `self.standard_params + self.conditioned_on` parameters and
            return a dictionary with `self.sampled_params` parameters.
            """
            par_dic.update(dict(zip(inverse_params, par_vals)))
            for subprior in self.subpriors:
                input_dic = {
                    par: par_dic[par] for par in (subprior.standard_params
                                                  + subprior.conditioned_on)}
                par_dic.update(subprior.inverse_transform(**input_dic))
            return {par: par_dic[par] for par in sampled_params}

        def lnprior_and_transform(self, *par_vals, **par_dic):
            """
            Take sampled and conditioned-on parameters, and return a
            2-element tuple with the log of the prior and a dictionary
            with standard parameters.
            """
            par_dic.update(dict(zip(direct_params, par_vals)))
            standard_par_dic = self.transform(**par_dic)
            par_dic.update(standard_par_dic)

            lnp = 0
            for subprior in self.subpriors:
                input_dic = {par: par_dic[par]
                             for par in (subprior.sampled_params
                                         + subprior.conditioned_on)}
                lnp += subprior.lnprior(**input_dic)
            return lnp, standard_par_dic

        def lnprior(self, *par_vals, **par_dic):
            """
            Natural logarithm of the prior probability density.
            Take `self.sampled_params + self.conditioned_on` parameters
            and return a float.
            """
            return self.lnprior_and_transform(*par_vals, **par_dic)[0]

        # Witchcraft to fix the functions' signatures:
        self_parameter = inspect.Parameter(
            'self', inspect.Parameter.POSITIONAL_ONLY)
        direct_parameters = [self_parameter] + [
            inspect.Parameter(par, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for par in direct_params]
        inverse_parameters = [self_parameter] + [
            inspect.Parameter(par, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for par in inverse_params]
        cls._change_signature(transform, direct_parameters)
        cls._change_signature(inverse_transform, inverse_parameters)
        cls._change_signature(lnprior, direct_parameters)
        cls._change_signature(lnprior_and_transform, direct_parameters)

        cls.range_dic = range_dic
        cls.standard_params = standard_params
        cls.periodic_params = periodic_params
        cls.conditioned_on = conditioned_on
        cls.lnprior_and_transform = lnprior_and_transform
        cls.lnprior = lnprior
        cls.transform = transform
        cls.inverse_transform = inverse_transform

        # Edit the `__init__()` signature of the new subclass:
        cls._change_signature(cls.__init__, cls._init_parameters())

    @classmethod
    def _init_parameters(cls):
        """
        Return list of `inspect.Parameter` objects, for the aggregated
        parameters taken by the `__init__` of `prior_classes`, without
        duplicates and sorted by parameter kind (i.e. positional
        arguments first, keyword arguments last).
        """
        signatures = [inspect.signature(prior_class.__init__)
                      for prior_class in cls.prior_classes]
        all_parameters = [par for signature in signatures
                          for par in signature.parameters.values()]
        sorted_unique_parameters = sorted(
            dict.fromkeys(all_parameters),
            key=lambda par: (par.kind, par.default is not inspect._empty))
        return sorted_unique_parameters

    @staticmethod
    def _change_signature(func, parameters):
        """
        Change the signature of a function to explicitize the parameters
        it takes. Use with caution.

        Parameters
        ----------
        func: function.
        parameters: sequence of `signature.Parameter` objects.
        """
        func.__signature__ = inspect.signature(func).replace(
            parameters=parameters)

    def get_init_dic(self):
        """
        Return dictionary with keyword arguments to reproduce the class
        instance.
        """
        init_dics = [subprior.get_init_dic() for subprior in self.subpriors]
        return utils.merge_dictionaries_safely(init_dics)

    @classmethod
    def get_fast_sampled_params(cls, fast_standard_params):
        """
        Return a list of parameter names that map to given "fast"
        standard parameters, useful for sampling fast-slow parameters.
        Updating fast sampling parameters is guaranteed to only
        change fast standard parameters.
        """
        return [par for prior_class in cls.prior_classes
                for par in prior_class.get_fast_sampled_params(
                    fast_standard_params)]


class FixedPrior(Prior):
    """
    Abstract class to set standard parameters to fixed values.
    Usage: Subclass `FixedPrior` and define a `standard_par_dic`
    attribute.
    """
    @property
    @staticmethod
    @abstractmethod
    def standard_par_dic():
        """Dictionary with fixed parameter names and values."""

    @utils.ClassProperty
    def standard_params(self):
        return list(self.standard_par_dic)

    range_dic = {}

    @staticmethod
    def lnprior():
        """Natural logarithm of the prior probability density."""
        return 0

    def transform(self):
        """Return a fixed dictionary of standard parameters."""
        return self.standard_par_dic

    @staticmethod
    def inverse_transform(**standard_par_dic):
        """Return an empty dictionary of sampled parameters."""
        return {}


class UniformPriorMixin:
    """
    Define `lnprior` for uniform priors.
    It must be inherited before `Prior` (otherwise a `PriorError` is
    raised) so that abstract methods get overriden.
    """
    def lnprior(self, *par_vals, **par_dic):
        """
        Natural logarithm of the prior probability density.
        Take `self.sampled_params + self.conditioned_on` parameters and
        return a float.
        """
        return - self.log_volume

    def __init_subclass__(cls):
        """
        Check that UniformPriorMixin comes before Prior in the MRO.
        """
        check_inheritance_order(cls, UniformPriorMixin, Prior)


class IdentityTransformMixin:
    """
    Define `transform` and `inverse_transform` for priors where sampled
    parameters and standard parameters are the same.
    It must be inherited before `Prior` (otherwise a `PriorError` is
    raised) so that abstract methods get overriden.
    """
    def __init_subclass__(cls):
        """
        Check that subclasses have same sampled and standard parameters,
        and that IdentityTransformMixin comes before Prior in the MRO.
        """
        super().__init_subclass__()
        if set(cls.sampled_params) != set(cls.standard_params):
            raise PriorError('This prior does not have an identity transform.')

        check_inheritance_order(cls, IdentityTransformMixin, Prior)

    def transform(self, *par_vals, **par_dic):
        """
        Transform sampled parameter values to standard parameter values.
        Take `self.sampled_params + self.conditioned_on` parameters and
        return a dictionary with `self.standard_params` parameters.
        """
        par_dic.update(dict(zip(self.sampled_params + self.conditioned_on,
                                par_vals)))
        return {par: par_dic[par] for par in self.standard_params}

    inverse_transform = transform


def check_inheritance_order(subclass, base1, base2):
    """
    Check that class `subclass` subclasses `base1` and `base2`, in that
    order. If it doesn't, raise `PriorError`.
    """
    for base in base1, base2:
        if not issubclass(subclass, base):
            raise PriorError(
                f'{subclass.__name__} must subclass {base.__name__}')

    if subclass.mro().index(base1) > subclass.mro().index(base2):
        raise PriorError(f'Wrong inheritance order: `{subclass.__name__}` '
                         f'must inherit from `{base1.__name__}` before '
                         f'`{base2.__name__}` (or their subclasses).')
