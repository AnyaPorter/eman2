#ifndef eman__imagicio_h__
#define eman__imagicio_h__ 1


#include "imageio.h"
#include <stdio.h>

namespace EMAN
{
    /*
      IMAGIC-5 Header File Format

      An IMAGIC-5 file has 2 files:
      a) a header file with the extension ".hed",
      which contains information for every image
      b) an image file with extension ".img",
      which contains only raw data (image densities).

      The header file contains one (fixed-size) record per image
      stored. Every header record consists of 256 REAL/float
      for every image.

      The image file contains only the raw data. Depending on the
      internal IMAGIC-5 format used, which can be REAL, INTG, PACK
      or COMP, the data is stored as REAL/float, INTEGER/int,
      INTEGER*1/byte or 2x REAL/float, respectively. The first pixel
      stored is the upper left one. The data is stored line
      by line, section by section, volume by volume.

      3D imagic uses the same format to 2D. it is a bunch of 2D slices.
      use the 'hint' IS_3D to treat "2D slices" as 3D volume.

      imagic doesn't store multiple 3D images in one file.
    */


    class ImagicIO : public ImageIO
    {
    public:
	ImagicIO(string filename, IOMode rw_mode = READ_ONLY);
	~ImagicIO();

	DEFINE_IMAGEIO_FUNC;
	static bool is_valid(const void *first_block);
	int read_ctf(Ctf & ctf, int image_index = 0);
	int write_ctf(const Ctf & ctf, int image_index = 0);

    private:
	static const char *HED_EXT;
	static const char *IMG_EXT;
	static const char *REAL_TYPE_MAGIC;
	static const char *CTF_MAGIC;


	enum DataType {
	    IMAGIC_UCHAR,
	    IMAGIC_USHORT,
	    IMAGIC_FLOAT,
	    IMAGIC_FLOAT_COMPLEX,
	    IMAGIC_FFT_FLOAT_COMPLEX,
	    IMAGIC_UNKNOWN_TYPE
	};

	enum {
	    NUM_4BYTES_PRE_IXOLD = 14,
	    NUM_4BYTES_AFTER_IXOLD = 14,
	    NUM_4BYTES_AFTER_SPACE = 207
	};

	struct ImagicHeader
	{
	    int imgnum;		// image number, [1,n]
	    int count;		// total number of images - 1 (only first image), [0,n-1]
	    int error;		// Error code for this image
	    int headrec;	// # of header records/image (always 1)
	    int mday;		// image creation time
	    int month;
	    int year;
	    int hour;
	    int minute;
	    int sec;
	    int reals;		// image size in reals
	    int pixels;		// image size in pixels
	    int ny;		// # of lines / image
	    int nx;		// # of pixels / line
	    char type[4];	// PACK, INTG, REAL, COMP, RECO
	    int ixold;		// Top left X-coord. in image before windowing 
	    int iyold;		// Top left Y-coord. in image before windowing 
	    float avdens;	// average density
	    float sigma;	// deviation of density
	    float varia;	// variance of density
	    float oldav;	// old average density
	    float max;		// max density
	    float min;		// min density
	    int complex;	// not used
	    float cellx;	// not used
	    float celly;	// not used
	    float cellz;	// not used
	    float cella1;	// not used
	    float cella2;	// not used
	    char label[80];	// image id string
	    int space[8];
	    float mrc1[4];
	    int mrc2;
	    int space2[7];
	    int lbuf;		// effective buffer len = nx
	    int inn;		// lines in buffer = 1
	    int iblp;		// buffer lines/image = ny
	    int ifb;		// 1st line in buf = 0
	    int lbr;		// last buf line read = -1
	    int lbw;		// last buf line written = 0
	    int lastlr;		// last line called for read = -1
	    int lastlw;		// last line called for write = 1
	    int ncflag;		// decode to complex = 0
	    int num;		// file number = 40 (?)
	    int nhalf;		// leff/2
	    int ibsd;		// record size for r/w (words) = nx*2
	    int ihfl;		// file # = 8
	    int lcbr;		// lin count read buf = -1
	    int lcbw;		// lin count wr buf = 1
	    int imstr;		// calc stat on rd = -1
	    int imstw;		// calc stat on wr = -1
	    int istart;		// begin line in buf = 1
	    int iend;		// end line in buf = nx
	    int leff;		// eff line len = nx
	    int linbuf;		// line len (16 bit) nx *2
	    int ntotbuf;	// total buf in pgm = -1
	    int space3[5];
	    int icstart;	// complex line start = 1
	    int icend;		// complex line end = nx/2
	    int rdonly;		// read only = 0
	    int clsrep;		// EMAN specific, classes represented with 0x7a6b5c00 mask
	    int emanmisc[6];
	    float qual[50];	// quality info from EMAN classification
	    int cls[50];	// number of best class
	    int flags[50];	// eman flags
	};

	int get_datatype_size(DataType t);
	int to_em_datatype(DataType t);
	void make_header_right_endian(ImagicHeader & hed);
	void swap_header(ImagicHeader & hed);
	DataType get_datatype_from_name(const char *name);

    private:
	string filename;
	string hed_filename;
	string img_filename;

	IOMode rw_mode;
	FILE *hed_file;
	FILE *img_file;

	ImagicHeader imagich;
	bool is_big_endian;
	bool initialized;
	bool is_new_hed;
	bool is_new_img;

	DataType datatype;
	int nz;
    };

}


#endif
