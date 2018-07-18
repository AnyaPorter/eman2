#!/usr/bin/env python
from __future__ import print_function

#
# Authors: James Michael Bell & Adam Fluty 07/13/2018
# Copyright (c) 2000-2013 Baylor College of Medicine
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
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  2111-1307 USA
#

from future import standard_library
standard_library.install_aliases()
from EMAN2 import *
import sys
import os
from sys import argv
import shutil
import subprocess
import shlex

def which(program):
	# found at https://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
	def is_exe(fpath) :
		return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

	fpath, fname = os.path.split(program)
	if fpath:
		if is_exe(program): return program
	else:
		for path in os.environ["PATH"].split(os.pathsep):
			for f in os.listdir(path):
				if program in f:
					exe_file = os.path.join(path, f)
					if is_exe(exe_file): return exe_file
	return None

def main():

	progname = os.path.basename(sys.argv[0])
	usage = """prog [options] <ddd_movie_stacks>
	This program is a wrapper for various DDD alignment routines including:
		alignframes (IMOD)
		motioncor2 (UCSF)

	Note, this is a simple script that mainly uses default alignment parameters for each
	external program. It is mainly intended to make some external ddd alignment routines
	available from the EMAN2 GUI for streamlined processing. In order for this program to
	run, the alignment routine you wish to use must be installed and accessible via the PATH 
	environment variable. To customize alignment, you will need to run these programs 
	from the command line independently and import the aligned averages/tiltseries into 
	your EMAN2 project.
	"""

	parser = EMArgumentParser(usage=usage,version=EMANVERSION)

	parser.add_pos_argument(name="input",help="List the movies you intend to align. If a directory is specified, this program will attempt to process frames within the specified directory using a provided mdoc file.", default="", guitype='filebox', browser="EMMovieDataTable(withmodal=True,multiselect=True)",  row=0, col=0, rowspan=1, colspan=2, mode="tomo,spr")

	parser.add_argument("--program",  default = "imod_alignframes", choices=["imod_alignframes","ucsf_motioncor2"], type=str, help="Use this external program to align frames. Choose between imod_alignframes and ucsf_motioncor2. Note, programs must be accessible from your PATH environment variable.",guitype='combobox', choicelist='["imod_alignframes","ucsf_motioncor2"]', row=1, col=0, rowspan=1, colspan=1, mode="tomo,spr")
	parser.add_argument("--device",  default = "gpu", type=str, choices=["cpu","gpu"], help="When possible, use this device to process movie frames. Default is gpu.",guitype='combobox', choicelist='["gpu","cpu"]', row=1, col=1, rowspan=1, colspan=1, mode="tomo,spr")

	parser.add_header(name="orblock1", help='Just a visual separation', title="Options", row=2, col=0, rowspan=1, colspan=2, mode="tomo,spr")

	parser.add_argument("--mdoc", default = None, type=str, help="Use this many patches with MotionCor2. Format is 'X Y'. Default is: '1 1'",guitype='filebox', browser="EMMovieDataTable(withmodal=True,multiselect=True)",  row=3, col=0,rowspan=1, colspan=2, mode="tomo")

	parser.add_argument("--dark",  default = None, type=str, help="Use this dark reference.",guitype='filebox',  browser="EMMovieDataTable(withmodal=True,multiselect=True)",  row=4, col=0,rowspan=1, colspan=2, mode="tomo,spr")
	parser.add_argument("--gain",  default = None, type=str, help="Use this gain reference.",guitype='filebox',  browser="EMMovieDataTable(withmodal=True,multiselect=True)",  row=5, col=0,rowspan=1, colspan=2, mode="tomo,spr")

	parser.add_argument("--defect_file",  default = None, type=str, help="Specify the camera defects file.", guitype='filebox', browser="EMMovieDataTable(withmodal=True,multiselect=True)",  row=6, col=0,rowspan=1, colspan=2, mode="tomo,spr")

	parser.add_argument("--mc2_rotgain",  default = 0, type=int, choices=[0,1,2,3], help="Rotates the gain 90 degress counter clockwise X times. Rotation is applied before flipping.",guitype='combobox', choicelist='["0","1","2","3"]', row=7, col=0, rowspan=1, colspan=1, mode="tomo,spr")
	parser.add_argument("--mc2_flipgain",  default = 0, type=int, choices=[0,1,2], help="A value of 1 flips gain image vertically, 2 flips gain image horizontally. Default is 0.",guitype='combobox',  choicelist='["0","1","2"]', row=7, col=1, rowspan=1, colspan=1, mode="tomo,spr")

	parser.add_argument("--imod_rotflipgain",  default = 0, type=int, choices=[0,1,2,3,4,5,6,7], help="Rotates the gain 90 degress counter clockwise X times. If value is greater than 3, gain image is flipped about the y axis before rotation.",guitype='combobox', choicelist='["0","1","2","3","4","5","6","7"]', row=8, col=0, rowspan=1, colspan=1, mode="tomo,spr")
	parser.add_argument("--device_num",  default = "0", type=str, help="When possible, use this device to process movie frames. Default is GPU.",guitype="intbox", row=8, col=1, rowspan=1, colspan=1, mode="tomo,spr")

	parser.add_argument("--binby",  default = "", type=int, help="The degree of binning for final image. Default is 1, i.e. no binning. Note that this option takes only integer values.",guitype='intbox', row=9, col=0, rowspan=1, colspan=1, mode="tomo,spr")
	parser.add_argument("--groupby",  default = "", type=int, help="Before alignment, sum raw frames in groups of X to increase signal to noise ratio.",guitype='intbox', row=9, col=1, rowspan=1, colspan=1, mode="tomo,spr")

	parser.add_argument("--first",  default = "", type=int, help="The index of the leading frame to include in alignment.",guitype='intbox', row=10, col=0, rowspan=1, colspan=1, mode="tomo,spr")
	parser.add_argument("--last",  default = "", type=int, help="The index of the last frame to include in alignment.", guitype='intbox', row=10, col=1, rowspan=1, colspan=1, mode="tomo,spr")

	parser.add_argument("--mc2_patch",  default = "", type=str, help="Use this many patches with MotionCor2. Format is 'X Y'. Default is: '5 5'",guitype='strbox', row=11, col=0, rowspan=1, colspan=1, mode="tomo,spr")

	parser.add_argument("--tiltseries_name",  default = "", type=str, help="Specify the name of the output tiltseries. A .mrc extension will be appended to the filename provided.",guitype='strbox', row=11, col=0, rowspan=1, colspan=1, mode="tomo")

	parser.add_argument("--tomo", default=False, action="store_true", help="If checked, aligned frames will be placed in a tiltseries located in the 'tiltseries' directory. Otherwise, aligned sums will populate the 'micrographs' directory.",guitype='boolbox', row=11, col=1, rowspan=1, colspan=1, mode="tomo[True]")

	parser.add_argument("--verbose", "-v", dest="verbose", action="store", metavar="n", type=int, default=0, help="verbose level [0-9], higner number means higher level of verboseness")
	parser.add_argument("--ppid", type=int, help="Set the PID of the parent process, used for cross platform PPID",default=-1)
	
	(options, args) = parser.parse_args()

	if len(args) == 0 and options.mdoc == None:
		print("ERROR: No movies privided. When running IMOD alignframes, you must specify movie files, an MDOC file via the --mdoc option, or a directory containing DDD movies to be aligned.")
		sys.exit(1)

	if options.mdoc != None:
		mdoc_bname,mdoc_ext = os.path.basename(options.mdoc).split(".")
		if mdoc_ext not in ["mdoc", "idoc"]:
			print("ERROR: The specified mdoc file does not have a .mdoc/.idoc extension.")
			print("Please provide a valid mdoc/idoc file with the proper extension.")
			sys.exit(1)

	if len(args) == 0 and options.program == "ucsf_motioncor2":
		print("ERROR: No movies privided. When running motioncor2, you must specify movie files for alignment.")
		sys.exit(1)

	if options.device == "gpu":
		try: devices = map(int,options.device_num.split())
		except:
			print("ERROR: Cannot interpret device number. Please specify the ID of the GPU you wish to use, i.e. an integer >= 0.")
			sys.exit(1)

	if options.program == "imod_alignframes":

		if options.first == "" and options.last != "":
			print("ERROR: In order to specify the last frame, you must also specify the first frame you wish to include using the --frst option.")
			sys.exit(1)

		if options.first != "" and options.last == "":
			print("ERROR: In order to specify the first frame, you must also specify the last frame you wish to include using the --last option.")
			sys.exit(1)

		program = which("alignframes")

	if options.program == "motioncor2":

		try: patchx,patchy = map(int,options.patch.split())
		except:
			print("ERROR: Could not interpret --patch for use with MotionCor2. Please input integer values in the form: 'X,Y'")
			sys.exit(1)

		if device == "cpu":
			print("ERROR: Cannot use --device cpu with MotionCor2. This program requires >= 1 gpu.")
			sys.exit(1)

		program = which("MotionCor2")

	if program == None:
		print("Could not locate {}. Please check that the program is installed and available within your PATH environment variable.".format(options.program.replace("_"," ")))
		sys.exit(1)

	if not os.path.isdir(args[0]):
		bname,ext = os.path.basename(args[0]).split(".")
		if ext not in  ["mrc","mrcs","tif"]:
			print("{} cannot parse .{} format files. Please check that files are MRC or TIF format.".format(program,ext))
			sys.exit(1)
	else:
		ext = None
		bname = os.path.basename(args[0])

	options.tiltseries_name

	cmdopts = ""

	if options.tomo: outdir = "tiltseries"
	else: outdir = "micrographs"

	try: os.mkdir(outdir)
	except: pass

	if options.program == "imod_alignframes":

		if options.device == "gpu": cmdopts += " -gpu {} ".format(options.device_num)

		if options.dark != None: cmdopts += " -dark {} ".format(options.dark)
		if options.gain != None: cmdopts += " -gain {} ".format(options.gain)
		if options.imod_rotflipgain != 0: cmdopts += " -rotation {} ".format(options.imod_rotflipgain)
		
		if options.defect_file != None: cmdopts+=" -defect {} ".format(options.defects)
		
		if options.groupby != "": cmdopts+=" -group {} ".format(options.groupby)
		if options.binby != "": cmdopts+=" -binning {} -1 ".format(options.binby)

		if options.first != "" and options.last != "":
			cmdopts+=" -frames {} {} ".format(options.first,options.last)

		if options.mdoc != None:

			if options.tomo and options.tiltseries_name != "":
				output = "{}/{}.mrc".format(options.tiltseries_name)
			else:
				output = "{}/{}_ali.mrc".format(outdir,mdoc_basename)
			if len(args) == 0:
				cmd = "{} -mdoc {} -output {}".format(program,options.mdoc,output)
			elif len(args) == 1:
				cmd = "{} -mdoc {} -path {} -output {}".format(program,options.mdoc,args[0],output)
			else:
				inputs = " ".join(args)
				cmd = "{} -input {} -mdoc {} -output {}".format(program,inputs,options.mdoc,output)
			run(cmd,verbose=options.verbose)
		else:
			for arg in args:
				if options.tomo and options.tiltseries_name != "":
					output = "{}/{}.mrc".format(options.tiltseries_name)
				else:
					output = "{}/{}_ali.mrc".format(outdir,bname)
				cmd = "{} -input {} -output {} {}".format(program,arg,output,cmdopts)
				run(cmd,verbose=options.verbose)

	elif options.program == "ucsf_motioncor2":

		if options.dark != None: cmd += " -Dark {} ".format(options.dark)
		if options.gain != None: cmd += " -Gain {} ".format(options.gain)

		if options.mc2_flipgain != 0: cmd+=" -FlipGain {}".format(options.mc2_flipgain)
		if options.mc2_rotgain != 0: cmd+=" -RotGain {}".format(options.mc2_rotgain)

		if options.defect_file != None: cmd+=" -DefectFile {}".format(options.defects)

		if options.first != "": cmd+=" -Throw {}".format(options.first)
		if options.last != "": cmd+=" -Trunc {}".format(options.last)

		if options.group != "": cmd+=" -Group {}".format(options.group)
		if options.binby != "": cmd+=" -FtBin {}".format(options.binby)

		if options.mc2_patch != "": cmd += " -Patch {} ".format(options.mc2_patch)

		if options.mdoc != None:
			if options.tiltseries_name != "":
				tiltname = "{}/{}.mrc".format(outdir,options.tiltseries_name)
			else: tiltname="{}/{}_ali.mrc".format(outdir,mdoc_basename)

			info=[]
			zval=-1
			print("DOC: {}".format(options.mdoc))
			with open(options.mdoc) as docf:
				for l in docf.readlines():
					p = l.strip()
					if "ZValue" in p:
						zval+=1
					elif p != "":
						x,y = p.split("=")[:2]
						x = x.strip()
						if x == "TiltAngle": ang=float(y)
						elif x == "SubFramePath":
							name,ext = y.split('\\')[-1].split(".")
							if os.path.exists("{}/{}.{}".format(args[0],name,ext)):
								info.append([ang,name,ext])
							else:
								print("WARNING: {}.{} was not found in {}".format(name,ext,args[0]))

			sortedlist=sorted(info, key=lambda x: x[0])

			if options.verbose > 0:
				print("File order:")
				for i in sortedlist:
					print("{}\t-\t{}\t{}".format(i[0],i[1],i[2]))
				
			print("\nWriting tilt series to:   {}".format(tiltname))

			for idx,i in enumerate(sortedlist):
				if i[2].lower()=="mrc": infile="-InMrc {}.{} ".format(i[1],i[2])
				if i[2].lower()=="tif": infile+="-InTif {}.{} ".format(i[1],i[2])
				outfile="tmp/{}_ali.mrc".format(i[1])
				output = "-OutMrc {}".format(outfile)
				cmd = "{} {} {} {}".format(program,infile,output,cmdopts)
			
				run(cmd,verbose=options.verbose)

				ali = EMData(outfile)
				ali.write_image(tiltname,idx)
				os.remove(outfile)				
		else:
			
			if os.path.isdir(args[0]):
				dirargs = []
				for f in f in os.listdir(args[0]):
					if ".mrc" in f or ".tif" in f:
						this = "{}/{}".format(args[0],f)
						if os.path.exists(this): dirargs.append(this)
				if len(dirargs) == 0:
					print("Could not find any .mrc or .tif extension files in {}".format(args[0]))
					print("Please try another directory or specify individual files you wish to align.")
					sys.exit(1)
				args = dirargs

			for idx,arg in enumerate(args):
				bname,ext = os.path.basename(arg).split(".")
				output = "micrographs/{}_ali.mrc".format(bname)
				if ext == "tif":
					cmd = "{} -InTiff {} -OutMrc {} {}".format(program,arg,output,cmdopts)
				else:
					cmd = "{} -InMrc {} -OutMrc {} {}".format(program,arg,output,cmdopts)
				run(cmd,verbose=options.verbose)

	print("DONE")



def run(cmd,shell=False,cwd=None,verbose=0):
	if verbose > 0: print(cmd)
	if cwd == None: cwd = os.getcwd()
	if shell == False: cmd = cmd.split()
	p = subprocess.Popen(cmd, shell=shell, cwd=cwd,stderr=subprocess.PIPE)
	_,err=p.communicate()
	return


if __name__ == "__main__":
	main()