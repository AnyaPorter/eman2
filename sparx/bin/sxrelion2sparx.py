#!/usr/bin/env python
# 
#
# Author: Toshio Moriya 03/12/2015 (toshio.moriya@mpi-dortmund.mpg.de)
#
# This software is issued under a joint BSD/GNU license. You may use the
# source code in this file under either license. However, note that the
# complete EMAN2 and SPARX software packages have some GPL dependencies,
# so you are responsible for compliance with the licenses of these packages
# if you opt to use BSD licensing. The warranty disclaimer below holds
# in either instance.
#
# This complete copyright notice must be included in any revised version of the
# source code. Additional authorship citations may be added, but existing
# author citations must be preserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307 USA
# 
# ========================================================================================
# NOTE: 2015/10/19 Toshio Moriya
# Now the script also stores the extract information in the stack header
# 
# NOTE: 2015/10/19 Toshio Moriya
# The script stores the relion's particle ID in the ptcl_source_coord_id header entry.
# This ID is generated by RELION when it extract particles using the original box file (before particle screening)
# If you run sxwindow.py using the box files generated by this script, ptcl_source_coord_id will be reassigned,
# which is different from relion's particle ID because it is after particle screening
# 
# ========================================================================================

from EMAN2 import *
from sparx import *
from sys import  *
import os
import sys

from optparse import OptionParser
import global_def
from global_def import  *

def main():
	# Parse command argument
	arglist = []
	for arg in sys.argv:
		arglist.append( arg )

	progname = os.path.basename( arglist[0] )
	usage = progname + ' input_star_file --output_dir=output_dir --star_section=star_section --box_size=box_size --create_stack'
	parser = OptionParser(usage, version=SPARXVERSION)

	parser.add_option('--output_dir',    type='string',        default='work',   help='output directory path.')
	parser.add_option('--star_section',  type='string',        default='data_',  help='section title in the star file where data should be extracted. (default: "data_"')
	parser.add_option('--box_size',      type=int,             default=0,        help='box size for particle extraction. It also controls the saved coordinates file format. If the given value is > 0, store the eman1 format coordinate file. The coordinates of eman1 format is particle box corner associated with this box size. The coordinates of sparx format is particle center. (Default 0: use sparx format)')
	parser.add_option('--create_stack',  action='store_true',  default=False,    help='create particle stack. (default: False)')
	
	(options,args) = parser.parse_args( arglist[1:] )

	# ------------------------------------------------------------------------------------
	# Check validity of input arguments and options
	# ------------------------------------------------------------------------------------
	if len(args) != 1:
		print( 'ERROR!!! Please provide path of input star file!' )
		print(( 'usage: ' + usage))
		print(( 'Please run "' + progname + ' -h" for detailed options'))
		return 1

	# Rename arguments and options for readability
	file_path_relion_star    = args[0]
	dir_path_work            = options.output_dir
	str_relion_start_section = options.star_section
	box_size                 = options.box_size
	is_enable_create_stack   = options.create_stack

	if (os.path.exists(file_path_relion_star) != True):
		print(( 'ERROR!!! Input star file (%s) is not found.' % file_path_relion_star))
		sys.exit(-1)

	if (os.path.exists(dir_path_work) == True):
		print(( 'ERROR!!! Output directory (%s) already exists. Please delete it or use a different output directory' % dir_path_work))
		sys.exit(-1)
	
	# ------------------------------------------------------------------------------------
	# Constants
	# ------------------------------------------------------------------------------------
	# Initialise dictionary for RELION params file related items
	idx_col = 0
	idx_title = 1
	
	relion_dict = {}
	relion_dict['_rlnVoltage']              = [-1, '#     Acc. Vol.       := %2d (%s)']
	relion_dict['_rlnDefocusU']             = [-1, '#     Defocus U       := %2d (%s)']
	relion_dict['_rlnDefocusV']             = [-1, '#     Defocus V       := %2d (%s)']
	relion_dict['_rlnDefocusAngle']         = [-1, '#     Defocus Angle   := %2d (%s)']
	relion_dict['_rlnSphericalAberration']  = [-1, '#     Cs              := %2d (%s)']
	relion_dict['_rlnDetectorPixelSize']    = [-1, '#     Det. Pix. Size  := %2d (%s)']
	relion_dict['_rlnMagnification']        = [-1, '#     Mag.            := %2d (%s)']
	relion_dict['_rlnAmplitudeContrast']    = [-1, '#     Amp. Contrast   := %2d (%s)']
	relion_dict['_rlnImageName']            = [-1, '#     Particle Source := %2d (%s)']
	relion_dict['_rlnCoordinateX']          = [-1, '#     X Coordinate    := %2d (%s)']
	relion_dict['_rlnCoordinateY']          = [-1, '#     Y Coordinate    := %2d (%s)']
	relion_dict['_rlnMicrographName']       = [-1, '#     Micrograph Name := %2d (%s)']
	relion_dict['_rlnNormCorrection']       = [-1, '#     Norm Correction   := %2d (%s)']
	relion_dict['_rlnOriginX']              = [-1, '#     X Translation   := %2d (%s)']
	relion_dict['_rlnOriginY']              = [-1, '#     Y Translation   := %2d (%s)']
	relion_dict['_rlnAngleRot']             = [-1, '#     Rotation        := %2d (%s)']
	relion_dict['_rlnAngleTilt']            = [-1, '#     Tilt            := %2d (%s)']
	relion_dict['_rlnAnglePsi']             = [-1, '#     Psi             := %2d (%s)']
	relion_dict['_rlnRandomSubset']         = [-1, '#     Random Subset   := %2d (%s)']
	relion_dict['_rlnMaxValueProbDistribution'] = [-1, '#     Max Probability   := %2d (%s)']
	
	idx_relion_process = 0
	idx_is_category_found = 1
	idx_key_list = 2

	relion_category_dict = {}
	relion_category_dict['window']  = ['Particle Extraction',  True, ['_rlnMicrographName','_rlnCoordinateX', '_rlnCoordinateY', '_rlnImageName']]
	relion_category_dict['ctf']     = ['CTF Estimation',       True, ['_rlnVoltage', '_rlnDefocusU', '_rlnDefocusV', '_rlnDefocusAngle', '_rlnSphericalAberration', '_rlnDetectorPixelSize', '_rlnMagnification', '_rlnAmplitudeContrast']]
	relion_category_dict['proj3d']  = ['Alignment Parameters', True, ['_rlnOriginX', '_rlnOriginY', '_rlnAngleRot', '_rlnAngleTilt', '_rlnAnglePsi', '_rlnMaxValueProbDistribution', '_rlnNormCorrection']]
	relion_category_dict['chunk']   = ['Random Subset',        True, ['_rlnRandomSubset']]
	
	# SPARX params file related
	if is_enable_create_stack: 
		file_name_sparx_stack      = 'sparx_stack.hdf'
	file_name_sparx_stack_ctf      = 'sparx_stack_ctf.txt'
	file_name_sparx_cter           = 'sparx_cter.txt'
	file_name_sparx_stack_proj3d   = 'sparx_stack_proj3d.txt'
	name_pattern_sparx_stack_chunk = 'sparx_stack_chunk*.txt'
	
	dir_name_coordinates           = 'Coordinates'
	
	i_enum = -1
	i_enum += 1; idx_cter_def          = i_enum # defocus [um]; index must be same as ctf object format
	i_enum += 1; idx_cter_cs           = i_enum # Cs [mm]; index must be same as ctf object format
	i_enum += 1; idx_cter_vol          = i_enum # voltage[kV]; index must be same as ctf object format
	i_enum += 1; idx_cter_apix         = i_enum # pixel size [A]; index must be same as ctf object format
	i_enum += 1; idx_cter_bfactor      = i_enum # B-factor [A^2]; index must be same as ctf object format
	i_enum += 1; idx_cter_ac           = i_enum # amplitude contrast [%]; index must be same as ctf object format
	i_enum += 1; idx_cter_astig_amp    = i_enum # astigmatism amplitude [um]; index must be same as ctf object format
	i_enum += 1; idx_cter_astig_ang    = i_enum # astigmatism angle [degree]; index must be same as ctf object format
	i_enum += 1; idx_cter_sd_def       = i_enum # std dev of defocus [um]
	i_enum += 1; idx_cter_sd_astig_amp = i_enum # std dev of ast amp [A]
	i_enum += 1; idx_cter_sd_astig_ang = i_enum # std dev of ast angle [degree]
	i_enum += 1; idx_cter_cv_def       = i_enum # coefficient of variation of defocus [%]
	i_enum += 1; idx_cter_cv_astig_amp = i_enum # coefficient of variation of ast amp [%]
	i_enum += 1; idx_cter_spectra_diff = i_enum # average of differences between with- and without-astig. experimental 1D spectra at extrema
	i_enum += 1; idx_cter_error_def    = i_enum # frequency at which signal drops by 50% due to estimated error of defocus alone [1/A]
	i_enum += 1; idx_cter_error_astig  = i_enum # frequency at which signal drops by 50% due to estimated error of defocus and astigmatism [1/A]
	i_enum += 1; idx_cter_error_ctf    = i_enum # limit frequency by CTF error [1/A]
	i_enum += 1; idx_cter_mic_name     = i_enum # micrograph name
	i_enum += 1; n_idx_cter            = i_enum
	
	# ------------------------------------------------------------------------------------
	# STEP 1: Prepare input/output file paths
	# ------------------------------------------------------------------------------------
	# Get the original current path
	dir_origin = os.getcwd() # print dir_path_origin
	
	# Create work directories
	assert(os.path.exists(dir_path_work) == False)
	print('# Creating work dir...')
	os.mkdir(dir_path_work)

	assert(os.path.exists(dir_path_work + '/' + dir_name_coordinates) == False)
	os.mkdir(dir_path_work + '/' + dir_name_coordinates)
	
	# Create input and output file paths
	if is_enable_create_stack: 
		file_path_sparx_stack = dir_path_work + '/' + file_name_sparx_stack
		assert(os.path.exists(file_path_sparx_stack) == False)

	file_path_sparx_stack_ctf = dir_path_work + '/' + file_name_sparx_stack_ctf
	assert(os.path.exists(file_path_sparx_stack_ctf) == False)

	file_path_sparx_cter = dir_path_work + '/' + file_name_sparx_cter
	assert(os.path.exists(file_path_sparx_cter) == False)

	file_path_sparx_stack_proj3d = dir_path_work + '/' + file_name_sparx_stack_proj3d
	assert(os.path.exists(file_path_sparx_stack_proj3d) == False)	

	# ------------------------------------------------------------------------------------
	# STEP 2: Convert RELION parameters to SPARX format
	# ------------------------------------------------------------------------------------	
	
	# Initialise loop variables 
	is_found_section = False
	is_found_loop = False
	is_success = True
	i_relion_item_col = 0   # Counter for number of relion items/columns
	i_relion_particle = 0   # Counter for number of relion particles/entries, starting from 0
	i_sprax_particle = 0    # Counter for number of sparx particles/entries, starting from 0


	sparx_cter_dict={}           # For CTF parameters in cter format (one entry for each micrograph)
	sparx_coordinates_dict = {}  # For Coordinate parameters
	sparx_chunk_dict = {}
	sparx_chunk_id_max = 0
	
	# Open input/output files
	#assert(os.path.exists(file_path_relion_star) == True)
	if not os.path.exists(file_path_relion_star):
		ERROR("relion input file does not exists","sxrelion2sparx.py", 1)
	file_relion_star = open(file_path_relion_star,'r')
	file_sparx_stack_ctf = open(file_path_sparx_stack_ctf,'w+')
	file_sparx_cter = open(file_path_sparx_cter,'w+')
	file_sparx_stack_proj3d = open(file_path_sparx_stack_proj3d,'w+')

	# Loop through all lines in input relion star file
	for i_line, str_line in enumerate(file_relion_star):
	
		# First, find data section in star file 
		if is_found_section == False:
			if str_line.find(str_relion_start_section) != -1:
				print('# Title: %s' % (str_line.rstrip('\n')))
				is_found_section = True
		# Then, ignore loop_ in star file 
		elif is_found_loop == False:
			assert(is_found_section == True)
			if str_line.find('loop_') != -1:
				is_found_loop = True
				print('# Extracted Column IDs:')
		# Process item list and data entries 
		else:
			#assert((is_found_section == True) & (is_found_loop == True))
			if (is_found_section is False) or (is_found_loop is False):
				ERROR("relion relion section and loop not found","sxrelion2sparx.py", 1)
			tokens_line = str_line.split() # print tokens_line
			n_tokens_line = len(tokens_line)

			# First, check item list and find the column number of each item
			if str_line.find('_rln') != -1:
				i_relion_item_col += 1
				# print '# DEBUG: updated Column Counts := %d ' % (i_relion_item_col)
				
				relion_key = str_line.split(' ')[0]
				assert(relion_key.find('_rln') != -1)
				
				if relion_key in relion_dict.keys():
					relion_dict[relion_key][idx_col] = int(i_relion_item_col)
					print(relion_dict[relion_key][idx_title] % (relion_dict[relion_key][idx_col], relion_key))
			
			# Then, read the data entries
			elif n_tokens_line == i_relion_item_col:
				# Check if all entries of each category were found in RELION star file
				# Do this only once
				if i_relion_particle == 0:
					print('# ')
					print('# Checking RELION star file contents ...')
					for category_key in relion_category_dict.keys():
						for key in relion_category_dict[category_key][idx_key_list]:
							if relion_dict[key][idx_col] < 0:
								print('#     %s entry for %s is not found' % (key, relion_category_dict[category_key][idx_relion_process]))
								relion_category_dict[category_key][idx_is_category_found] = False
					
					if relion_category_dict['window'][idx_is_category_found] == False:
						print('# ')
						print('# ERROR!!! Input star file must contain all entries for %s. Aborting execution ...' % (relion_category_dict['window'][idx_relion_process]))
						is_success = False
						break;
						
					for category_key in relion_category_dict.keys():
						if relion_category_dict[category_key][idx_is_category_found] == False:
							print('# ')
							print('# WARNING!!! %s cannot be extracted!!!' % (relion_category_dict[category_key][idx_relion_process]))
					print('# ')
				
				if i_relion_particle % 1000 == 0:
					print('# Processing RELION entries from %6d to %6d ...' % (i_relion_particle, i_relion_particle + 1000 - 1))
				
				##### Store box coordinate related parameters #####
				relion_coordinate_x = int(float(tokens_line[relion_dict['_rlnCoordinateX'][idx_col] - 1]))
				relion_coordinate_y = int(float(tokens_line[relion_dict['_rlnCoordinateY'][idx_col] - 1]))
				
				relion_micrograph_name = tokens_line[relion_dict['_rlnMicrographName'][idx_col] - 1]
				micrograph_basename = os.path.basename(relion_micrograph_name)
				
				# No conversion is necessary from relion to sparx formats
				if micrograph_basename in sparx_coordinates_dict.keys():
					sparx_coordinates_dict[micrograph_basename].append([relion_coordinate_x, relion_coordinate_y])
				else:
					sparx_coordinates_dict[micrograph_basename] = [[relion_coordinate_x, relion_coordinate_y]]

				if relion_category_dict['ctf'][idx_is_category_found]:
					##### Store CTF related parameters #####
					# Parse this entry line and covert the parameters from RELION to SPARX formats
					sparx_ctf = {}
					sparx_ctf['acc_vol'] = float(tokens_line[relion_dict['_rlnVoltage'][idx_col] - 1])
					
					relion_defocusU = float(tokens_line[relion_dict['_rlnDefocusU'][idx_col] - 1])
					relion_defocusV = float(tokens_line[relion_dict['_rlnDefocusV'][idx_col] - 1])
					relion_defocus_angle = float(tokens_line[relion_dict['_rlnDefocusAngle'][idx_col] - 1])
					
					sparx_ctf['defocus']     = (relion_defocusU + relion_defocusV) / 20000   # convert format from RELION to SPARX
					sparx_ctf['astig_amp']   = (-relion_defocusU + relion_defocusV) / 10000   # convert format from RELION to SPARX
					sparx_ctf['astig_angle'] = 45.0 - relion_defocus_angle # convert format from RELION to SPARX
					while sparx_ctf['astig_angle']  >= 180:
						sparx_ctf['astig_angle'] -= 180
					while sparx_ctf['astig_angle'] < 0:
						sparx_ctf['astig_angle'] += 180
					assert(sparx_ctf['astig_angle'] < 180 and sparx_ctf['astig_angle'] >= 0)
					
					sparx_ctf['cs'] = float(tokens_line[relion_dict['_rlnSphericalAberration'][idx_col] - 1])
					
					relion_det_pix_size = float(tokens_line[relion_dict['_rlnDetectorPixelSize'][idx_col] - 1])
					relion_mag = float(tokens_line[relion_dict['_rlnMagnification'][idx_col] - 1])
					sparx_ctf['apix'] = 10000 * relion_det_pix_size / relion_mag # convert um to A
					
					relion_amp_contrast = float(tokens_line[relion_dict['_rlnAmplitudeContrast'][idx_col] - 1])
					sparx_ctf['amp_contrast'] = 100 * relion_amp_contrast # convert to %
					
					sparx_ctf['bfactor'] = 0.0 # RELION does not use B-Factor, so set it zero always
					
					# Write to file
					# NOTE: Toshio Moriya 2016/04/26
					# Use the file output of header() in application.py
					# file_sparx_stack_ctf.write('%12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f \n' % (sparx_ctf['defocus'], sparx_ctf['cs'], sparx_ctf['acc_vol'], sparx_ctf['apix'], sparx_ctf['bfactor'], sparx_ctf['amp_contrast'], sparx_ctf['astig_amp'], sparx_ctf['astig_angle']))
					file_sparx_stack_ctf.write('%15.5f %15.5f %15.5f %15.5f %15.5f %15.5f %15.5f %15.5f' % (sparx_ctf['defocus'], sparx_ctf['cs'], sparx_ctf['acc_vol'], sparx_ctf['apix'], sparx_ctf['bfactor'], sparx_ctf['amp_contrast'], sparx_ctf['astig_amp'], sparx_ctf['astig_angle']))
					file_sparx_stack_ctf.write('\n')
					
					##### Store CTF related parameters in cter format ##### 
					cter_entry = [sparx_ctf['defocus'], sparx_ctf['cs'], sparx_ctf['acc_vol'], sparx_ctf['apix'], sparx_ctf['bfactor'], sparx_ctf['amp_contrast'], sparx_ctf['astig_amp'], sparx_ctf['astig_angle'], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.5, relion_micrograph_name]
					#assert(len(cter_entry) == n_idx_cter)
					if (len(cter_entry) != n_idx_cter):
						ERROR(" number of cter entries does not match number of index of cter", "sxrelion2sparx.py", 1)
						
					# Store one CTER entry for each micrograph
					if micrograph_basename not in sparx_cter_dict:
						sparx_cter_dict[micrograph_basename] = cter_entry
						# file_sparx_cter.write('%12.6f %12.6f %12d %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %s\n' % (cter_entry[0], cter_entry[1], cter_entry[2], cter_entry[3], cter_entry[4], cter_entry[5], cter_entry[6], cter_entry[7], cter_entry[8], cter_entry[9], cter_entry[10], cter_entry[11], cter_entry[12], cter_entry[13]))
						for idx_cter in xrange(n_idx_cter - 1):
							file_sparx_cter.write("  %12.5g" % cter_entry[idx_cter])
						file_sparx_cter.write("  %s\n" % cter_entry[-1])
					else:
						#assert(cmp(sparx_cter_dict[micrograph_basename], cter_entry) == 0)
						if cmp(sparx_cter_dict[micrograph_basename], cter_entry) != 0:
							ERROR(" number of micrograph entries does not match number of decous entries", "sxrelion2sparx.py", 1)
	
				if relion_category_dict['proj3d'][idx_is_category_found]:
					##### Store Projection related parameters #####
					relion_tx = float(tokens_line[relion_dict['_rlnOriginX'][idx_col] - 1])
					relion_ty = float(tokens_line[relion_dict['_rlnOriginY'][idx_col] - 1])
					relion_rot = float(tokens_line[relion_dict['_rlnAngleRot'][idx_col] - 1])
					relion_tilt = float(tokens_line[relion_dict['_rlnAngleTilt'][idx_col] - 1])
					relion_psi = float(tokens_line[relion_dict['_rlnAnglePsi'][idx_col] - 1])

					relion_trans3d = Transform({'phi':relion_rot, 'theta':relion_tilt, 'omega':relion_psi, 'tx':relion_tx, 'ty':relion_ty, 'type':'mrc', 'tz':0})
					sparx_proj3d = relion_trans3d.get_params('spider')
					file_sparx_stack_proj3d.write('%12.6f %12.6f %12.6f %12.6f %12.6f %12.6f %12.6f\n' % (sparx_proj3d['phi'], sparx_proj3d['theta'], sparx_proj3d['psi'], sparx_proj3d['tx'], sparx_proj3d['ty'], \
													float(tokens_line[relion_dict['_rlnMaxValueProbDistribution'][idx_col] - 1]), float(tokens_line[relion_dict['_rlnNormCorrection'][idx_col] - 1])))
				
				if relion_category_dict['chunk'][idx_is_category_found]:
					##### Store the entry id (particle id) in the corresponding subset #####
					# relion_random_subset starts from 1 in RELION
					relion_random_subset = int(tokens_line[relion_dict['_rlnRandomSubset'][idx_col] - 1])
					
					# Chunk ID starts from 0 in SPARX
					sparx_chunk_id = relion_random_subset - 1
					
					if (sparx_chunk_id_max < sparx_chunk_id):
						sparx_chunk_id_max = sparx_chunk_id
				
					sparx_chunk_key = '%1d' % sparx_chunk_id
					if sparx_chunk_dict.has_key(sparx_chunk_key) == False:
						sparx_chunk_dict[sparx_chunk_key] = []
					sparx_chunk_dict[sparx_chunk_key].append(i_relion_particle)
				
							
				##### Create stack and set the header information ##### 
				if is_enable_create_stack: 
					# Now read image
					relion_particle_source = tokens_line[relion_dict['_rlnImageName'][idx_col] - 1]
					tokens_particle_source = relion_particle_source.split('@')
					assert(len(tokens_particle_source) == 2)
				
	
					relion_local_particle_id = int(tokens_particle_source[0]) - 1 # Local Particle ID of RELION from 1 but SPARX from 0 
					relion_local_stack_path = tokens_particle_source[1]
										
					# assert(os.path.exists(relion_local_stack_path) == True)
					if(not os.path.exists(relion_local_stack_path)):
						print('# WARNING!!! Image name %s specified in star file is not found. Skipping star file entry %d!!!' % (relion_local_stack_path, i_relion_particle))
					else:
						# Copy this particle image from local stack to new global stack
						n_img_relion_local_stack = EMUtil.get_image_count(relion_local_stack_path)
						assert(relion_local_particle_id < n_img_relion_local_stack)
						img_particle = get_im(relion_local_stack_path, relion_local_particle_id)
						
						# NOTE: 2015/10/19 Toshio Moriya
						# Now storing the extract information in the header
						# set_params_proj(img_particle, [sparx_phi, sparx_theta, sparx_psi, sparx_s2x, sparx_s2y])
						img_particle.set_attr('ptcl_source_relion', relion_particle_source)
						img_particle.set_attr('ptcl_source_image', relion_micrograph_name)
						img_particle.set_attr('ptcl_source_coord_id', relion_local_particle_id)
						img_particle.set_attr('ptcl_source_coord', [relion_coordinate_x, relion_coordinate_y]) # No conversion is necessary from relion to sparx foramts
						
						if relion_category_dict['ctf'][idx_is_category_found]:
							img_particle.set_attr('ctf', generate_ctf([sparx_ctf['defocus'], sparx_ctf['cs'], sparx_ctf['acc_vol'], sparx_ctf['apix'], sparx_ctf['bfactor'], sparx_ctf['amp_contrast'], sparx_ctf['astig_amp'], sparx_ctf['astig_angle']]))
						if relion_category_dict['proj3d'][idx_is_category_found]:
							set_params_proj(img_particle, [sparx_proj3d['phi'], sparx_proj3d['theta'], sparx_proj3d['psi'], sparx_proj3d['tx'], sparx_proj3d['ty']])
						if relion_category_dict['chunk'][idx_is_category_found]:
							img_particle.set_attr('chunk_id', sparx_chunk_id)
						
						img_particle.write_image(file_path_sparx_stack, i_sprax_particle)
						i_sprax_particle += 1

				i_relion_particle += 1

			else:
				print('# An Empty Line is detected after data entries. Breaking the loop...')
				break;
	
	if is_found_section == False:
		print('# ERROR!!! Specified --star_section (%s) is not found!!!' % (str_relion_start_section))
		print('#          Please check section name in star file')
		is_success = False
	elif is_found_loop == False:
		print('# ERROR!!! loop_ line after specified --star_section (%s) is not found!!!' % (str_relion_start_section))
		print('#          Please check if star file is not corrupted')
		is_success = False
	
	if is_success:
		# Store the results of counters
		print('# ')
		print('# Detected Column Counts      := %d ' % (i_relion_item_col))
		print('# Detected Entry Counts       := %d ' % (i_relion_particle))
		print('# Image counts added to stack := %d ' % (i_sprax_particle))
			
		# Warn user if number of particles in sparx stack is different from relion star file entries
		if is_enable_create_stack :
			if i_sprax_particle < i_relion_particle:
				print('# WARNING!!! Number of particles in generated stack (%d) is different from number of entries in input RELION star file (%d)!!!' % (i_relion_particle, i_sprax_particle))
				print('#            Please check if there are all images specified by _rlnImageName in star file')
			else:
				if (i_sprax_particle != i_relion_particle):
					ERROR("number of particles does not match ","is_enable_create_stack", 1)
				if (not os.path.exists(file_path_sparx_stack)):
					ERROR("sparx stack does not exists","is_enable_create_stack", 1)
				if (i_sprax_particle != EMUtil.get_image_count(file_path_sparx_stack)):
					ERROR("numbers of particles does not match ","is_enable_create_stack", 1)
				
		# Write box coordinate to files (doing here to avoid repeating open/close files in loop)
		if box_size > 0:
			coordinates_extension = '.box'
		else:
			coordinates_extension = '.txt'
			assert(box_size <= 0)
	
		for micrograph_basename in sparx_coordinates_dict.keys():
			micrograph_extension = os.path.splitext(micrograph_basename)[1]
			file_path_coordinates = dir_path_work + '/' + dir_name_coordinates + '/' + micrograph_basename.replace(micrograph_extension, coordinates_extension)
			file_coordinates = open(file_path_coordinates,'w')
			for sparx_coordinates in sparx_coordinates_dict[micrograph_basename]:
				if box_size > 0:
					# Convert coordinate from sparx to eman1 foramts
					eman1_coordinate_x = sparx_coordinates[0] - box_size//2
					eman1_coordinate_y = sparx_coordinates[1] - box_size//2
					eman1_dummy = -1 # For 5th column of EMAN1 boxer format
					file_coordinates.write('%6d %6d %6d %6d %6d\n' % (eman1_coordinate_x, eman1_coordinate_y, box_size, box_size, eman1_dummy))
				else:
					file_coordinates.write('%6d %6d\n' % (sparx_coordinates[0], sparx_coordinates[1]))
			file_coordinates.close()
		
		# Write chunk parameter files (particle id list of each chunk/group) parameter files
		for sparx_chunk_key in sparx_chunk_dict:
			# Open the files for this chunk key
			file_name_sparx_stack_chunk = name_pattern_sparx_stack_chunk.replace('*', sparx_chunk_key)
			file_path_sparx_stack_chunk = dir_path_work + '/' + file_name_sparx_stack_chunk
			file_sparx_stack_chunk = open(file_path_sparx_stack_chunk, 'w+')
			# Write the list of particle IDs of each chunk 
			for relion_particle_id in sparx_chunk_dict[sparx_chunk_key]:
				file_sparx_stack_chunk.write('%d \n' % (relion_particle_id))
			# Close the files for this chunk key
			file_sparx_stack_chunk.close()

	# Close input/output files
	file_relion_star.close()
	file_sparx_stack_ctf.close()
	file_sparx_cter.close()
	file_sparx_stack_proj3d.close()

	# Remove unnecessarily generated files
	if relion_category_dict['ctf'][idx_is_category_found] == False:
		if os.path.exists(file_path_sparx_stack_ctf):
			os.remove(file_path_sparx_stack_ctf)
		if os.path.exists(file_path_sparx_cter):
			os.remove(file_path_sparx_cter)
	if relion_category_dict['proj3d'][idx_is_category_found] == False:
		if os.path.exists(file_path_sparx_stack_proj3d):
			os.remove(file_path_sparx_stack_proj3d)
	
	# Restore the original current dir
	os.chdir(dir_origin)

	print('# ')
	print('# DONE!')

if __name__ == '__main__':
	main()
