"""
Post-process parameter estimation samples:
    * Compute derived parameters
    * Compute likelihood
    * Diagnostics for sampler convergence
    * Diagnostics for robustness against ASD-drift choice
    * Diagnostics for relative-binning accuracy

The function `postprocess_rundir` is used to process samples from a
single parameter estimation run.
"""

import copy
import json
import pathlib
from pstats import Stats
from scipy.cluster.vq import kmeans
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import matplotlib as mpl
import pandas as pd

from . import grid
from . import utils
from .sampling import Sampler, SAMPLES_FILENAME

TESTS_FILENAME = 'postprocessing_tests.json'


def concat_drop_duplicates(df1, df2):
    """
    Concatenate DataFrames by columns, dropping repeated columns
    from df2.
    """
    cols_to_use = df2.columns.difference(df1.columns)
    return pd.concat([df1, df2[cols_to_use]], axis=1)


def postprocess_rundir(rundir, relative_binning_boost=4):
    """
    Postprocess posterior samples from a single run.

    This computes:
        * Columns for standard parameters
        * Column for log likelihood
        * Auxiliary columns for log likelihood (by detector, at high
          relative binning resolution and with no ASD-drift
          correction applied)
        * Tests for log likelihood differences arising from
          reference waveform choice for setting ASD-drift
        * Tests for log likelihood differences arising from
          relative binning accuracy.
    """
    PostProcessor(rundir, relative_binning_boost).process_samples()


class PostProcessor:
    """
    Postprocess posterior samples from a single run.

    The method `process_samples` executes all the functionality of the
    class. It is suggested to use the top-level function
    `postprocess_rundir` for simple usage.
    """
    LNL_COL = 'lnl'

    def __init__(self, rundir, relative_binning_boost: int=4):
        super().__init__()

        self.rundir = pathlib.Path(rundir)
        self.relative_binning_boost = relative_binning_boost

        sampler = utils.read_json(self.rundir/Sampler.JSON_FILENAME)
        self.posterior = sampler.posterior
        self.samples = pd.read_feather(self.rundir/SAMPLES_FILENAME)

        try:
            with open(self.rundir/TESTS_FILENAME) as file:
                self.tests = json.load(file)
        except FileNotFoundError:
            self.tests = {'asd_drift': [],
                          'relative_binning': {},
                          'lnl_max': None,
                          'lnl_0': self.posterior.likelihood._lnl_0}

        self._lnl_aux_cols = self.get_lnl_aux_cols(
            self.posterior.likelihood.event_data.detector_names)

        self._asd_drifts_subset = None

    @staticmethod
    def get_lnl_aux_cols(detector_names):
        """
        Return names of auxiliary log likelihood columns.
        """
        return [f'lnl_aux_{det}' for det in detector_names]

    def process_samples(self):
        """
        Call the various methods of the class sequentially, then save
        the results. This computes:
            * Columns for standard parameters
            * Column for log likelihood
            * Auxiliary columns for log likelihood (by detector, at high
              relative binning resolution and with no ASD-drift
              correction applied)
            * Tests for log likelihood differences arising from
              reference waveform choice for setting ASD-drift
            * Tests for log likelihood differences arising from
              relative binning accuracy.
        """
        print(f'Processing {self.rundir}')

        print(' * Adding standard parameters...')
        self.add_standard_parameters()
        print(' * Computing relative-binning likelihood...')
        self.compute_lnl()
        print(' * Computing auxiliary likelihood products...')
        self.compute_lnl_aux()
        print(' * Testing ASD-drift correction...')
        self.test_asd_drift()
        print(' * Testing relative binning...')
        self.test_relative_binning()
        self.save_tests_and_samples()

    def add_standard_parameters(self):
        """
        Add columns for `standard_params` to `self.samples`.
        """
        standard = pd.DataFrame([self.posterior.prior.transform(**sample)
                                 for _, sample in self.samples.iterrows()])
        self.samples = concat_drop_duplicates(self.samples, standard)

    def compute_lnl(self):
        """
        Add column to `self.samples` with log likelihood computed
        at original relative binning resolution
        """
        self.samples[self.LNL_COL] = list(
            map(self.posterior.likelihood.lnlike, self._standard_samples()))
        self.tests['lnl_max'] = max(self.samples[self.LNL_COL])

    def compute_lnl_aux(self):
        """
        Add columns `self._lnl_aux_cols` to `self.samples` with log
        likelihood computed by detector, at high relative binning
        resolution, with no ASD-drift correction applied.
        """
        # Increase the relative-binning frequency resolution:
        likelihood = copy.deepcopy(self.posterior.likelihood)
        if likelihood.pn_phase_tol:
            likelihood.pn_phase_tol /= self.relative_binning_boost
        else:
            likelihood.fbin = np.interp(
                np.linspace(0, 1, (self.relative_binning_boost
                                   * len(likelihood.fbin) - 1) + 1),
                np.linspace(0, 1, len(likelihood.fbin)),
                likelihood.fbin)

        lnl_aux = pd.DataFrame(map(likelihood.lnlike_detectors_no_asd_drift,
                                   self._standard_samples()),
                               columns=self._lnl_aux_cols)
        self.samples = concat_drop_duplicates(self.samples, lnl_aux)

    def test_asd_drift(self):
        """
        Compute typical and worse-case log likelihood differences
        arising from the choice of somewhat-parameter-dependent
        asd_drift correction. Store in `self.tests['asd_drift']`.
        """
        ref_lnl = self._apply_asd_drift(self.posterior.likelihood.asd_drift)
        for asd_drift in self._get_representative_asd_drifts():
            lnl = self._apply_asd_drift(asd_drift)
            # Difference in log likelihood from changing asd_drift:
            dlnl = lnl - lnl.mean() - (ref_lnl - ref_lnl.mean())
            self.tests['asd_drift'].append({'asd_drift': asd_drift,
                                            'dlnl_std': np.std(dlnl),
                                            'dlnl_max': np.max(np.abs(dlnl))})

    def test_relative_binning(self):
        """
        Compute typical and worst-case errors in log likelihood due to
        relative binning. Store in `self.tests['relative_binning']`.
        """
        dlnl = (self.samples[self.LNL_COL]
                - self._apply_asd_drift(self.posterior.likelihood.asd_drift))
        self.tests['relative_binning'] = {'dlnl_std': np.std(dlnl),
                                          'dlnl_max': np.max(np.abs(dlnl))}

    def save_tests_and_samples(self):
        """Save `self.tests` and `self.samples` in `self.rundir`."""
        with open(self.rundir/TESTS_FILENAME, 'w') as file:
            json.dump(self.tests, file)

        self.samples.to_feather(self.rundir/SAMPLES_FILENAME)

    def _get_representative_asd_drifts(self, n_kmeans=5, n_subset=100,
                                       decimals=3):
        """
        Return `n_kmeans` sets of `asd_drift` generated with via k-means
        from the asd_drift of `n_subset` random samples.
        Each asd_drift is a float array of length n_detectors.
        asd_drifts are rounded to `decimals` places.
        """
        if (self._asd_drifts_subset is None
                or len(self._asd_drifts_subset) != n_subset):
            self._gen_asd_drifts_subset(n_subset)

        return np.round(kmeans(self._asd_drifts_subset, n_kmeans)[0], decimals)

    def _apply_asd_drift(self, asd_drift):
        """
        Return series of length n_samples with log likelihood for the
        provided `asd_drift`.

        Parameters
        ----------
        asd_drift: float array of length n_detectors.
        """
        return self.samples[self._lnl_aux_cols] @ asd_drift**-2

    def _gen_asd_drifts_subset(self, n_subset):
        """
        Compute asd_drifts for a random subset of the samples, store
        them in `self._asd_drifts_subset`.
        """
        self._asd_drifts_subset = list(
            map(self.posterior.likelihood.compute_asd_drift,
                self._standard_samples(self.samples.sample(n_subset))))

    def _standard_samples(self, samples=None):
        """Iterator over standard parameter samples."""
        samples = samples if samples is not None else self.samples
        return (sample for _, sample in samples[
            self.posterior.likelihood.waveform_generator.params].iterrows())


def diagnostics(eventdir, reference_rundir=None, outfile=None):
    """
    Make diagnostics plots aggregating multiple runs of an event and
    save them to pdf format.
    These include a summary table of the parameters of the runs,
    number of samples vs time to completion, and corner plots comparing
    each run to a reference one.

    Parameters
    ----------
    reference_rundir: path to rundir used as reference against which to
                      overplot samples. Defaults to the first rundir by
                      name.
    outfile: path to save output as pdf. Defaults to
             `{eventdir}/{Diagnostics.DIAGNOSTICS_FILENAME}`.
    """
    Diagnostics(eventdir, reference_rundir).diagnostics(outfile)


class Diagnostics:
    """
    Class to gather information from multiple runs of an event and
    exporting summary to pdf file.

    The method `diagnostics` executes all the functionality of the
    class. It is suggested to use the top-level function `diagnostics`
    for simple usage.
    """
    DIAGNOSTICS_FILENAME = 'diagnostics.pdf'
    DEFAULT_TOLERANCE_PARAMS = {'asd_drift_dlnl_std': .1,
                                'asd_drift_dlnl_max': .5,
                                'lnl_max_exceeds_lnl_0': 5.,
                                'lnl_0_exceeds_lnl_max': .1,
                                'relative_binning_dlnl_std': .05,
                                'relative_binning_dlnl_max': .25}
    _LABELS = {
      'nsamples': r'$N_\mathrm{samples}$',
      'runtime': 'Runtime (h)',
      'asd_drift_dlnl_std': r'$\sigma(\Delta_{\rm ASD\,drift}\ln\mathcal{L})$',
      'asd_drift_dlnl_max': r'$\max|\Delta_{\rm ASD\,drift}\ln\mathcal{L}|$',
      'lnl_max': r'$\max \ln\mathcal{L}$',
      'lnl_0': r'$\ln\mathcal{L}_0$',
      'relative_binning_dlnl_std': r'$\sigma(\Delta_{\rm RB}\ln\mathcal{L})$',
      'relative_binning_dlnl_max': r'$\max|\Delta_{\rm RB}\ln\mathcal{L}|$'}

    def __init__(self, eventdir, reference_rundir=None,
                 tolerance_params=None):
        """
        Parameters
        ----------
        eventdir: path to directory containing rundirs.
        reference_rundir: path to reference run directory. Defaults to
                          the first (by name) rundir in `eventdir`.
        tolerance_params: dict with items to update the defaults from
                          `TOLERANCE_PARAMS`. Values higher than their
                          tolerance are highlighted in the table.
                          Keys include:
            * 'asd_drift_dlnl_std'
                Tolerable standard deviation of log likelihood
                fluctuations due to choice of reference waveform for
                ASD-drift.

            * 'asd_drift_dlnl_max'
                Tolerable maximum log likelihood fluctuation due to
                choice of reference waveform for ASD-drift.

            * 'lnl_max_exceeds_lnl_0'
                Tolerable amount by which the log likelihood of the best
                sample may exceed that of the reference waveform.

            * 'lnl_0_exceeds_lnl_max'
                Tolerable amount by which the log likelihood of the
                reference waveform may exceed that of the best sample.

            * 'relative_binning_dlnl_std'
                Tolerable standard deviation of log likelihood
                fluctuations due to the relative binning approximation.

            * 'relative_binning_dlnl_max'
                Tolerable maximum log likelihood fluctuation due to
                the relative binning approximation.
        """
        self.eventdir = pathlib.Path(eventdir)
        self.rundirs = self.get_rundirs()
        self.table = self.make_table()
        self.reference_rundir = reference_rundir
        self.tolerance_params = (self.DEFAULT_TOLERANCE_PARAMS
                                 | (tolerance_params or {}))

    def diagnostics(self, outfile=None):
        """
        Make diagnostics plots aggregating multiple runs of an event and
        save them to pdf format in `{eventdir}/{DIAGNOSTICS_FILENAME}`.
        These include a summary table of the parameters of the runs,
        number of samples vs time to completion, and corner plots comparing
        each run to a reference one.
        """
        outfile = outfile or self.eventdir/self.DIAGNOSTICS_FILENAME
        print(f'Diagnostic plots will be saved to "{outfile}"...')

        if self.reference_rundir:
            # Move reference_rundir to front:
            self.rundirs.insert(0, self.rundirs.pop(self.rundirs.index(
                pathlib.Path(self.reference_rundir))))

        with PdfPages(outfile) as pdf:
            self._display_table()
            plt.title(self.eventdir)
            pdf.savefig(bbox_inches='tight')

            self._scatter_nsamples_vs_runtime()
            pdf.savefig(bbox_inches='tight')

            refdir, *otherdirs = self.rundirs
            ref_samples = pd.read_feather(refdir/'samples.feather')
            ref_grid = grid.Grid.from_samples(list(ref_samples), ref_samples,
                                              pdf_key=refdir.name)

            par_dic_0 = (utils.read_json(refdir/Sampler.JSON_FILENAME)
                         .posterior.likelihood.par_dic_0)

            for otherdir in otherdirs:
                other_samples = pd.read_feather(otherdir/'samples.feather')
                other_grid = grid.Grid.from_samples(
                    list(other_samples), other_samples, pdf_key=otherdir.name)

                grid.MultiGrid([ref_grid, other_grid]).corner_plot(
                    figsize=(10, 10), set_legend=True,
                    scatter_points=par_dic_0)
                pdf.savefig(bbox_inches='tight')

    def get_rundirs(self):
        """
        Return a list of rundirs in `self.eventdir` for which sampling
        has completed. Ignores incomplete runs, printing a warning.
        """
        rundirs = []
        for rundir in sorted(self.eventdir.glob(Sampler.RUNDIR_PREFIX + '*')):
            if (rundir/TESTS_FILENAME).exists():
                rundirs.append(rundir)
            else:
                print(f'{rundir} was not post-processed, excluding.')
        return rundirs

    def make_table(self, rundirs=None):
        """
        Return a pandas DataFrame with a table that summarizes the
        different runs in `rundirs`.
        The columns report the differences in the samplers' `run_kwargs`,
        plus the runtime and number of samples of each run.

        Parameters
        ----------
        rundirs: sequence of `pathlib.Path`s pointing to run directories.
        """
        rundirs = rundirs or self.rundirs

        table = pd.DataFrame()
        table['run'] = [x.name for x in rundirs]
        table = concat_drop_duplicates(table, self._collect_run_kwargs(rundirs))
        table['n_samples'] = [len(pd.read_feather(rundir/SAMPLES_FILENAME))
                              for rundir in rundirs]
        table['runtime'] = [
            Stats(str(rundir/Sampler.PROFILING_FILENAME)).total_tt / 3600
            for rundir in rundirs]
        table = concat_drop_duplicates(table, self._collect_tests(rundirs))

        return table

    @staticmethod
    def _collect_run_kwargs(rundirs):
        """Return a DataFrame aggregating run_kwargs used in sampling."""
        run_kwargs = []
        for rundir in rundirs:
            with open(rundir/Sampler.JSON_FILENAME) as sampler_file:
                dic = json.load(sampler_file)['init_kwargs']
                run_kwargs.append({**dic['run_kwargs'],
                                   'sample_prior': dic['sample_prior']})

        run_kwargs = pd.DataFrame(run_kwargs)
        const_cols = [col for col, (first, *others) in run_kwargs.iteritems()
                      if all(first == other for other in others)]
        drop_cols = const_cols + ['outputfiles_basename']
        return run_kwargs.drop(columns=drop_cols, errors='ignore')

    @staticmethod
    def _collect_tests(rundirs):
        """Return a DataFrame aggregating postprocessing tests."""
        tests = []
        for rundir in rundirs:
            with open(rundir/TESTS_FILENAME) as tests_file:
                dic = json.load(tests_file)['init_kwargs']

                asd_drift_dlnl_std = np.sqrt(np.mean(
                    val['dlnl_std']**2 for val in dic['asd_drift'].values()))

                asd_drift_dlnl_max = np.max(
                    val['dlnl_max'] for val in dic['asd_drift'].values())

                tests.append({'lnl_max': dic['lnl_max'],
                              'lnl_0': dic['lnl_0'],
                              'asd_drift_dlnl_std': asd_drift_dlnl_std,
                              'asd_drift_dlnl_max': asd_drift_dlnl_max,
                              'relative_binning_dlnl_std':
                                  dic['relative_binning']['dlnl_std'],
                              'relative_binning_dlnl_max':
                                  dic['relative_binning']['dlnl_max']})
        return pd.DataFrame(tests)

    def _display_table(self, cell_size=(1., .3)):
        """Make a matplotlib figure and display the table in it."""
        tests = self.table[['asd_drift_dlnl_std',
                            'asd_drift_dlnl_max',
                            'relative_binning_dlnl_std',
                            'relative_binning_dlnl_max']].copy()
        tests['lnl_max_exceeds_lnl_0'] = (self.table['lnl_max']
                                          - self.table['lnl_0'])
        tests['lnl_0_exceeds_lnl_max'] = (self.table['lnl_0']
                                          - self.table['lnl_max'])

        cell_colors = self.table.copy()
        cell_colors[::2] = 'whitesmoke'
        cell_colors[1::2] = 'w'
        for key, tol in self.tolerance_params.items():
            # yellow = 1x tolerance, red = 2x tolerance
            cell_colors[key] = list(mpl.cm.RdYlGn_r(tests[key] / tol / 2, .3))

        nrows, ncols = self.table.shape
        _, ax = plt.subplots(figsize=np.multiply((ncols, nrows+1), cell_size))
        ax.axis([0, 1, nrows, -1])

        tab = plt.table(
            self.table.round(2).to_numpy(),
            colLabels=self.table.rename(columns=self._LABELS).columns,
            loc='center',
            cellColours=cell_colors.to_numpy(),
            bbox=[0, 0, 1, 1])

        for cell in tab._cells.values():
            cell.set_edgecolor(None)

        tab.auto_set_column_width(range(ncols))

        plt.axhline(0, color='k', lw=1)
        plt.axis('off')
        plt.tight_layout()

    def _scatter_nsamples_vs_runtime(self):
        """Scatter plot number of samples vs runtime from `table`."""
        plt.figure()
        xpar, ypar = 'runtime', 'n_samples'
        plt.scatter(self.table[xpar], self.table[ypar])
        for run, *x_y in self.table[['run', xpar, ypar]].to_numpy():
            plt.annotate(run.lstrip(Sampler.RUNDIR_PREFIX), x_y,
                         fontsize='large')
        plt.grid()
        plt.xlim(0)
        plt.ylim(0)
        plt.xlabel(xpar)
        plt.ylabel(ypar)
