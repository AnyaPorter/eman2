#!/usr/bin/env python

#
# Author: Steven Ludtke, 04/10/2003 (sludtke@bcm.edu)
# Copyright (c) 2000-2006 Baylor College of Medicine
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

# $Id$

# todo: verify the processors who have the same names in proc3d
#	   and proc2d have the same implementation
#
# todo: lp, hp, tlp vs apix

from EMAN2 import *
from optparse import OptionParser
import sys
import os.path
import pyemtbx.options

def print_iminfo(data, label):
	print "%s image : %dx%dx%d Mean=%1.3g Sigma=%1.3g Min=%1.3g Max=%1.3g" % \
	(label, data.get_xsize(), data.get_ysize(), data.get_zsize(),
	 data.get_attr("mean"), data.get_attr("sigma"),
	 data.get_attr("minimum"), data.get_attr("maximum"))


def main():
    progname = os.path.basename(sys.argv[0])
    usage = progname + " options inputfile outputfile"
    parser = OptionParser(usage)
    
    parser.add_option("--shrink", metavar="n", type="int", action="append", 
                                help="Shrinks the image by integer n using median filter")

    parser.add_option("--scale", metavar="n", type="float", action="append",
                                help="Rescales the image by 'n', generally used with clip option.")

    parser.add_option("--clip", metavar="x y z xc yc zc", type="float", nargs=6, action="append",
                                help="Make the output have this size, no scaling. ")
    
    parser.add_option("--fftclip", metavar="x y z", type="float", nargs=3, action="append",
                                help="Make the output have this size, rescaling by padding FFT.")

    parser.add_option("--filter", metavar="filtername:param1=val1:param2=val2", type="string", action="append",
                                help="Apply a filter named 'filtername' with all its parameters/values.")

    parser.add_option("--apix", type="float", help="A/pixel for S scaling")
    
    parser.add_option("--origin", metavar="x y z", type="float", nargs=3,
                                help="Set the coordinates for the pixel (0,0,0).")

    parser.add_option("--mult", metavar="f", type="float", 
                                help="Scales the densities by 'f' in the output")
    
    parser.add_option("--mrc16bit",  action="store_true", help="output as 16 bit MRC file")
    parser.add_option("--mrc8bit",  action="store_true", help="output as 8 bit MRC file")
    
    parser.add_option("--add", metavar="f", type="float", 
                                help="Adds a constant 'f' to the densities")
    
    parser.add_option("--calcsf", type="string", metavar="outputfile",
                                help="Calculate a radial structure factor. Must specify apix.")
    
    parser.add_option("--tophalf", action="store_true",
                                help="The output only keeps the top half map")
    
    parser.add_option("--icos5fhalfmap", action="store_true",
                                help="The input is the icos 5f top half map generated by the 'tophalf' option")
    
    parser.add_option("--outtype", metavar="image-type", type="string", 
                                help="Set output image format, mrc, imagic, hdf, etc")

    parser.add_option("--first", metavar="n", type="int", default=0, 
                                help="the first image in the input to process [0 - n-1])")

    parser.add_option("--trans", metavar="dx,dy,dz", type="string", default=0, help="Translate map by dx,dy,dz ")

    parser.add_option("--rot", metavar="az,alt,phi or convention,a1,a2,a3,a4", type="string", default=0, help="Rotate map using EMAN Euler angles z,x,z' or an arbitrary convention")

    parser.add_option("--last", metavar="n", type="int", default=-1, 
                                help="the last image in the input to process")
    
    parser.add_option("--swap", action="store_true", help="Swap the byte order", default=False)	
    
    append_options = ["clip", "fftclip", "filter", "shrink", "scale"]
    
    optionlist = pyemtbx.options.get_optionlist(sys.argv[1:])
    
    (options, args) = parser.parse_args()
    
    if len(args) != 2:
        print "usage: " + usage
        print "Please run '" + progname + " -h' for detailed options"
        sys.exit(1)
    
    infile = args[0]
    outfile = args[1]
    
    n0 = options.first
    n1 = options.last
    nimg = EMUtil.get_image_count(infile)
    
    index_d = {}
    for append_option in append_options:
        index_d[append_option] = 0
    
    if(n0 < 0 or n0 > nimg):
        print "Your first index is out of range, changed to zero"
        n0 = 0
    
    if(n1 == -1): 
        n1 = nimg-1
    elif(n1 > nimg-1):
        print "Your last index is out of range, changed to %d" % (nimg-1)
        n1 = nimg-1
    
    datlst = parse_infile(infile, n0, n1)
    
    x = datlst[0].get_xsize()
    y = datlst[0].get_ysize()
    z = datlst[0].get_zsize()
    
    xc = x/2
    yc = y/2
    zc = z/2
    
    nx = x
    ny = y
    nz = z

    #print_iminfo(datlst[0], "Original")
    
    apix = -1
    if options.apix:
        apix = options.apix
        for data in datlst:
            data.set_attr('apix_x', apix)
            data.set_attr('apix_y', apix)
            data.set_attr('apix_z', apix)

    if not "outtype" in optionlist:
	    optionlist.append("outtype")

    print "%d images, processing %d-%d......"%(nimg, n0, n1)
    #print 'start.....'
    for data in datlst:
        for option1 in optionlist:				
            if option1 == "origin":
                (originx, originy, originz) = options.origin
                data.set_xyz_origin(originx, originy, originz)

            elif option1 == "calcsf":
                dataf = data.do_fft()
                curve = dataf.calc_radial_func(y, 0, 0.5)
                Util.save_data(0, 1.0/(apix*2.0*y), curve, options.calcsf);

            elif option1 == "filter":
                fi = index_d[option1]
                (filtername, param_dict) = parsemodopt(options.filter[fi])
                data.process_inplace(filtername, param_dict)
                index_d[option1] += 1

            elif option1 == "mult":
                data.mult(options.mult)

            elif option1 == "add":
                data.add(options.add)
            
            elif option1 == "trans":
            	dx,dy,dz=options.trans.split(",")
            	data.translate(float(dx),float(dy),float(dz))
            
            elif option1 == "rot":
            	parm=parsemodopt(options.rot)
            	data.rotate(Transform3D(EULER[parm[0].lower()],parm[1]))
		
            elif option1 == "clip":
                ci = index_d[option1]
                (nx, ny, nz, xc, yc, zc) = options.clip[ci]

                if not (xc>=0 and yc>=0 and zc>=0 and xc<x and yc<y and zc<z):
                    xc = x/2
                    yc = y/2
                    zc = z/2
                    
                if x != nx or y != ny or z != nz:
                	data = data.get_clip(Region(xc-nx/2, yc-ny/2, zc-nz/2, nx, ny, nz))
                	index_d[option1] += 1

            elif option1 == "scale":
                scale_f = options.scale[index_d[option1]]
                if scale_f != 1.0:
                    data.scale(scale_f)
                index_d[option1] += 1

            elif option1 == "shrink":
                shrink_f = options.shrink[index_d[option1]]
                if shrink_f > 1:
                    data.process_inplace("math.medianshrink",{"n":shrink_f})
                    nx = data.get_xsize()
                    ny = data.get_ysize()
                    nz = data.get_zsize()
                index_d[option1] += 1

            elif option1 == "fftclip":
                fi = index_d[option1]
                (fnx, fny, fnz) = options.fftclip[fi]
                fft = data.do_fft()
                padfft = fft.clip(Region(0, 0, 0, fnx+2, fny, fnz))
                data = padfft.do_ift()
                index_d[option1] += 1

            elif option1 == "icos5fhalfmap":
                print "not implemented yet"

            elif option1 == "tophalf":
                half = data.get_top_half()
                data = half
                
            elif option1 == "outtype":
				if not options.outtype:
					options.outtype = "unknown"

        #print_iminfo(data, "Final")
        
        if 'mrc8bit' in optionlist:
        	data.write_image(outfile.split('.')[0]+'.mrc', -1, EMUtil.ImageType.IMAGE_MRC, False, None, EMUtil.EMDataType.EM_UCHAR, not(options.swap))
        elif 'mrc16bit' in optionlist:
        	data.write_image(outfile.split('.')[0]+'.mrc', -1, EMUtil.ImageType.IMAGE_MRC, False, None, EMUtil.EMDataType.EM_USHORT, not(options.swap))
        else:
    	    data.write_image(outfile, -1, EMUtil.get_image_ext_type(options.outtype), False, None, EMUtil.EMDataType.EM_FLOAT, not(options.swap))

#parse_file() wil read the input image file and return a list of EMData() object
def parse_infile(infile, first, last):
	nimg = EMUtil.get_image_count(infile)
	
	if (nimg > 1):
		#print "it appears %s contains %d image" % (infile, nimg)
		d = EMData()
		d.read_image(infile, 0)
	
		x = d.get_xsize()
		y = d.get_ysize()
		z = d.get_zsize()
		if (z == 1):
			print "the images are 2D - I will now make a 3D image out of the 2D images"
			data = []
			return_data = EMData()
			return_data.set_size(x, y, nimg)
			for i in range(0, nimg):
				d.read_image(infile, i)
				print i, nimg
				return_data.insert_clip(d, (0, 0, i))
			data.append(return_data)	
			return data
		else:
			print "the image is a 3D stack - I will process images from %d to %d" % (first, last)
			data = []
			for i in xrange(first, last+1):
				d.read_image(infile, i)
				data.append(d)
			return data
	else:
		data = []
		d = EMData()
		d.read_image(infile)
		data.append(d)
		return data
	

if __name__ == "__main__":
	main()
