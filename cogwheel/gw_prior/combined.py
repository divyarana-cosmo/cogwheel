"""
Define some commonly used priors for the full set of parameters, for
convenience.

Prior classes defined here can be used for parameter estimation and
are registered in a dictionary ``prior_registry``.
"""

from cogwheel.prior import CombinedPrior, Prior, check_inheritance_order

from .extrinsic import (UniformPhasePrior,
                        IsotropicInclinationPrior,
                        IsotropicSkyLocationPrior,
                        UniformTimePrior,
                        UniformPolarizationPrior,
                        UniformLuminosityVolumePrior,
                        UniformComovingVolumePrior,
                        UniformComovingVolumePriorSampleEffectiveDistance)

from .mass import (UniformDetectorFrameMassesPrior,
                   UniformSourceFrameTotalMassInverseMassRatioPrior)

from .miscellaneous import (ZeroTidalDeformabilityPrior,
                            FixedIntrinsicParametersPrior,
                            FixedReferenceFrequencyPrior)

from .spin import (UniformEffectiveSpinPrior,
                   UniformDiskInplaneSpinsPrior,
                   IsotropicSpinsAlignedComponentsPrior,
                   IsotropicSpinsInplaneComponentsPrior,
                   UniformDiskInplaneSpinsInclinationPhaseSkyLocationTimePrior,
                   ZeroInplaneSpinsPrior)

prior_registry = {}


class ConditionedPriorError(Exception):
    """Indicates that a Prior is conditioned on some parameters."""


class ReferenceWaveformFinderMixin:
    """
    Provide a constructor based on a `likelihood.ReferenceWaveformFinder`
    instance to provide initialization arguments.
    """
    @classmethod
    def from_reference_waveform_finder(
            cls, reference_waveform_finder, **kwargs):
        """
        Instantiate `prior.Prior` subclass with help from a
        `likelihood.ReferenceWaveformFinder` instance.
        This will generate kwargs for:
            * tgps
            * par_dic
            * f_avg
            * f_ref
            * ref_det_name
            * detector_pair
            * t0_refdet
            * mchirp_range
        Additional `**kwargs` can be passed to complete missing entries
        or override these.
        """
        return cls(**reference_waveform_finder.get_coordinate_system_kwargs()
                   | kwargs)


class RegisteredPriorMixin(ReferenceWaveformFinderMixin):
    """
    Register existence of a `Prior` subclass in `prior_registry`.
    Intended usage is to only register the final priors (i.e., for the
    full set of GW parameters).
    `RegisteredPriorMixin` should be inherited before `Prior` (otherwise
    `PriorError` is raised) in order to test for conditioned-on
    parameters.
    """
    def __init_subclass__(cls):
        """Validate subclass and register it in prior_registry."""
        super().__init_subclass__()
        check_inheritance_order(cls, RegisteredPriorMixin, Prior)

        if cls.conditioned_on:
            raise ConditionedPriorError('Only register fully defined priors.')

        prior_registry[cls.__name__] = cls


# ----------------------------------------------------------------------
# Default priors for the full set of variables, for convenience.

class IASPrior(RegisteredPriorMixin, CombinedPrior):
    """Precessing, flat in chieff, uniform luminosity volume."""
    prior_classes = [
        FixedReferenceFrequencyPrior,
        UniformDetectorFrameMassesPrior,
        UniformEffectiveSpinPrior,
        UniformPolarizationPrior,
        UniformDiskInplaneSpinsInclinationPhaseSkyLocationTimePrior,
        UniformLuminosityVolumePrior,
        ZeroTidalDeformabilityPrior]


# class IASPriorLSystem(RegisteredPriorMixin, CombinedPrior):
#     """
#     Precessing, flat in chieff, uniform luminosity volume.
#     Physically equivalent to IASPrior, but using L (the orbital angular
#     momentum at `f_ref`) as opposed to J (the total angular momentum at
#     `f_ref`) to define azimuths for spins and zenith for direction of
#     propagation. In practice, spin azimuths are slightly worse measured
#     but the orbital phase becomes a fast parameter.
#     """
#     prior_classes = [UniformDetectorFrameMassesPrior,
#                      UniformPhasePrior,
#                      IsotropicInclinationPrior,
#                      IsotropicSkyLocationPrior,
#                      UniformTimePrior,
#                      UniformPolarizationPrior,
#                      UniformLuminosityVolumePrior,
#                      UniformEffectiveSpinPrior,
#                      UniformDiskInplaneSpinsPrior,
#                      ZeroTidalDeformabilityPrior,
#                      FixedReferenceFrequencyPrior]


class AlignedSpinIASPrior(RegisteredPriorMixin, CombinedPrior):
    """Aligned spin, flat in chieff, uniform luminosity volume."""
    prior_classes = [UniformDetectorFrameMassesPrior,
                     IsotropicInclinationPrior,
                     IsotropicSkyLocationPrior,
                     UniformTimePrior,
                     UniformPolarizationPrior,
                     UniformPhasePrior,
                     UniformLuminosityVolumePrior,
                     UniformEffectiveSpinPrior,
                     ZeroInplaneSpinsPrior,
                     ZeroTidalDeformabilityPrior,
                     FixedReferenceFrequencyPrior]


class LVCPrior(RegisteredPriorMixin, CombinedPrior):
    """Precessing, isotropic spins, uniform luminosity volume."""
    prior_classes = [UniformDetectorFrameMassesPrior,
                     IsotropicInclinationPrior,
                     IsotropicSkyLocationPrior,
                     UniformTimePrior,
                     UniformPolarizationPrior,
                     UniformPhasePrior,
                     UniformLuminosityVolumePrior,
                     IsotropicSpinsAlignedComponentsPrior,
                     IsotropicSpinsInplaneComponentsPrior,
                     ZeroTidalDeformabilityPrior,
                     FixedReferenceFrequencyPrior]


class AlignedSpinLVCPrior(RegisteredPriorMixin, CombinedPrior):
    """
    Aligned spin components from isotropic distribution, uniform
    luminosity volume.
    """
    prior_classes = [UniformDetectorFrameMassesPrior,
                     IsotropicInclinationPrior,
                     IsotropicSkyLocationPrior,
                     UniformTimePrior,
                     UniformPolarizationPrior,
                     UniformPhasePrior,
                     UniformLuminosityVolumePrior,
                     IsotropicSpinsAlignedComponentsPrior,
                     ZeroInplaneSpinsPrior,
                     ZeroTidalDeformabilityPrior,
                     FixedReferenceFrequencyPrior]


class IASPriorComovingVT(RegisteredPriorMixin, CombinedPrior):
    """Precessing, flat in chieff, uniform comoving VT."""
    prior_classes = [
        FixedReferenceFrequencyPrior,
        UniformDetectorFrameMassesPrior,
        UniformEffectiveSpinPrior,
        UniformPolarizationPrior,
        UniformDiskInplaneSpinsInclinationPhaseSkyLocationTimePrior,
        UniformComovingVolumePrior,
        ZeroTidalDeformabilityPrior]


class AlignedSpinIASPriorComovingVT(RegisteredPriorMixin,
                                    CombinedPrior):
    """Aligned spin, flat in chieff, uniform comoving VT."""
    prior_classes = [UniformDetectorFrameMassesPrior,
                     IsotropicInclinationPrior,
                     IsotropicSkyLocationPrior,
                     UniformTimePrior,
                     UniformPolarizationPrior,
                     UniformPhasePrior,
                     UniformComovingVolumePrior,
                     UniformEffectiveSpinPrior,
                     ZeroInplaneSpinsPrior,
                     ZeroTidalDeformabilityPrior,
                     FixedReferenceFrequencyPrior]


# class LVCPriorComovingVT(RegisteredPriorMixin, CombinedPrior):
#     """Precessing, isotropic spins, uniform comoving VT."""
#     prior_classes = [UniformDetectorFrameMassesPrior,
#                      UniformPhasePrior,
#                      IsotropicInclinationPrior,
#                      IsotropicSkyLocationPrior,
#                      UniformTimePrior,
#                      UniformPolarizationPrior,
#                      UniformComovingVolumePrior,
#                      IsotropicSpinsAlignedComponentsPrior,
#                      IsotropicSpinsInplaneComponentsPrior,
#                      ZeroTidalDeformabilityPrior,
#                      FixedReferenceFrequencyPrior]


# class AlignedSpinLVCPriorComovingVT(RegisteredPriorMixin,
#                                     CombinedPrior):
#     """
#     Aligned spins from isotropic distribution, uniform comoving VT.
#     """
#     prior_classes = [UniformDetectorFrameMassesPrior,
#                      UniformPhasePrior,
#                      IsotropicInclinationPrior,
#                      IsotropicSkyLocationPrior,
#                      UniformTimePrior,
#                      UniformPolarizationPrior,
#                      UniformComovingVolumePrior,
#                      IsotropicSpinsAlignedComponentsPrior,
#                      ZeroInplaneSpinsPrior,
#                      ZeroTidalDeformabilityPrior,
#                      FixedReferenceFrequencyPrior]


# class NitzMassIASSpinPrior(RegisteredPriorMixin, CombinedPrior):
#     """
#     Priors are uniform in source-frame total mass, inverse mass ratio,
#     effective spin, and comoving VT.
#     Sampling is in mtot_source, lnq, d_effective, and the rest of the
#     IAS spin and extrinsic parameters.
#     """
#     prior_classes = [UniformPhasePrior,
#                      IsotropicInclinationPrior,
#                      IsotropicSkyLocationPrior,
#                      UniformTimePrior,
#                      UniformPolarizationPrior,
#                      UniformComovingVolumePriorSampleEffectiveDistance,
#                      UniformSourceFrameTotalMassInverseMassRatioPrior,
#                      UniformEffectiveSpinPrior,
#                      UniformDiskInplaneSpinsPrior,
#                      ZeroTidalDeformabilityPrior,
#                      FixedReferenceFrequencyPrior]


# class NitzMassLVCSpinPrior(RegisteredPriorMixin, CombinedPrior):
#     """
#     Priors have isotropic spins and are uniform in source-frame total
#     mass, inverse mass ratio, and comoving VT.
#     Sampling is in mtot_source, lnq, d_effective, and the rest of the
#     LVC spin and extrinsic parameters.
#     """
#     prior_classes = [UniformPhasePrior,
#                      IsotropicInclinationPrior,
#                      IsotropicSkyLocationPrior,
#                      UniformTimePrior,
#                      UniformPolarizationPrior,
#                      UniformComovingVolumePriorSampleEffectiveDistance,
#                      UniformSourceFrameTotalMassInverseMassRatioPrior,
#                      IsotropicSpinsAlignedComponentsPrior,
#                      IsotropicSpinsInplaneComponentsPrior,
#                      ZeroTidalDeformabilityPrior,
#                      FixedReferenceFrequencyPrior]


class ExtrinsicParametersPrior(RegisteredPriorMixin, CombinedPrior):
    """Uniform luminosity volume, fixed intrinsic parameters."""
    prior_classes = [FixedIntrinsicParametersPrior,
                     IsotropicInclinationPrior,
                     IsotropicSkyLocationPrior,
                     UniformTimePrior,
                     UniformPolarizationPrior,
                     UniformPhasePrior,
                     UniformLuminosityVolumePrior,
                     FixedReferenceFrequencyPrior]
