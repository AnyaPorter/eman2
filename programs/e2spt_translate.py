#!/usr/bin/env python

#
# Author: Jesus Galaz, 10/20/2012; last update July/26/2015
# Copyright (c) 2011 Baylor College of Medicine
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
#

import os
from EMAN2 import *
import math	 

	
def main():
	
	progname = os.path.basename(sys.argv[0])
	usage = """WARNING:  **PRELIMINARY** program, still heavily under development. 
				Autoboxes globular particles from tomograms.
				Note that self-generated spherical templates generated by this program
				are 'white'; which means you have to provide the tomogram with inverted (or 'white') contrast, and the same goes for any stacks
				provided (specimen particles, gold, carbon and/or background)."""
			
	parser = EMArgumentParser(usage=usage,version=EMANVERSION)
	
	
	parser.add_argument("--parallel",type=str,default='',help="""Default=Auto. This program will detect the number of CPU cores on your machine and parallelize some of the tasks using all of them. To disable, provide --parallel=None""")
	
	parser.add_argument("--input", type=str,default='', help="""Default=None. HDF stack of volumes to translate""")

	parser.add_argument("--alistack", type=str,default='', help="""Default=None. HDF stack of volumes with alignment parameters on the header from which translations will be read and applied to --input.""")

	parser.add_argument("--alifile", type=str,default='', help=""".json file from where to read alignment parameters. Alternative to --alistack.""")

	parser.add_argument("--path",default='',type=str,help="Default=spttranslate. Name of directory where to save the output file.")

	parser.add_argument("--ppid", type=int, help="Set the PID of the parent process, used for cross platform PPID",default=-1)
	
	parser.add_argument("--verbose", "-v", dest="verbose", action="store", metavar="n",type=int, default=0, help="verbose level [0-9], higner number means higher level of verboseness")
	
	parser.add_argument("--subset",type=int,default=0,help="""default=0 (not used). Subset of particles to process.""")
	(options, args) = parser.parse_args()	#c:this parses the options or "arguments" listed 
											#c:above so that they're accesible in the form of option.argument; 
											#c:for example, the input for --template would be accesible as options.template
		
	logger = E2init(sys.argv, options.ppid)	#c:this initiates the EMAN2 logger such that the execution
											#of the program with the specified parameters will be logged
											#(written) in the invisible file .eman2log.txt
	
	'''
	c:make a directory to store output generated by this program
	'''
	from e2spt_classaverage import sptmakepath
	options = sptmakepath(options,'spttranslate')

	n = EMUtil.get_image_count( options.input )
	orign = n
	print("\nnumber of particles in stack %s is %d" %(options.input,n))
	
	if options.subset:
		n = options.subset

	if options.alistack:
		n2 = EMUtil.get_image_count( options.alistack )
		if n > n2:
			print("""\nERROR: there are fewer particles in --alistack, %d, than in --input, %d. 
				Use --subset and set it to a number equal to or smaller than the number or particles in --alistack""" %(n2,n))
			sys.exit(1)

	if options.alifile:
		preOrientationsDict = js_open_dict(options.alifile)

	txs=[]
	tys=[]
	tzs=[]
	trs=[]

	outstack = options.path + '/' + os.path.basename(options.input).replace('.hdf','_trans.hdf')

	for i in range(n):	
		print("\nreading particle %d" %(i))	
		a=EMData( options.input, i)
		
		ptcl = a.copy()
		
		t=None
		if options.alifile:
			ID ='subtomo_' + str(i).zfill(len(str( orign )))
			t = preOrientationsDict[ID][0]
		elif options.alistack:
			b=EMData(options.alistack,i,True)
			t = b['xform.align3d']
		
		ptcl['origin_x'] = 0
		ptcl['origin_y'] = 0
		ptcl['origin_z'] = 0
		ptcl['xform.align3d'] = Transform()
		
		if t:
			print("transform is t",t)
			trans = t.get_trans()
			rot = t.get_rotation()
			
			az = rot['az']
			alt = rot['alt']
			phi = rot['phi']

			trot = Transform({'type':'eman','az':az,'alt':alt,'phi':phi})
			troti = trot.inverse()

			transi =troti*trans 	#translations are in the frame of the rotated particle.
									#to apply translations only, you need to convert them to the unrotated frame

			tx = transi[0]
			txs.append(math.fabs(tx))

			ty = transi[1]
			tys.append(math.fabs(ty))

			tz = transi[2]
			tzs.append(math.fabs(tz))

			tr=math.sqrt(tx*tx+ty*ty+tz*tz)
			trs.append(tr)

			newt = Transform({'type':'eman','tx':tx,'ty':ty,'tz':tz})
			print("new transform is", newt)

			ptcl.transform(newt)
			ptcl['xform.align3d'] = newt
			#if options.saveali:
			print("\nsaving translated particle",i)
			ptcl.write_image( outstack, i )
		
	
	outavg = options.path + '/' + os.path.basename(options.input).replace('.hdf','_trans_avg.hdf')
	cmd = 'e2proc3d.py ' + outstack + ' ' + outavg + ' --average'
	cmd += ' && e2proc3d.py ' + outavg + ' ' + outavg + ' --process normalize.edgemean'	
	os.system( cmd )

	if options.alifile:
		preOrientationsDict.close()			
	
	from e2spt_classaverage import textwriter

	if txs:
		txs.sort()
		textwriter(txs,options,'x_trans.txt')

	if tys:
		tys.sort()
		textwriter(tys,options,'y_trans.txt')

	if tzs:
		tzs.sort()
		textwriter(tzs,options,'z_trans.txt')
	
	if trs:
		trs.sort()
		textwriter(trs,options,'r_trans.txt')


	E2end(logger)
	
	return 


if '__main__' == __name__:
	main()
	
