"""Class to run MR on SIMBAD results"""

from __future__ import division

__author__ = "Adam Simpkin"
__date__ = "09 Mar 2017"
__version__ = "1.0"

import logging
import os

from pyjob import pool
from pyjob.script import ScriptCollector, Script
from pyjob.exception import PyJobExecutionError

from simbad.mr import anomalous_util
from simbad.mr.options import MrPrograms, RefPrograms
from simbad.parsers import molrep_parser
from simbad.parsers import phaser_parser
from simbad.parsers import refmac_parser
from simbad.util import source_ccp4
from simbad.util import submit_chunk
from simbad.util import tmp_file
from simbad.util import mtz_util
from simbad.util.pdb_util import PdbStructure
from simbad.util.matthews_prob import MatthewsProbability, SolventContent

from simbad.core.lattice_score import LatticeSearchResult
from simbad.core.amore_score import AmoreRotationScore
from simbad.core.phaser_score import PhaserRotationScore
from simbad.core.mr_score import MrScore

logger = logging.getLogger(__name__)

EXPORT = "SET" if os.name == "nt" else "export"
CMD_PREFIX = "call" if os.name == "nt" else ""


class MrSubmit(object):
    """Class to run MR on a defined set of models

    Attributes
    ----------
    mtz : str
        Path to the input MTZ file
    mr_program : str
        Name of the molecular replacement program to use
    refine_program : str
        Name of the refinement program to use
    refine_type : str
        Type of refinement to run (None | jelly)
    refine_cycles : int
        The number of refinement cycles (default: 30)
    output_dir : str
        Path to the directory to output results
    sgalternative : str
        Specify whether to try alternative space groups (all | enant)
    results : obj
        Results from :obj: '_LatticeParameterScore' or :obj: '_AmoreRotationScore'

    Examples
    --------
    >>> from simbad.mr import MrSubmit
    >>> MR = MrSubmit('<mtz>', '<mr_program>', '<refine_program>', '<refine_type>', '<output_dir>', '<sgalternative>')
    >>> MR.submit_jobs('<results>', '<nproc>', '<submit_cluster>', '<submit_qtype>', '<submit_queue>',
    ...                '<submit_array>', '<submit_max_array>', '<process_all>', '<monitor>')

    If a solution is found and process_all is not set, the queued jobs will be terminated.
    """

    def __init__(
        self,
        mtz,
        mr_program,
        refine_program,
        refine_type,
        refine_cycles,
        output_dir,
        tmp_dir,
        timeout,
        sgalternative=None,
    ):
        """Initialise MrSubmit class"""
        self.input_file = None
        self._process_all = None
        self._sgalternative = None
        self._mtz = None
        self._mr_program = None
        self._output_dir = None
        self._refine_program = None
        self._refine_type = None
        self._refine_cycles = None
        self._search_results = []
        self._timeout = None

        # options derived from the input mtz
        self._cell_parameters = None
        self._resolution = None
        self._space_group = None
        self._mtz_labels = None

        self.dano_columns = []
        self.sgalternative = sgalternative
        self.mat_prob = None
        self.mtz = mtz
        self.mr_program = mr_program
        self.mute = False
        self.output_dir = output_dir
        self.refine_program = refine_program
        self.refine_type = refine_type
        self.refine_cycles = refine_cycles
        self.sol_cont = None
        self.tmp_dir = tmp_dir
        self.timeout = timeout

    def __call__(self, result):
        return self.generate_script(result)

    @property
    def mtz(self):
        """The input MTZ file"""
        return self._mtz

    @mtz.setter
    def mtz(self, mtz):
        """Define the input MTZ file"""
        self._mtz = os.path.abspath(mtz)
        self.get_mtz_info(mtz)

    @property
    def mtz_labels(self):
        """Column labels from input mtz"""
        return self._mtz_labels

    @property
    def cell_parameters(self):
        """The cell parameters of the input MTZ file"""
        return self._cell_parameters

    @property
    def resolution(self):
        """The resolution of the input MTZ file"""
        return self._resolution

    @property
    def search_results(self):
        """The results from the amore rotation search"""
        return sorted(self._search_results, key=lambda x: float(x.final_r_free), reverse=False)

    @property
    def sgalternative(self):
        """Whether to check for alternative space groups"""
        return self._sgalternative

    @sgalternative.setter
    def sgalternative(self, sgalternative):
        """Define whether to check for alternative space groups"""
        if sgalternative:
            self._sgalternative = sgalternative.lower()
        else:
            self._sgalternative = sgalternative

    @property
    def space_group(self):
        """The space group of the input MTZ file"""
        return self._space_group

    @property
    def mr_python_module(self):
        """The MR python module"""
        return MrPrograms[self.mr_program].value

    @property
    def mr_program(self):
        """The molecular replacement program to use"""
        return self._mr_program

    @mr_program.setter
    def mr_program(self, mr_program):
        """Define the molecular replacement program to use"""
        if mr_program.lower() in MrPrograms.__members__:
            self._mr_program = mr_program.lower()
        else:
            msg = "Unknown MR program!"
            raise RuntimeError(msg)

    @property
    def refine_python_module(self):
        """The Refinement python module"""
        return RefPrograms[self.refine_program].value

    @property
    def refine_program(self):
        """The refinement program to use"""
        return self._refine_program

    @refine_program.setter
    def refine_program(self, refine_program):
        """Define the refinement program to use"""
        if refine_program.lower() in RefPrograms.__members__:
            self._refine_program = refine_program
        else:
            msg = "Unknown Refinement program!"
            raise RuntimeError(msg)

    @property
    def refine_type(self):
        """The refinement type to use"""
        return self._refine_type

    @refine_type.setter
    def refine_type(self, refine_type):
        """Define the refinement type to use"""
        self._refine_type = refine_type

    @property
    def refine_cycles(self):
        """The number of refinement cycles to use"""
        return self._refine_cycles

    @refine_cycles.setter
    def refine_cycles(self, refine_cycles):
        """Define the number of refinement cycles to use"""
        self._refine_cycles = refine_cycles

    @property
    def output_dir(self):
        """The path to the output directory"""
        return self._output_dir

    @output_dir.setter
    def output_dir(self, output_dir):
        """Define the output directory"""
        self._output_dir = output_dir

    @property
    def timeout(self):
        """The time in minutes before phaser is killed"""
        return self._timeout

    @timeout.setter
    def timeout(self, timeout):
        """Define the time in minutes before phaser should be killed"""
        self._timeout = timeout

    def get_mtz_info(self, mtz):
        """Get various information from the input MTZ

        Parameters
        ----------
        mtz : str
            Path to the input MTZ

        Returns
        -------
        self._cell_parameters : list
            The parameters that descibe the unit cell
        self._resolution : float
            The resolution of the data
        self._space_group : str
            The space group of the data
        self._mtz_labels : obj
            :obj: containing the column labels for the mtz
        """
        # Extract crystal data from input mtz
        self._space_group, _, cell_parameters = mtz_util.crystal_data(mtz)
        self._cell_parameters = " ".join(map(str, cell_parameters))

        # Extract column labels from input mtz
        self._mtz_labels = mtz_util.GetLabels(mtz)

    def submit_jobs(
        self,
        results,
        nproc=1,
        process_all=False,
        submit_nproc=None,
        submit_qtype=None,
        submit_queue=False,
        monitor=None,
    ):
        """Submit jobs to run in serial or on a cluster

        Parameters
        ----------
        results : class
            Results from :obj: '_LatticeParameterScore' or :obj: '_AmoreRotationScore'
        nproc : int, optional
            Number of processors to use [default: 1]
        process_all : bool, optional
            Terminate MR after a success [default: True]
        submit_nproc : int
            The number of processors to use on the head node when creating submission scripts on a cluster [default: 1]
        submit_qtype : str
            The cluster submission queue type
        submit_queue : str
            The queue to submit to on the cluster
        monitor : str

        Returns
        -------
        file
            Output pdb from mr
        file
            Output hkl from mr - if using phaser
        file
            Output log file from mr program
        file
            Output pdb from refinement
        file
            Output hkl from refinement
        file
            Output log file from refinement program

        """
        if not os.path.isdir(self.output_dir):
            os.mkdir(self.output_dir)

        if self.existing_solution(results):
            return

        self.sol_cont = SolventContent(self.cell_parameters, self.space_group)
        self.mat_prob = MatthewsProbability(self.cell_parameters, self.space_group)

        run_files = []
        collector = ScriptCollector(None)

        processes = nproc if submit_qtype == "local" else submit_nproc

        with pool.Pool(processes=processes) as p:
            [(collector.add(i[0]), run_files.append(i[1])) for i in p.map(self, results) if i is not None]

        if not self.mute:
            logger.info("Running %s Molecular Replacement", self.mr_program)

        input_arguments = [collector, self.output_dir, nproc, "simbad_mr", submit_qtype, submit_queue, True, monitor]

        if process_all:
            input_arguments.append(None)
        else:
            input_arguments.append(mr_succeeded_log)

        submit_chunk(*input_arguments)

        mr_results = []
        mr_pdbouts, mr_logfiles, ref_logfiles = zip(*run_files)
        for result, mr_logfile, mr_pdbout, ref_logfile in zip(results, mr_logfiles, mr_pdbouts, ref_logfiles):
            if not os.path.isfile(mr_logfile):
                logger.debug("Cannot find %s MR log file: %s", self.mr_program, mr_logfile)
                continue
            elif not os.path.isfile(ref_logfile):
                logger.debug("Cannot find %s refine log file: %s", self.mr_program, ref_logfile)
                continue
            elif not os.path.isfile(mr_pdbout):
                logger.debug("Cannot find %s output file: %s", self.mr_program, mr_pdbout)
                continue

            score = MrScore(pdb_code=result.pdb_code)

            if self.mr_program == "molrep":
                mp = molrep_parser.MolrepParser(mr_logfile)
                score.molrep_score = mp.score
                score.molrep_tfscore = mp.tfscore
            elif self.mr_program == "phaser":
                pp = phaser_parser.PhaserParser(mr_logfile)
                score.phaser_tfz = pp.tfz
                score.phaser_llg = pp.llg
                score.phaser_rfz = pp.rfz

            if self.anomalous_data_present():
                try:
                    work_dir = os.path.join(self.output_dir, result.pdb_code, "anomalous")
                    anode = anomalous_util.AnodeSearch(self.mtz, work_dir)
                    input_model = os.path.join(
                        self.output_dir,
                        result.pdb_code,
                        "mr",
                        self.mr_program,
                        "{0}_mr_output.pdb".format(result.pdb_code),
                    )
                    anode.run(input_model)
                    a = anode.search_results()
                    score.dano_peak_height = a.dano_peak_height
                    score.nearest_atom = a.nearest_atom
                    self.dano_columns = ["dano_peak_height", "nearest_atom"]
                except RuntimeError:
                    logger.debug("RuntimeError: Unable to create DANO map for: %s", result.pdb_code)
                except PyJobExecutionError:
                    logger.debug("PyJobExecutionError: Unable to run exectute anode for: %s", result.pdb_code)

            if os.path.isfile(ref_logfile):
                rp = refmac_parser.RefmacParser(ref_logfile)
                score.final_r_free = rp.final_r_free
                score.final_r_fact = rp.final_r_fact
            else:
                logger.debug("Cannot find %s log file: %s", self.refine_program, ref_logfile)
            mr_results += [score]

        self._search_results = mr_results

    def generate_script(self, result):
        mr_workdir = os.path.join(self.output_dir, result.pdb_code, "mr", self.mr_program)
        mr_logfile = os.path.join(mr_workdir, "{0}_mr.log".format(result.pdb_code))
        mr_pdbout = os.path.join(mr_workdir, "{0}_mr_output.pdb".format(result.pdb_code))
        mr_hklout = os.path.join(mr_workdir, "{0}_mr_output.mtz".format(result.pdb_code))

        ref_workdir = os.path.join(mr_workdir, "refine")
        ref_hklout = os.path.join(ref_workdir, "{0}_refinement_output.mtz".format(result.pdb_code))
        ref_logfile = os.path.join(ref_workdir, "{0}_ref.log".format(result.pdb_code))
        ref_pdbout = os.path.join(ref_workdir, "{0}_refinement_output.pdb".format(result.pdb_code))

        diff_mapout1 = os.path.join(ref_workdir, "{0}_refmac_2fofcwt.map".format(result.pdb_code))
        diff_mapout2 = os.path.join(ref_workdir, "{0}_refmac_fofcwt.map".format(result.pdb_code))

        if isinstance(result, (AmoreRotationScore, PhaserRotationScore)):
            pdb_struct = PdbStructure.from_file(result.dat_path)
            mr_pdbin = os.path.join(self.output_dir, result.pdb_code + ".pdb")
        elif isinstance(result, LatticeSearchResult):
            pdb_struct = PdbStructure.from_file(result.pdb_path)
            mr_pdbin = result.pdb_path
        else:
            raise ValueError("Do not recognize result container")

        solvent_content = self.sol_cont.calculate_from_struct(pdb_struct)
        if solvent_content > 30:
            solvent_content, n_copies = self.mat_prob.calculate_content_ncopies_from_struct(pdb_struct)
            pdb_struct.save(mr_pdbin)
        else:
            pdb_struct.keep_first_chain_only()
            pdb_struct.save(mr_pdbin)
            solvent_content, n_copies = self.mat_prob.calculate_content_ncopies_from_struct(pdb_struct)
            msg = (
                "%s is predicted to be too large to fit in the unit "
                + "cell with a solvent content of at least 30 percent, "
                + "therefore MR will use only the first chain"
            )
            logger.debug(msg, result.pdb_code)

        mr_cmd = [
            CMD_PREFIX,
            "ccp4-python",
            "-m",
            self.mr_python_module,
            "-hklin",
            self.mtz,
            "-hklout",
            mr_hklout,
            "-pdbin",
            mr_pdbin,
            "-pdbout",
            mr_pdbout,
            "-logfile",
            mr_logfile,
            "-work_dir",
            mr_workdir,
            "-nmol",
            n_copies,
            "-sgalternative",
            self.sgalternative,
        ]

        if self.mr_program == "molrep":
            mr_cmd += ["-space_group", self.space_group]

        elif self.mr_program == "phaser":
            mr_cmd += [
                "-i",
                self.mtz_labels.i,
                "-sigi",
                self.mtz_labels.sigi,
                "-f",
                self.mtz_labels.f,
                "-sigf",
                self.mtz_labels.sigf,
                "-solvent",
                solvent_content,
                "-timeout",
                self.timeout,
            ]

            if isinstance(result, LatticeSearchResult):
                mr_cmd += ["-autohigh", 4.0, "-hires", 5.0]

        ref_cmd = [
            CMD_PREFIX,
            "ccp4-python",
            "-m",
            self.refine_python_module,
            "-pdbin",
            mr_pdbout,
            "-pdbout",
            ref_pdbout,
            "-hklin",
            mr_hklout,
            "-hklout",
            ref_hklout,
            "-logfile",
            ref_logfile,
            "-work_dir",
            ref_workdir,
            "-ncyc",
            self.refine_cycles,
        ]

        if self.refine_program == "refmac5":
            ref_cmd += ["-refinement_type", self.refine_type]
        # ====
        # Create a run script - prefix __needs__ to contain mr_program so we can find log
        # Leave order of this as SGE does not like scripts with numbers as first char
        # ====
        prefix, stem = self.mr_program + "_", result.pdb_code

        fft_cmd1, fft_stdin1 = self.fft(ref_hklout, diff_mapout1, "2mfo-dfc")
        run_stdin_1 = tmp_file(directory=self.output_dir, prefix=prefix, stem=stem, suffix="_1.stdin")
        with open(run_stdin_1, "w") as f_out:
            f_out.write(fft_stdin1)

        fft_cmd2, fft_stdin2 = self.fft(ref_hklout, diff_mapout2, "mfo-dfc")
        run_stdin_2 = tmp_file(directory=self.output_dir, prefix=prefix, stem=stem, suffix="_2.stdin")
        with open(run_stdin_2, "w") as f_out:
            f_out.write(fft_stdin2)

        ccp4_scr = os.environ["CCP4_SCR"]
        if self.tmp_dir:
            tmp_dir = os.path.join(self.tmp_dir)
        else:
            tmp_dir = os.path.join(self.output_dir)

        source = source_ccp4()

        cmd = [
            [source],
            [EXPORT, "CCP4_SCR=" + tmp_dir],
            mr_cmd + [os.linesep],
            ref_cmd + [os.linesep],
            fft_cmd1 + ["<", run_stdin_1, os.linesep],
            fft_cmd2 + ["<", run_stdin_2, os.linesep],
            [EXPORT, "CCP4_SCR=" + ccp4_scr],
        ]
        run_script = Script(directory=self.output_dir, prefix=prefix, stem=stem)
        for c in cmd:
            run_script.append(" ".join(map(str, c)))

        run_files = (mr_pdbout, mr_logfile, ref_logfile)
        return run_script, run_files

    def existing_solution(self, results):
        """Function to check if a solution is has already been found

        Parameters
        ----------
        results : class
            Results from :obj: '_LatticeParameterScore' or :obj: '_AmoreRotationScore'

        Returns
        -------
        bool
            True/False depending on whether a solution is found amongst results
        """

        for result in results:
            mr_workdir = os.path.join(self.output_dir, result.pdb_code, "mr", self.mr_program)
            mr_logfile = os.path.join(mr_workdir, "{0}_mr.log".format(result.pdb_code))
            ref_workdir = os.path.join(mr_workdir, "refine")
            ref_logfile = os.path.join(ref_workdir, "{0}_ref.log".format(result.pdb_code))
            if os.path.isfile(ref_logfile):
                rp = refmac_parser.RefmacParser(ref_logfile)
                if _mr_job_succeeded(rp.final_r_fact, rp.final_r_free):
                    score = MrScore(pdb_code=result.pdb_code)

                    if self.mr_program == "molrep":
                        mp = molrep_parser.MolrepParser(mr_logfile)
                        score.molrep_score = mp.score
                        score.molrep_tfscore = mp.tfscore
                    elif self.mr_program == "phaser":
                        pp = phaser_parser.PhaserParser(mr_logfile)
                        score.phaser_tfz = pp.tfz
                        score.phaser_llg = pp.llg
                        score.phaser_rfz = pp.rfz

                    rp = refmac_parser.RefmacParser(ref_logfile)
                    score.final_r_free = rp.final_r_free
                    score.final_r_fact = rp.final_r_fact
                    self._search_results = [score]
                    return True
        return False

    def anomalous_data_present(self):
        """Function to check if there is anomalous data present in the input MTZ

        Returns
        -------
        bool
            True/False depending on whether anomalous data is present
        """
        if self.mtz_labels.dano:
            return True
        elif self.mtz_labels.iplus:
            return True
        elif self.mtz_labels.fplus:
            return True
        else:
            return False

    @staticmethod
    def fft(hklin, mapout, map_type):
        """Function to run fft to generate difference maps for uglymol

        Parameters
        ----------
        hklin : str
           Path to input HKL file
        mapout : str
           Path to output MAP file
        map_type : str
           Define type of run, either mfo-dfc or 2mfo-dfc

        Returns
        -------
        list
           cmd
        str
           stdin

        Raises
        ------
        ValueError
           Unknown map type

        """

        cmd = [CMD_PREFIX, "fft", "hklin", hklin, "mapout", mapout]
        if map_type == "2mfo-dfc":
            stdin = (
                "title Sigmaa style 2mfo-dfc map calculated with refmac coefficients"
                + os.linesep
                + "labi F1=FWT PHI=PHWT"
                + os.linesep
                + "end"
                + os.linesep
            )
        elif map_type == "mfo-dfc":
            stdin = (
                "title Sigmaa style mfo-dfc map calculated with refmac coefficients"
                + os.linesep
                + "labi F1=DELFWT PHI=PHDELWT"
                + os.linesep
                + "end"
                + os.linesep
            )
        else:
            msg = "Unknown map type!"
            raise ValueError(msg)
        return cmd, stdin

    def summarize(self, csv_file):
        """Summarize the search results

        Parameters
        ----------
        csv_file : str
           The path for a backup CSV file

        Raises
        ------
            No results found
        """
        from simbad.util import summarize_result

        columns = []
        if self.mr_program == "molrep":
            columns += ["molrep_score", "molrep_tfscore"]

        elif self.mr_program == "phaser":
            columns += ["phaser_tfz", "phaser_llg", "phaser_rfz"]

        columns += ["final_r_fact", "final_r_free"]

        if self.anomalous_data_present():
            columns += self.dano_columns

        summarize_result(self.search_results, csv_file=csv_file, columns=columns)


def _mr_job_succeeded(r_fact, r_free):
    """Check values for job success"""
    return r_fact < 0.45 and r_free < 0.45


def _refinement_succeeded(r_fact, r_free):
    """Check values for job success"""
    return r_fact < 0.45 and r_free < 0.45


def _phaser_succeeded(llg, tfz):
    """Check values for job success"""
    return llg > 120 and tfz > 8


def mr_succeeded_log(log):
    """Check a Molecular Replacement job for it's success

    Parameters
    ----------
    log : str
       The path to a log file

    Returns
    -------
    bool
       Success status of the MR run

    """
    mr_prog, pdb = os.path.basename(log).replace(".log", "").split("_", 1)
    refmac_log = os.path.join(os.path.dirname(log), pdb, "mr", mr_prog, "refine", pdb + "_ref.log")
    if os.path.isfile(refmac_log):
        rp = refmac_parser.RefmacParser(refmac_log)
        return _mr_job_succeeded(rp.final_r_fact, rp.final_r_free)
    return False


def mr_succeeded_csvfile(f):
    """Check a Molecular Replacement job for it's success

    Parameters
    ----------
    f : str
        The path to f

    Returns
    -------
    bool
       Success status of the MR run

    """
    import pandas as pd

    df = pd.read_csv(f)
    try:
        data = zip(df.final_r_fact.tolist(), df.final_r_free.tolist(), df.phaser_llg.tolist(), df.phaser_tfz.tolist())
        return any(
            _refinement_succeeded(rfact, rfree) or _phaser_succeeded(llg, tfz) for rfact, rfree, llg, tfz in data
        )
    except AttributeError:
        data = zip(df.final_r_fact.tolist(), df.final_r_free.tolist())
        return any(_refinement_succeeded(rfact, rfree) for rfact, rfree in data)
