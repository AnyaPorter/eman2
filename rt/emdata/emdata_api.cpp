#include "emdata.h"
//#include "EMData.h"

static int terr = 0;

#if 1

/** return 1 if err; 0 if OK */
int cmp_data(EMData *em1, EMAN::EMData *em2)
{
	if (!em1 || !em2) {
		fprintf(stderr, "Error: NULL images in comp_data()\n");
		return 1;
	}

	int nx1 = em1->xSize();
	int ny1 = em1->ySize();
	int nz1 = em1->zSize();

	int nx2 = em2->get_xsize();
	int ny2 = em2->get_ysize();
	int nz2 = em2->get_zsize();

	if (nx1 != nx2 || ny1 != ny2 || nz1 != nz2) {
		fprintf(stderr, "Error: EMAN1(%d,%d,%d) != EMAN2(%d,%d,%d)\n",
				nx1, ny1, nz1, nx2, ny2, nz2);
		return 1;
	}
	
	float *data1 = em1->getDataRO();
	float *data2 = em2->get_data();
	size_t n = nx1 * ny1 * nz1;
	
	for (size_t i = 0; i < n; i++) {
		if (data1[i] != data2[i]) {
			fprintf(stderr, "Error: data difference at %d in comp_data()\n");
			return 1;
		}
	}

	em1->doneData();
	
	return 0;
}

const char* get_test_image()
{
	static char filename[256];
	static bool done = false;
	if (!done) {
		sprintf(filename, "%s/images/groel2d.mrc", getenv("HOME"));
		done = true;
	}
	return filename;
}

int test_rfilter(EMData *em1, int type, float v1, float v2, float v3,
				 EMAN::EMData *em2, string filtername, const EMAN::Dict& params = EMAN::Dict())
{
	fprintf(stdout, "testing real filter EMAN1:%d vs EMAN2:%s :   ",
			type, filtername.c_str());
	int err = cmp_data(em1, em2);
	
	if (!err) {
		EMData *em1copy = em1->copy();
		EMAN::EMData *em2copy = em2->copy();
		
		em1copy->realFilter(type, v1, v2, v3);
		em2copy->filter(filtername, params);

		err = cmp_data(em1copy, em2copy);

		delete em1copy;
		em1copy = 0;

		delete em2copy;
		em2copy = 0;
		
		if (err) {
			fprintf(stderr, "FAILED\n", type, filtername.c_str());
			return err;
		}
		else {
			fprintf(stdout, "PASSED\n");
			return 0;
		}
	}
	else {
		fprintf(stderr, "Error: different input images\n");
		return err;
	}
	return 0;
}
	
void test_filters()
{
	const char *image1 = get_test_image();

	EMData * em1 = new EMData();
	em1->readImage(image1, 0);

	EMAN::EMData *em2 = new EMAN::EMData();
	em2->read_image(image1);
	
	float mean = em2->get_mean();
	
	terr = test_rfilter(em1, 4, 0, 0, 0,
						em2, "AbsoluateValue");

	
	test_rfilter(em1, 6, 0, 0, 0,
				 em2, "Boolean");
	test_rfilter(em1, 18, 0, 0, 0,
				 em2, "ValueSquared");
	test_rfilter(em1, 19, 0, 0, 0,
				 em2, "ValueSqrt");
	//test_rfilter(em1, , 0, 0, 0,
	//			 em2, "ToZero", EMAN::Dict("minval", mean));
	
	test_rfilter(em1, 2, mean, 0, 0,
				 em2, "Binarize", EMAN::Dict("minval", mean));
	//test_rfilter(em1, , 0, 0, 0,
	//			 em2, "Collapse", EMAN::Dict("bottom", mean, "value", mean/2));
	test_rfilter(em1, 11, 2, mean/2, 0,
				 em2, "Exp", EMAN::Dict("low", 2, "high", mean/2));
	test_rfilter(em1, 14, mean/4, mean, 0,
				 em2, "RangeThreshold", EMAN::Dict("low", mean/4, "high", mean));
#if 0
	
	test_rfilter(em1, , 0, 0, 0,
				 em2, "");
	
	test_rfilter(em1, , 0, 0, 0,
				 em2, "");
	
	test_rfilter(em1, , 0, 0, 0,
				 em2, "");
	
	test_rfilter(em1, , 0, 0, 0,
				 em2, "");
#endif

	
	delete em1;
	em1 = 0;
	delete em2;
	em2 = 0;
}

#endif

int main()
{
	test_filters();

	return terr;
}
