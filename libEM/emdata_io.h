/*
 * Author: Steven Ludtke, 04/10/2003 (sludtke@bcm.edu)
 * Probable contributing author: Liwei Peng
 * Copyright (c) 2000-2006 Baylor College of Medicine
 *
 * This software is issued under a joint BSD/GNU license. You may use the
 * source code in this file under either license. However, note that the
 * complete EMAN2 and SPARX software packages have some GPL dependencies,
 * so you are responsible for compliance with the licenses of these packages
 * if you opt to use BSD licensing. The warranty disclaimer below holds
 * in either instance.
 *
 * This complete copyright notice must be included in any revised version of the
 * source code. Additional authorship citations may be added, but existing
 * author citations must be preserved.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
 *
 * */

/** This file is a part of "emdata.h", to use functions in this file,
 * you should "#include "emdata.h",
 * NEVER directly include this file. */

#ifndef emdata__io_h__
#define emdata__io_h__


private:
void _read_image(ImageIO *imageio, int img_index = 0,
				bool header_only = false,
				const Region * region = 0, bool is_3d = false);

void _write_image(ImageIO *imageio,
				 int img_index = 0,
				 EMUtil::ImageType imgtype = EMUtil::IMAGE_UNKNOWN,
				 bool header_only = false,
				 const Region * region = 0,
				 EMUtil::EMDataType filestoragetype = EMUtil::EM_FLOAT,
				 bool use_host_endian = true);

public:
/** read an image file and stores its information to this
 * EMData object.
 *
 * If a region is given, then only read a
 * region of the image file. The region will be this
 * EMData object. The given region must be inside the given
 * image file. Otherwise, an error will be created.
 *
 * @param filename The image file name.
 * @param img_index The nth image you want to read.
 * @param header_only To read only the header or both header and data.
 * @param region To read only a region of the image.
 * @param is_3d  Whether to treat the image as a single 3D or a
 *   set of 2Ds. This is a hint for certain image formats which
 *   has no difference between 3D image and set of 2Ds.
 * @exception ImageFormatException
 * @exception ImageReadException
 */
void read_image(const string & filename, int img_index = 0,
				bool header_only = false,
				const Region * region = 0, bool is_3d = false,
				EMUtil::ImageType imgtype = EMUtil::IMAGE_UNKNOWN);

/** read in a binned image, bin while reading. For use in huge files(tomograms)
 * @param filename The image file name.
 * @param img_index The nth image you want to read.
 * @param binfactor The amout you want to bin by. Must be an integer
 * @param fast Only bin xy slice every binfactor intervals, otherwise meanshrink z
 * @param is_3d  Whether to treat the image as a single 3D or a
 *   set of 2Ds. This is a hint for certain image formats which
 *   has no difference between 3D image and set of 2Ds.
 * @exception ImageFormatException
 * @exception ImageReadException
 */
void read_binedimage(const string & filename, int img_index = 0, int binfactor=0, bool fast = false, bool is_3d = false);


/** write the header and data out to an image.
 *
 * If the img_index = -1, append the image to the given image file.
 *
 * If the given image file already exists, this image
 * format only stores 1 image, and no region is given, then
 * truncate the image file  to  zero length before writing
 * data out. For header writing only, no truncation happens.
 *
 * If a region is given, then write a region only.
 *
 * @param filename The image file name.
 * @param img_index The nth image to write as.
 * @param imgtype Write to the given image format type. if not
 *        specified, use the 'filename' extension to decide.
 * @param header_only To write only the header or both header and data.
 * @param region Define the region to write to.
 * @param filestoragetype The image data type used in the output file.
 * @param use_host_endian To write in the host computer byte order.
 *
 * @exception ImageFormatException
 * @exception ImageWriteException
 */
void write_image(const string & filename,
				 int img_index = 0,
				 EMUtil::ImageType imgtype = EMUtil::IMAGE_UNKNOWN,
				 bool header_only = false,
				 const Region * region = 0,
				 EMUtil::EMDataType filestoragetype = EMUtil::EM_FLOAT,
				 bool use_host_endian = true);


/** append to an image file; If the file doesn't exist, create one.
 *
 * @param filename The image file name.
 * @param imgtype Write to the given image format type. if not
 *        specified, use the 'filename' extension to decide.
 * @param header_only To write only the header or both header and data.
 */
void append_image(const string & filename,
				  EMUtil::ImageType imgtype = EMUtil::IMAGE_UNKNOWN,
				  bool header_only = false);

/** Append data to a LST image file.
 * @param filename The LST image file name.
 * @param reffile Reference file name.
 * @param refn The reference file number.
 * @param comment The comment to the added reference file.
 * @see lstio.h
 */
void write_lst(const string & filename,
			   const string & reffile="", int refn=-1,
			   const string & comment="");


/** Read a set of images from file specified by 'filename'.
 * Which images are read is set by 'img_indices'.
 * @param filename The image file name.
 * @param img_indices Which images are read. If it is empty,
 *     all images are read. If it is not empty, only those
 *     in this array are read.
 * @param header_only If true, only read image header. If
 *     false, read both data and header.
 * @return The set of images read from filename.
 */
static vector<std::shared_ptr<EMData>> read_images(const string & filename,
									  vector<int> img_indices = vector<int>(),
									  EMUtil::ImageType imgtype = EMUtil::IMAGE_UNKNOWN,
									  bool header_only = false);

/** Write a set of images to file specified by 'filename'.
 * Which images are written is set by 'imgs'.
 * @param filename The image file name.
 * @param imgs Which images are written.
 * @param imgtype Write to the given image format type. if not
 *        specified, use the 'filename' extension to decide.
 * @param header_only To write only the header or both header and data.
 * @param region Define the region to write to.
 * @param filestoragetype The image data type used in the output file.
 * @param use_host_endian To write in the host computer byte order.
 * @return True if set of images are written successfully to filename.
 */
static bool write_images(const string & filename,
									vector<std::shared_ptr<EMData>> imgs,
									int idxs=0,
									EMUtil::ImageType imgtype = EMUtil::IMAGE_UNKNOWN,
									bool header_only = false,
									const Region * region = nullptr,
									EMUtil::EMDataType filestoragetype = EMUtil::EM_FLOAT,
									bool use_host_endian = true);

friend ostream& operator<<(ostream& out, const EMData& obj);

#endif	//emdata__io_h__
