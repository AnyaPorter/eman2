#!/usr/bin/env python

import os
import sys
from EMAN2 import *
from EMAN2star import *

def main():

	usage = """Program to convert an ".star" file to .box coordinate format."""

	parser = EMArgumentParser(usage=usage,version=EMANVERSION)

	parser.add_argument("--input",help="""The .star file you wish to convert to .box format""",type=str,required=True)
	parser.add_argument("--output",help="""The name of the .box file to be written""",type=str)
	parser.add_argument("--boxsize",help="""Specify the boxsize for each particle.""",required=True,type=int)
	parser.add_argument("--prepend",help="""Specify a word or phrase to prepend the box file name(s)""",type=str,default="")
	parser.add_argument("--append",help="""Specify a word or phrase to append the box file name(s)""",type=str,default="")
	parser.add_argument("--path",help="""The path to the output generated by this program""",type=str,default=None)
	parser.add_argument("--zfill",help="""Specify the number of zeros to prepend to numbers in order to correct file names. For example, specifying 4 will turn '1' to '0001'. Specifying 3 will turn '34' into '034'. Specifying 2 will turn '25' into '25'.""",type=int)
	(options, args) = parser.parse_args()
	
	if not options.path: options.path = os.getcwd()
	
	if os.path.exists(options.input): starf = StarFile(options.input)
	else:
		print(("Sorry, could not locate {}".format(options.input))) 
		exit(-1)
	
	if options.output:
		if options.output.split('.')[-1] != "box":
			f = options.output.split('.')
			if len(f) > 2: bn = ".".join(f[:-2])
			else: bn = f[-2]
			print(("Writing to {base}.box rather than {base}.{ext}".format(base=bn,ext=f[-1])))
			options.output = bn + ".box"
		if options.prepend: options.output = options.prepend + "_" + options.output
		if options.append: options.output = options.output.split('.')[0] + "_" + options.append + ".box"
		
	bs = int(options.boxsize/2)
	
	logger = E2init(sys.argv)
	
	hdr = starf.keys()
	
	# resolve correct micrograph dictionary key
	
	mks = [i for i in hdr if "Micrograph" in i]
	if len(mks) >= 1:
		if len(mks) > 1:
			print("There are multiple header labels containing the word 'Micrograph':")
			for mk in mks:
				print(mk)
			print(("Using {}\n".format(mks[0])))
		mk = mks[0]
		mgs = list(set(starf[mk]))
		nmgs = len(mgs)
	else: 
		nmgs = 1
	
	xk = [i for i in hdr if "X" in i]
	yk = [i for i in hdr if "Y" in i]
	
	## resolve correct x and y dictionary keys
	
	if len(xk) == 1: # case 1: only one X key
		xk = xk[0]
		if not options.output:
			print("No output file name was specified. Will use the input basename as output.")
			options.output = options.input.split('.')[0] + ".box"
	elif len(xk) > 1: # case 2: multiple xk
		print("There are multiple header labels containing 'X':")
		for k in xk:
			print(k)
		xk = [i for i in xk if "Coordinate" in i][0]
		print(("Using {}\n".format(xk)))
	else: # case 3: no xk
		print("Could not find any keys containing 'X'")
		exit(-1)
	
	if len(yk) == 1: # case 1: only one Y key
		yk = yk[0]
	elif len(yk) > 1: # case 2: multiple yk
		print("There are multiple header labels containing 'Y':")
		for k in yk:
			print(k)
		yk = [i for i in yk if "Coordinate" in i][0]
		print(("Using {}\n".format(yk)))
	else: # case 3: no xk
		print("Could not find any keys containing 'Y'")
		exit(-1)
	
	## Read data and write to file (we read only one micrograph worth of particles at once for a small memory footprint)

	# case 1: file pertains to one micrograph
	if nmgs == 1:
		with open(options.output,'w+') as boxf:
			for x,y in zip(starf[xk],starf[yk]):
				boxf.write("{}\t{}\t{}\t{}\n".format(int(x-bs/2),int(y-bs/2),2*bs,2*bs))
	# case 2: multiple micrographs in file
	elif nmgs > 1:
		newpth = options.path + "/" + os.path.basename(options.input).split('.')[0]
		try: os.makedirs(newpth)
		except: pass
		for mg in mgs:
			boxfile = str(mg)
			if options.zfill: boxfile = boxfile.zfill(options.zfill)
			boxfile = boxfile.split('/')[-1].split('.')[0] + ".box"
			if options.prepend: boxfile = options.prepend + "_" + boxfile
			if options.append: boxfile = boxfile.split('.')[0] + "_" + options.append + ".box"
			ptcls = [i for i,m in enumerate(starf[mk]) if m == mg]
			print(boxfile)
			with open(newpth + "/" + boxfile,'w+') as boxf:
				for ptcl in ptcls:
					x = starf[xk][ptcl]
					y = starf[yk][ptcl]
					boxf.write("{}\t{}\t{}\t{}\n".format(int(x-bs/2),int(y-bs/2),2*bs,2*bs))
	
	E2end(logger)

	return

if __name__ == "__main__":
	main()
