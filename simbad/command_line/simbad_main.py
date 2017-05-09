#!/usr/bin/env python

from __future__ import print_function

__author__ = "Adam Simpkin, and Felix Simkovic"
__contributing_authors__ = "Jens Thomas, and Ronan Keegan"
__credits__ = "Daniel Rigden, William Shepard, Charles Ballard, Villi Uski, and Andrey Lebedev"
__date__ = "05 May 2017"
__email__ = "hlasimpk@liv.ac.uk"
__version__ = "0.1"

import argparse
import os
import sys
import time

import simbad.command_line
import simbad.util.exit_util

logger = None


def simbad_argparse():
    """Create the argparse options"""
    p = argparse.ArgumentParser(
        description="SIMBAD: Sequence Independent Molecular replacement Based on Available Database",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    simbad.command_line._argparse_core_options(p)
    simbad.command_line._argparse_job_submission_options(p)
    simbad.command_line._argparse_contaminant_options(p)
    simbad.command_line._argparse_lattice_options(p)
    simbad.command_line._argparse_mr_options(p)
    simbad.command_line._argparse_mtz_options(p)
    p.add_argument('mtz', help="The path to the input mtz file")
    return p.parse_args()


def main():
    """Main SIMBAD routine"""
    args = simbad_argparse()

    if args.work_dir and os.path.isdir(args.work_dir):
        raise ValueError("Named working directory exists, please rename or remove")
    elif args.work_dir:
        os.mkdir(args.work_dir)
        args.work_dir = args.work_dir
    elif args.run_dir and os.path.isdir(args.run_dir):
        args.work_dir = simbad.command_line.make_workdir(args.run_dir, ccp4_jobid=args.ccp4_jobid)
    elif args.run_dir:
        os.mkdir(args.run_dir)
        args.work_dir = simbad.command_line.make_workdir(args.run_dir, ccp4_jobid=args.ccp4_jobid)
    else:
        raise RuntimeError("Not entirely sure what has happened here but I should never get to here")
    
    # Logger setup
    global logger
    debug_log = os.path.join(args.work_dir, 'debug.log')
    logger = simbad.command_line.setup_logging(level=args.debug_lvl, logfile=debug_log)

    # Print some nice information
    simbad.command_line.print_header()
    logger.info("Running in directory: %s\n", args.work_dir)
    
    # Take the start time
    time_start = time.time()

    # Let's start searching old boyo
    end_of_cycle, solution_found = False, False
    while not (solution_found or end_of_cycle):
        # =====================================================================================
        # Perform the lattice search
        solution_found = simbad.command_line._simbad_lattice_search(args)
        if solution_found:
            logger.info("Lucky you! SIMBAD worked its charm and found a lattice match for you.")
            continue
        else:
            logger.info("No results found - lattice search was unsuccessful")
        
        # =====================================================================================
        # Perform the contaminante search
        solution_found = simbad.command_line._simbad_contaminant_search(args)   
        if solution_found:
            logger.info("Check you out, crystallizing contaminants! But don't worry, SIMBAD figured it out and found a solution.")
            continue
        else:
            logger.info("No results found - contaminant search was unsuccessful")

        # =====================================================================================
        # Perform the contaminante search
        solution_found = simbad.command_line._simbad_full_search(args)   
        if solution_found:
            logger.info("... and SIMBAD worked once again. Get in!")
            continue
        else:
            logger.info("No results found - full search was unsuccessful")
        
        # =====================================================================================
        # Make sure we only run the loop once for now
        end_of_cycle = True

    # Calculate and display the runtime in hours
    days, hours, mins, secs = simbad.command_line.calculate_runtime(time_start, time.time())
    logger.info("All processing completed in %d days, %d hours, %d minutes, and %d seconds", days, hours, mins, secs)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        msg = "Error running main SIMBAD program: {0}".format(e.message)
        simbad.util.exit_util.exit_error(*sys.exc_info())
