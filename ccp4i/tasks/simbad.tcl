#
#     Copyright (C) 1999-2004  Liz Potterton, Peter Briggs
#
#     This code is distributed under the terms and conditions of the
#     CCP4 Program Suite Licence Agreement as a CCP4 Library.
#     A copy of the CCP4 licence can be obtained by writing to the
#     CCP4 Secretary, Daresbury Laboratory, Warrington WA4 4AD, UK.
#
#CCP4i_cvs_Id $Id$
# ======================================================================
# simbad.tcl --
#
# CCP4Interface 
#
# =======================================================================

#---------------------------------------------------------------------
proc simbad_setup { typedefVar arrayname } {
#---------------------------------------------------------------------
  upvar #0  $typedefVar typedef
  upvar #0 $arrayname array

  DefineMenu _simbad_mode [ list "Lattice search" \
	          		"Contaminant search" \
	          		"MoRDa database search" ] \
	     [ list LATTICE CONTAMINANT MORDA ] 

  return 1
}

#------------------------------------------------------------------------
  proc toggle_labin {arrayname} {
#------------------------------------------------------------------------
  upvar #0 $arrayname array
  set path_mtz [GetFullFileName0 $arrayname HKLIN]
  if { [string length $path_mtz] && [file isfile $path_mtz] } {
    GetMtzColumnByType $path_mtz J colnames coltypes
    if { [llength $colnames] } {
#     SetValue $arrayname TOGGLE_LABIN 1
      set array(TOGGLE_LABIN) 1
    } else {
      GetMtzColumnByType $path_mtz F colnames coltypes
      if { [llength $colnames] } {
#       SetValue $arrayname TOGGLE_LABIN 0
        set array(TOGGLE_LABIN) 0
      }
    }
  }
}

############################################################################
proc simbadArguments { arrayname counter } {
############################################################################
  upvar #0 $arrayname array

  SetProgramHelpFile "simbad" 
  
  CreateLine line \
    help match \
    message "SIMBAD command line argument and value (e.g. -F <F col label>)" \
    label "SIMBAD command line argument and value:" \
    widget SIMBADARG  -width 50

}

# procedure to draw task window
#---------------------------------------------------------------------
proc simbad_task_window { arrayname } {
#---------------------------------------------------------------------
  upvar #0 $arrayname array

  if { [CreateTaskWindow $arrayname  \
        "Sequence Independent Molecular Replacement" "SIMBAD" \
               {} ] == 0 } return

  # Automatically determine the number of processors available
  set array(NProc) [numberOfCPUs]

  SetProgramHelpFile "simbad"

  set array(INITIALISED) 0

#=PROTOCOL==============================================================

  OpenFolder protocol 

  CreateTitleLine line TITLE

#=FILES================================================================ 

  CreateLine line \
      message "Select the mode for SIMBAD to run" \
      label "Program Mode:" \
      widget SIMBAD_MODE  

  OpenFolder file

  CreateLine line \
	  label "Run SIMBAD to check for contaminants" \
	  -italic

  # Give the number of processors to use
  CreateLine line \
	message "Number of Processors" \
        label "Number of Processors" \
	widget NProc \
	  -width 3 

  # Input MTZ file
  CreateInputFileLine line \
        "Enter name of input mtz file" \
        "MTZ in" \
        HKLIN DIR_HKLIN
#        -command "toggle_labin $arrayname" 
#
#  CreateLine line \
#      widget TOGGLE_LABIN \
#      label "Input data are merged intensities"
#
#  # MTZ labels
#  CreateLabinLine line \
#       "Select amplitude (F) and sigma (SIGF)" \
#       HKLIN "F" F {NULL} \
#       -sigma "SIGF" SIGF {NULL} \
#       -toggle_display TOGGLE_LABIN open 0
#
#  CreateLabinLine line \
#       "Select intensity (I) and sigma (SIGI)" \
#       HKLIN "I" I {NULL} \
#       -sigma "SIGI" SIGI {NULL} \
#       -toggle_display TOGGLE_LABIN open 1

#  CreateLabinLine line \
      "Assign structure factor amplitudes (FP) and sigmas (SIGFP)" \
      HKLIN "FP" FP {NULL} \
      -sigma "SIGFP" SIGFP {NULL}

  CreateLine line \
      label "Enter additional command line options for SIMBAD" -italic 
 
  CreateExtendingFrame NSIMBADARG simbadArguments \
      "Additional command line arguments" \
      "Add argument" \
      SIMBADARG   

}

#--------------------------------------------------------------
proc simbad_run { arrayname } {
#--------------------------------------------------------------
  global system
  return 1

}