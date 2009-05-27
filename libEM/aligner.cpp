/**
 * $Id$
 */

/*
 * Author: Steven Ludtke, 04/10/2003 (sludtke@bcm.edu)
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

#include "cmp.h"
#include "aligner.h"
#include "emdata.h"
#include "processor.h"
#include "util.h"
#include <gsl/gsl_multimin.h>

#ifdef EMAN2_USING_CUDA
	#include <sparx/cuda/cuda_ccf.h>
#endif

#define EMAN2_ALIGNER_DEBUG 0

using namespace EMAN;

template <> Factory < Aligner >::Factory()
{
	force_add(&TranslationalAligner::NEW);
	force_add(&RotationalAligner::NEW);
	force_add(&RotatePrecenterAligner::NEW);
	force_add(&RotateTranslateAligner::NEW);
// 	force_add(&RotateTranslateBestAligner::NEW);
	force_add(&RotateFlipAligner::NEW);
	force_add(&RotateTranslateFlipAligner::NEW);
	force_add(&RTFExhaustiveAligner::NEW);
	force_add(&RTFSlowExhaustiveAligner::NEW);
	force_add(&RefineAligner::NEW);
}

Transform* Aligner::get_set_align_attr(const string& key, EMData* const image, const EMData* const from_image  )
{
	// WARNING - THIS APPROACH CURRENTLY CAUSES A MEMORY LEAK.
	Transform* t;
	if (from_image->has_attr(key) ) {
		t = new Transform( *((Transform*)from_image->get_attr(key)) );
	}
	else {
		t = new Transform();
	}
	image->set_attr(key,t);
	image->set_attr_owned(key);
	return t;
}

Transform* Aligner::get_align_attr(const string& key, EMData* const image  )
{
	if (image->has_attr(key) ) return (Transform*) image->get_attr(key);
	else {
		Transform* t = new Transform;
		image->set_attr(key,t);
		return t;
	}
}


// Note, the translational aligner assumes that the correlation image
// generated by the calc_ccf function is centered on the bottom left corner
// That is, if you did at calc_cff using identical images, the
// peak would be at 0,0
EMData *TranslationalAligner::align(EMData * this_img, EMData *to,
					const string&, const Dict&) const
{
	if (!this_img) {
		return 0;
	}

	if (to && !EMUtil::is_same_size(this_img, to))
		throw ImageDimensionException("Images must be the same size to perform translational alignment");

	EMData *cf = 0;

	bool use_cpu = true;
#ifdef EMAN2_USING_CUDA
	if (this_img->gpu_operation_preferred() ) {
// 		cout << "Translate on GPU" << endl;
		use_cpu = false;
		cf = this_img->calc_ccf_cuda(to,false,false);
	}
#endif // EMAN2_USING_CUDA
	if (use_cpu) cf = this_img->calc_ccf(to);

//
	int nx = this_img->get_xsize();
	int ny = this_img->get_ysize();
	int nz = this_img->get_zsize();

	int maxshiftx = params.set_default("maxshift",-1);
	int maxshifty = params["maxshift"];
	int maxshiftz = params["maxshift"];
	int nozero = params["nozero"];

	if (maxshiftx <= 0) {
		maxshiftx = nx / 8;
		maxshifty = ny / 8;
		maxshiftz = nz / 8;
	}

	if (maxshiftx > nx / 2 - 1) maxshiftx = nx / 2 - 1;
	if (maxshifty > ny / 2 - 1)	maxshifty = ny / 2 - 1;
	if (maxshiftz > nz / 2 - 1) maxshiftz = nz / 2 - 1;

	if (nx == 1) maxshiftx = 0; // This is justhere for completeness really... plus it saves errors
	if (ny == 1) maxshifty = 0;
	if (nz == 1) maxshiftz = 0;

	// If nozero the portion of the image in the center (and its 8-connected neighborhood) is zeroed
	if (nozero) {
		cf->zero_corner_circulant(1);
	}

	IntPoint peak;
#ifdef EMAN2_USING_CUDA
	if (!use_cpu) {
		EMDataForCuda tmp = cf->get_data_struct_for_cuda();
		int* p = calc_max_location_wrap_cuda(&tmp,maxshiftx, maxshifty, maxshiftz);
		peak = IntPoint(p[0],p[1],p[2]);
		free(p);
	}
#endif // EMAN2_USING_CUDA
	if (use_cpu) {
		peak = cf->calc_max_location_wrap(maxshiftx, maxshifty, maxshiftz);
	}
	Vec3f cur_trans = Vec3f ( (float)-peak[0], (float)-peak[1], (float)-peak[2]);

	if (!to) {
		cur_trans /= 2.0f; // If aligning theimage to itself then only go half way -
		int intonly = params.set_default("intonly",false);
		if (intonly) {
			cur_trans[0] = floor(cur_trans[0] + 0.5f);
			cur_trans[1] = floor(cur_trans[1] + 0.5f);
			cur_trans[2] = floor(cur_trans[2] + 0.5f);
		}
	}

	if( cf ){
		delete cf;
		cf = 0;
	}
	Dict params("trans",static_cast< vector<int> >(cur_trans));
	cf=this_img->process("math.translate.int",params);

	if ( nz != 1 ) {
		Transform* t = get_set_align_attr("xform.align3d",cf,this_img);
		t->set_trans(cur_trans);
	} else if ( ny != 1 ) {
		Transform* t = get_set_align_attr("xform.align2d",cf,this_img);
		cur_trans[2] = 0; // just make sure of it
		t->set_trans(cur_trans);
	}

	return cf;
}

EMData * RotationalAligner::align_180_ambiguous(EMData * this_img, EMData * to, int rfp_mode) {

	// Make translationally invariant rotational footprints
	EMData* this_img_rfp, * to_rfp;
	if (rfp_mode == 0) {
		this_img_rfp = this_img->make_rotational_footprint_e1();
		to_rfp = to->make_rotational_footprint_e1();
	} else if (rfp_mode == 1) {
		this_img_rfp = this_img->make_rotational_footprint();
		to_rfp = to->make_rotational_footprint();
	} else if (rfp_mode == 2) {
		this_img_rfp = this_img->make_rotational_footprint_cmc();
		to_rfp = to->make_rotational_footprint_cmc();
	} else {
		throw InvalidParameterException("rfp_mode must be 0,1 or 2");
	}
	int this_img_rfp_nx = this_img_rfp->get_xsize();

	// Do row-wise correlation, returning a sum.
	EMData *cf = this_img_rfp->calc_ccfx(to_rfp, 0, this_img->get_ysize());

	// Delete them, they're no longer needed
	delete this_img_rfp; this_img_rfp = 0;
	delete to_rfp; to_rfp = 0;

	// Now solve the rotational alignment by finding the max in the column sum
	float *data = cf->get_data();
	float peak = 0;
	int peak_index = 0;
	Util::find_max(data, this_img_rfp_nx, &peak, &peak_index);

	if( cf ) {
		delete cf;
		cf = 0;
	}
	float rot_angle = (float) (peak_index * 180.0f / this_img_rfp_nx);

	// Return the result
	Transform tmp(Dict("type","2d","alpha",rot_angle));
	cf=this_img->process("math.transform",Dict("transform",(Transform*)&tmp));
	Transform* t = get_set_align_attr("xform.align2d",cf,this_img);
	Dict d("type","2d","alpha",rot_angle);
	t->set_rotation(d);
	return cf;
}

EMData *RotationalAligner::align(EMData * this_img, EMData *to,
			const string& cmp_name, const Dict& cmp_params) const
{
	if (!to) throw InvalidParameterException("Can not rotational align - the image to align to is NULL");

	// Perform 180 ambiguous alignment
	int rfp_mode = params.set_default("rfp_mode",0);
	EMData* rot_aligned = RotationalAligner::align_180_ambiguous(this_img,to,rfp_mode);
	Transform * tmp = rot_aligned->get_attr("xform.align2d");
	Dict rot = tmp->get_rotation("2d");
	float rotate_angle_solution = rot["alpha"];

	// Get a copy of the rotationally aligned image that is rotated 180
// 	cout << "rot aligned gpu? " << rot_aligned->gpu_operation_preferred() << endl;
	EMData *rot_align_180 = rot_aligned->process("math.rotate.180");
// 	cout << "rot aligned 180 gpu? " << rot_align_180->gpu_operation_preferred() << to->gpu_operation_preferred() << endl;;
	// Generate the comparison metrics for both rotational candidates
	float rot_cmp = rot_aligned->cmp(cmp_name, to, cmp_params);
// 	cout << "And then " << to->gpu_operation_preferred() << endl;
	float rot_180_cmp = rot_align_180->cmp(cmp_name, to, cmp_params);
// 	cout << "sssrot aligned 180 gpu? " << rot_align_180->gpu_operation_preferred() <<	endl;
	// Decide on the result
	float score = 0.0;
	EMData* result = NULL;
	if (rot_cmp < rot_180_cmp){
		result = rot_aligned;
		score = rot_cmp;
		delete rot_align_180; rot_align_180 = 0;
	} else {
		result = rot_align_180;
		score = rot_180_cmp;
		delete rot_aligned; rot_aligned = 0;
		rotate_angle_solution = rotate_angle_solution-180.0;
	}

	Transform* t = get_align_attr("xform.align2d",result);
	t->set_rotation(Dict("type","2d","alpha",rotate_angle_solution));

	return result;
}


EMData *RotatePrecenterAligner::align(EMData * this_img, EMData *to,
			const string&, const Dict&) const
{
	if (!to) {
		return 0;
	}

	int ny = this_img->get_ysize();
	int size = Util::calc_best_fft_size((int) (M_PI * ny * 1.5));
	EMData *e1 = this_img->unwrap(4, ny * 7 / 16, size, 0, 0, 1);
	EMData *e2 = to->unwrap(4, ny * 7 / 16, size, 0, 0, 1);
	EMData *cf = e1->calc_ccfx(e2, 0, ny);

	float *data = cf->get_data();

	float peak = 0;
	int peak_index = 0;
	Util::find_max(data, size, &peak, &peak_index);
	float a = (float) ((1.0f - 1.0f * peak_index / size) * 180. * 2);
	this_img->transform(Dict("type","2d","alpha",(float)(a*180./M_PI)));

	Transform* t = get_set_align_attr("xform.align2d",cf,this_img);
	t->set_rotation(Dict("type","2d","alpha",-a));
	cf->update();

	if( e1 )
	{
		delete e1;
		e1 = 0;
	}

	if( e2 )
	{
		delete e2;
		e2 = 0;
	}

	return cf;
}

EMData *RotateTranslateAligner::align(EMData * this_img, EMData *to,
			const string & cmp_name, const Dict& cmp_params) const
{
	// Get the 180 degree ambiguously rotationally aligned and its 180 degree rotation counterpart
	int rfp_mode = params.set_default("rfp_mode",0);
	EMData *rot_align  =  RotationalAligner::align_180_ambiguous(this_img,to,rfp_mode);
	Transform * tmp = rot_align->get_attr("xform.align2d");
	Dict rot = tmp->get_rotation("2d");
	float rotate_angle_solution = rot["alpha"];

	EMData *rot_align_180 = rot_align->copy();
	rot_align_180->process_inplace("math.rotate.180");

	Dict trans_params;
	trans_params["intonly"]  = 0;
	trans_params["maxshift"] = params.set_default("maxshift", -1);

	// Do the first case translational alignment
	trans_params["nozero"]   = params.set_default("nozero",false);
	EMData* rot_trans = rot_align->align("translational", to, trans_params, cmp_name, cmp_params);
	if( rot_align ) { // Clean up
		delete rot_align;
		rot_align = 0;
	}

	// Do the second case translational alignment
	EMData*  rot_180_trans = rot_align_180->align("translational", to, trans_params, cmp_name, cmp_params);
	if( rot_align_180 )	{ // Clean up
		delete rot_align_180;
		rot_align_180 = 0;
	}

	// Finally decide on the result
	float cmp1 = rot_trans->cmp(cmp_name, to, cmp_params);
	float cmp2 = rot_180_trans->cmp(cmp_name, to, cmp_params);

	EMData *result = 0;
	if (cmp1 < cmp2) { // Assumes smaller is better - thus all comparitors should support "smaller is better"
		if( rot_180_trans )	{
			delete rot_180_trans;
			rot_180_trans = 0;
		}
		result = rot_trans;
	}
	else {
		if( rot_trans )	{
			delete rot_trans;
			rot_trans = 0;
		}
		result = rot_180_trans;
		rotate_angle_solution -= 180.f;
	}

	Transform* t = result->get_attr("xform.align2d");
	t->set_rotation(Dict("type","2d","alpha",rotate_angle_solution));

	return result;
}




EMData* RotateTranslateFlipAligner::align(EMData * this_img, EMData *to,
										  const string & cmp_name, const Dict& cmp_params) const
{
	// Get the non flipped rotational, tranlsationally aligned image
	Dict rt_params("maxshift", params["maxshift"], "rfp_mode", params.set_default("rfp_mode",0));
	EMData *rot_trans_align = this_img->align("rotate_translate",to,rt_params,cmp_name, cmp_params);

	// Do the same alignment, but using the flipped version of the image
	EMData *flipped = params.set_default("flip", (EMData *) 0);
	bool delete_flag = false;
	if (flipped == 0) {
		flipped = to->process("xform.flip", Dict("axis", "x"));
		delete_flag = true;
	}

	EMData * rot_trans_align_flip = this_img->align("rotate_translate", flipped, rt_params, cmp_name, cmp_params);
	Transform* t = get_align_attr("xform.align2d",rot_trans_align_flip);
	t->set_mirror(true);

	// Now finally decide on what is the best answer
	float cmp1 = rot_trans_align->cmp(cmp_name, to, cmp_params);
	float cmp2 = rot_trans_align_flip->cmp(cmp_name, flipped, cmp_params);

	if (delete_flag){
		delete flipped;
		flipped = 0;
	}

	EMData *result = 0;
	if (cmp1 < cmp2 )  {

		if( rot_trans_align_flip ) {
			delete rot_trans_align_flip;
			rot_trans_align_flip = 0;
		}
		result = rot_trans_align;
	}
	else {
		if( rot_trans_align ) {
			delete rot_trans_align;
			rot_trans_align = 0;
		}
		result = rot_trans_align_flip;
		result->process_inplace("xform.flip",Dict("axis","x"));
	}

	return result;
}




EMData *RotateFlipAligner::align(EMData * this_img, EMData *to,
			const string& cmp_name, const Dict& cmp_params) const
{
	Dict rot_params("rfp_mode",params.set_default("rfp_mode",0));
	EMData *r1 = this_img->align("rotational", to, rot_params,cmp_name, cmp_params);


	EMData* flipped =to->process("xform.flip", Dict("axis", "x"));
	EMData *r2 = this_img->align("rotational", flipped,rot_params, cmp_name, cmp_params);
	Transform* t = get_align_attr("xform.align2d",r2);
	t->set_mirror(true);


	float cmp1 = r1->cmp(cmp_name, to, cmp_params);
	float cmp2 = r2->cmp(cmp_name, flipped, cmp_params);

	delete flipped; flipped = 0;

	EMData *result = 0;

	if (cmp1 < cmp2) {
		if( r2 )
		{
			delete r2;
			r2 = 0;
		}
		result = r1;
	}
	else {
		if( r1 )
		{
			delete r1;
			r1 = 0;
		}
		result = r2;
		result->process_inplace("xform.flip",Dict("axis","x"));
	}

	return result;
}


// David Woolford says FIXME
// You will note the excessive amount of EMData copying that's going in this function
// This is because functions that are operating on the EMData objects are changing them
// and if you do not use copies the whole algorithm breaks. I did not have time to go
// through and rectify this situation.
// David Woolford says - this problem is related to the fact that many functions that
// take EMData pointers as arguments do not take them as constant pointers to constant
// objects, instead they are treated as raw (completely changeable) pointers. This means
// it's hard to track down which functions are changing the EMData objects, because they
// all do (in name). If this behavior is unavoidable then ignore this comment, however if possible it would
// be good to make things const as much as possible. For example in alignment, technically
// the argument EMData objects (raw pointers) should not be altered... should they?
//
// But const can be very annoying sometimes...
EMData *RTFExhaustiveAligner::align(EMData * this_img, EMData *to,
			const string & cmp_name, const Dict& cmp_params) const
{
	EMData *flip = params.set_default("flip", (EMData *) 0);
	int maxshift = params.set_default("maxshift", this_img->get_xsize()/8);
	if (maxshift < 2) throw InvalidParameterException("maxshift must be greater than or equal to 2");

	int ny = this_img->get_ysize();
	int xst = (int) floor(2 * M_PI * ny);
	xst = Util::calc_best_fft_size(xst);

	Dict d("n",2);
	EMData *to_shrunk_unwrapped = to->process("math.medianshrink",d);

	int to_copy_r2 = to_shrunk_unwrapped->get_ysize() / 2 - 2 - maxshift / 2;
	EMData *tmp = to_shrunk_unwrapped->unwrap(4, to_copy_r2, xst / 2, 0, 0, true);
	if( to_shrunk_unwrapped )
	{
		delete to_shrunk_unwrapped;
		to_shrunk_unwrapped = 0;
	}
	to_shrunk_unwrapped = tmp;

	EMData *to_shrunk_unwrapped_copy = to_shrunk_unwrapped->copy();
	EMData* to_unwrapped = to->unwrap(4, to->get_ysize() / 2 - 2 - maxshift, xst, 0, 0, true);
	EMData *to_unwrapped_copy = to_unwrapped->copy();

	bool delete_flipped = true;
	EMData *flipped = 0;
	if (flip) {
		delete_flipped = false;
		flipped = flip;
	}
	else {
		flipped = to->process("xform.flip", Dict("axis", "x"));
	}
	EMData *to_shrunk_flipped_unwrapped = flipped->process("math.medianshrink",d);
	tmp = to_shrunk_flipped_unwrapped->unwrap(4, to_copy_r2, xst / 2, 0, 0, true);
	if( to_shrunk_flipped_unwrapped )
	{
		delete to_shrunk_flipped_unwrapped;
		to_shrunk_flipped_unwrapped = 0;
	}
	to_shrunk_flipped_unwrapped = tmp;
	EMData *to_shrunk_flipped_unwrapped_copy = to_shrunk_flipped_unwrapped->copy();
	EMData* to_flip_unwrapped = flipped->unwrap(4, to->get_ysize() / 2 - 2 - maxshift, xst, 0, 0, true);
	EMData* to_flip_unwrapped_copy = to_flip_unwrapped->copy();

	if (delete_flipped && flipped != 0) {
		delete flipped;
		flipped = 0;
	}

	EMData *this_shrunk_2 = this_img->process("math.medianshrink",d);

	float bestval = FLT_MAX;
	float bestang = 0;
	int bestflip = 0;
	float bestdx = 0;
	float bestdy = 0;

	int half_maxshift = maxshift / 2;

	int ur2 = this_shrunk_2->get_ysize() / 2 - 2 - half_maxshift;
	for (int dy = -half_maxshift; dy <= half_maxshift; dy += 1) {
		for (int dx = -half_maxshift; dx <= half_maxshift; dx += 1) {
#ifdef	_WIN32
			if (_hypot(dx, dy) <= half_maxshift) {
#else
			if (hypot(dx, dy) <= half_maxshift) {
#endif
				EMData *uw = this_shrunk_2->unwrap(4, ur2, xst / 2, dx, dy, true);
				EMData *uwc = uw->copy();
				EMData *a = uw->calc_ccfx(to_shrunk_unwrapped);

				uwc->rotate_x(a->calc_max_index());
				float cm = uwc->cmp(cmp_name, to_shrunk_unwrapped_copy, cmp_params);
				if (cm < bestval) {
					bestval = cm;
					bestang = (float) (2.0 * M_PI * a->calc_max_index() / a->get_xsize());
					bestdx = (float)dx;
					bestdy = (float)dy;
					bestflip = 0;
				}


				if( a )
				{
					delete a;
					a = 0;
				}
				if( uw )
				{
					delete uw;
					uw = 0;
				}
				if( uwc )
				{
					delete uwc;
					uwc = 0;
				}
				uw = this_shrunk_2->unwrap(4, ur2, xst / 2, dx, dy, true);
				uwc = uw->copy();
				a = uw->calc_ccfx(to_shrunk_flipped_unwrapped);

				uwc->rotate_x(a->calc_max_index());
				cm = uwc->cmp(cmp_name, to_shrunk_flipped_unwrapped_copy, cmp_params);
				if (cm < bestval) {
					bestval = cm;
					bestang = (float) (2.0 * M_PI * a->calc_max_index() / a->get_xsize());
					bestdx = (float)dx;
					bestdy = (float)dy;
					bestflip = 1;
				}

				if( a )
				{
					delete a;
					a = 0;
				}

				if( uw )
				{
					delete uw;
					uw = 0;
				}
				if( uwc )
				{
					delete uwc;
					uwc = 0;
				}
			}
		}
	}
	if( this_shrunk_2 )
	{
		delete this_shrunk_2;
		this_shrunk_2 = 0;
	}
	if( to_shrunk_unwrapped )
	{
		delete to_shrunk_unwrapped;
		to_shrunk_unwrapped = 0;
	}
	if( to_shrunk_unwrapped_copy )
	{
		delete to_shrunk_unwrapped_copy;
		to_shrunk_unwrapped_copy = 0;
	}
	if( to_shrunk_flipped_unwrapped )
	{
		delete to_shrunk_flipped_unwrapped;
		to_shrunk_flipped_unwrapped = 0;
	}
	if( to_shrunk_flipped_unwrapped_copy )
	{
		delete to_shrunk_flipped_unwrapped_copy;
		to_shrunk_flipped_unwrapped_copy = 0;
	}
	bestdx *= 2;
	bestdy *= 2;
	bestval = FLT_MAX;

	float bestdx2 = bestdx;
	float bestdy2 = bestdy;
	// Note I tried steps less than 1.0 (sub pixel precision) and it actually appeared detrimental
	// So my advice is to stick with dx += 1.0 etc unless you really are looking to fine tune this
	// algorithm
	for (float dy = bestdy2 - 3; dy <= bestdy2 + 3; dy += 1.0 ) {
		for (float dx = bestdx2 - 3; dx <= bestdx2 + 3; dx += 1.0 ) {

#ifdef	_WIN32
			if (_hypot(dx, dy) <= maxshift) {
#else
			if (hypot(dx, dy) <= maxshift) {
#endif
				EMData *uw = this_img->unwrap(4, this_img->get_ysize() / 2 - 2 - maxshift, xst, dx, dy, true);
				EMData *uwc = uw->copy();
				EMData *a = uw->calc_ccfx(to_unwrapped);

				uwc->rotate_x(a->calc_max_index());
				float cm = uwc->cmp(cmp_name, to_unwrapped_copy, cmp_params);

				if (cm < bestval) {
					bestval = cm;
					bestang = (float)(2.0 * M_PI * a->calc_max_index() / a->get_xsize());
					bestdx = dx;
					bestdy = dy;
					bestflip = 0;
				}

				if( a )
				{
					delete a;
					a = 0;
				}
				if( uw )
				{
					delete uw;
					uw = 0;
				}
				if( uwc )
				{
					delete uwc;
					uwc = 0;
				}
				uw = this_img->unwrap(4, this_img->get_ysize() / 2 - 2 - maxshift, xst, dx, dy, true);
				uwc = uw->copy();
				a = uw->calc_ccfx(to_flip_unwrapped);

				uwc->rotate_x(a->calc_max_index());
				cm = uwc->cmp(cmp_name, to_flip_unwrapped_copy, cmp_params);

				if (cm < bestval) {
					bestval = cm;
					bestang = (float)(2.0 * M_PI * a->calc_max_index() / a->get_xsize());
					bestdx = dx;
					bestdy = dy;
					bestflip = 1;
				}

				if( a )
				{
					delete a;
					a = 0;
				}
				if( uw )
				{
					delete uw;
					uw = 0;
				}
				if( uwc )
				{
					delete uwc;
					uwc = 0;
				}
			}
		}
	}
	if( to_unwrapped ) {delete to_unwrapped;to_unwrapped = 0;}
	if( to_shrunk_unwrapped ) {	delete to_shrunk_unwrapped;	to_shrunk_unwrapped = 0;}
	if (to_unwrapped_copy) { delete to_unwrapped_copy; to_unwrapped_copy = 0; }
	if (to_flip_unwrapped) { delete to_flip_unwrapped; to_flip_unwrapped = 0; }
	if (to_flip_unwrapped_copy) { delete to_flip_unwrapped_copy; to_flip_unwrapped_copy = 0;}

	bestang *= (float)EMConsts::rad2deg;
	Transform * t = new Transform(Dict("type","2d","alpha",(float)bestang));
	t->set_pre_trans(Vec2f(-bestdx,-bestdy));
	if (bestflip) {
		t->set_mirror(true);
	}

	EMData* ret = this_img->copy();
	ret->transform(*t);
	ret->set_attr("xform.align2d",t);

	return ret;
}


EMData *RTFSlowExhaustiveAligner::align(EMData * this_img, EMData *to,
			const string & cmp_name, const Dict& cmp_params) const
{

	EMData *flip = params.set_default("flip", (EMData *) 0);
	int maxshift = params.set_default("maxshift", -1);

	EMData *this_img_copy = this_img->copy();
	EMData *flipped = 0;

	bool delete_flipped = true;
	if (flip) {
		delete_flipped = false;
		flipped = flip;
	}
	else {
		flipped = to->process("xform.flip", Dict("axis", "x"));
	}

	int nx = this_img->get_xsize();

	if (maxshift < 0) {
		maxshift = nx / 10;
	}

	float angle_step =  params.set_default("angstep", 0.0f);
	if ( angle_step == 0 ) angle_step = atan2(2.0f, (float)nx);
	else {
		angle_step *= (float)EMConsts::deg2rad; //convert to radians
	}
	float trans_step =  params.set_default("transtep",1.0f);

	if (trans_step <= 0) throw InvalidParameterException("transstep must be greater than 0");
	if (angle_step <= 0) throw InvalidParameterException("angstep must be greater than 0");


	Dict shrinkfactor("n",2);
	EMData *this_img_shrink = this_img->process("math.medianshrink",shrinkfactor);
	EMData *to_shrunk = to->process("math.medianshrink",shrinkfactor);
	EMData *flipped_shrunk = flipped->process("math.medianshrink",shrinkfactor);

	int bestflip = 0;
	float bestdx = 0;
	float bestdy = 0;

	float bestang = 0;
	float bestval = FLT_MAX;

	int half_maxshift = maxshift / 2;


	for (int dy = -half_maxshift; dy <= half_maxshift; dy += 1) {
		for (float dx = -half_maxshift; dx <= half_maxshift; dx += 1) {
			if (hypot(dx, dy) <= maxshift) {
				for (float ang = -angle_step * 2.0f; ang <= (float)2 * M_PI; ang += angle_step * 4.0f) {
					EMData v(*this_img_shrink);
					Transform t(Dict("type","2d","alpha",static_cast<float>(ang*EMConsts::rad2deg)));
					t.set_trans(dx,dy);
					v.transform(t);
// 					v.rotate_translate(ang*EMConsts::rad2deg, 0.0f, 0.0f, (float)dx, (float)dy, 0.0f);

					float lc = v.cmp(cmp_name, to_shrunk, cmp_params);

					if (lc < bestval) {
						bestval = lc;
						bestang = ang;
						bestdx = dx;
						bestdy = dy;
						bestflip = 0;
					}

					lc = v.cmp(cmp_name,flipped_shrunk , cmp_params);
					if (lc < bestval) {
						bestval = lc;
						bestang = ang;
						bestdx = dx;
						bestdy = dy;
						bestflip = 1;
					}
				}
			}
		}
	}

	if( to_shrunk )
	{
		delete to_shrunk;
		to_shrunk = 0;
	}
	if( flipped_shrunk )
	{
		delete flipped_shrunk;
		flipped_shrunk = 0;
	}
	if( this_img_shrink )
	{
		delete this_img_shrink;
		this_img_shrink = 0;
	}

	bestdx *= 2;
	bestdy *= 2;
	bestval = FLT_MAX;

	float bestdx2 = bestdx;
	float bestdy2 = bestdy;
	float bestang2 = bestang;

	for (float dy = bestdy2 - 3; dy <= bestdy2 + 3; dy += trans_step) {
		for (float dx = bestdx2 - 3; dx <= bestdx2 + 3; dx += trans_step) {
			if (hypot(dx, dy) <= maxshift) {
				for (float ang = bestang2 - angle_step * 6.0f; ang <= bestang2 + angle_step * 6.0f; ang += angle_step) {
					EMData v(*this_img);
					Transform t(Dict("type","2d","alpha",static_cast<float>(ang*EMConsts::rad2deg)));
					t.set_trans(dx,dy);
					v.transform(t);
// 					v.rotate_translate(ang*EMConsts::rad2deg, 0.0f, 0.0f, (float)dx, (float)dy, 0.0f);

					float lc = v.cmp(cmp_name, to, cmp_params);

					if (lc < bestval) {
						bestval = lc;
						bestang = ang;
						bestdx = dx;
						bestdy = dy;
						bestflip = 0;
					}

					lc = v.cmp(cmp_name, flipped, cmp_params);

					if (lc < bestval) {
						bestval = lc;
						bestang = ang;
						bestdx = dx;
						bestdy = dy;
						bestflip = 1;
					}
				}
			}
		}
	}

	if (delete_flipped) { delete flipped; flipped = 0; }

	bestang *= (float)EMConsts::rad2deg;
	Transform * t = new Transform(Dict("type","2d","alpha",(float)bestang));
	t->set_trans(bestdx,bestdy);

	if (bestflip) {
		t->set_mirror(true);
	}

	this_img_copy->set_attr("xform.align2d",t);
	this_img_copy->transform(*t);

	return this_img_copy;
}



static double refalifn(const gsl_vector * v, void *params)
{
	Dict *dict = (Dict *) params;

	double x = gsl_vector_get(v, 0);
	double y = gsl_vector_get(v, 1);
	double a = gsl_vector_get(v, 2);

	EMData *this_img = (*dict)["this"];
	EMData *with = (*dict)["with"];
	bool mirror = (*dict)["mirror"];

	EMData *tmp = this_img->copy();

	float mean = (float)tmp->get_attr("mean");
	if ( Util::goodf(&mean) ) {
		//cout << "tmps mean is nan even before rotation" << endl;
	}

	Transform t(Dict("type","2d","alpha",static_cast<float>(a)));
// 	Transform3D t3d(Transform3D::EMAN, (float)a, 0.0f, 0.0f);
// 	t3d.set_posttrans( (float) x, (float) y);
//	tmp->rotate_translate(t3d);
	t.set_trans((float)x,(float)y);
	t.set_mirror(mirror);
	tmp->transform(t);

	Cmp* c = (Cmp*) ((void*)(*dict)["cmp"]);
	double result = c->cmp(tmp,with);

	// DELETE AT SOME STAGE, USEFUL FOR PRERELEASE STUFF
	// 	float test_result = (float)result;
// 	if ( Util::goodf(&test_result) ) {
//		cout << "result " << result << " " << x << " " << y << " " << a << endl;
//		cout << (float)this_img->get_attr("mean") << " " << (float)tmp->get_attr("mean") << " " << (float)with->get_attr("mean") << endl;
//		tmp->write_image("tmp.hdf");
//		with->write_image("with.hdf");
//		this_img->write_image("this_img.hdf");
//		EMData* t = this_img->copy();
//		cout << (float)t->get_attr("mean") << endl;
//		t->rotate_translate( t3d );
//		cout << (float)t->get_attr("mean") << endl;
//		cout << "exit" << endl;
//// 		double result = c->cmp(t,with);
//		cout << (float)t->get_attr("mean") << endl;
//		cout << "now exit" << endl;
//		delete t;
// 	}


	if ( tmp != 0 ) delete tmp;

	return result;
}

static double refalifnfast(const gsl_vector * v, void *params)
{
	Dict *dict = (Dict *) params;
	EMData *this_img = (*dict)["this"];
	EMData *img_to = (*dict)["with"];
	bool mirror = (*dict)["mirror"];

	double x = gsl_vector_get(v, 0);
	double y = gsl_vector_get(v, 1);
	double a = gsl_vector_get(v, 2);

	double r = this_img->dot_rotate_translate(img_to, (float)x, (float)y, (float)a, mirror);
	int nsec = this_img->get_xsize() * this_img->get_ysize();
	double result = 1.0 - r / nsec;

// 	cout << result << " x " << x << " y " << y << " az " << a <<  endl;
	return result;
}


EMData *RefineAligner::align(EMData * this_img, EMData *to,
	const string & cmp_name, const Dict& cmp_params) const
{

	if (!to) {
		return 0;
	}

	EMData *result = this_img->copy();

	int mode = params.set_default("mode", 0);
	float saz = 0.0;
	float sdx = 0.0;
	float sdy = 0.0;
	bool mirror = false;

	Transform* t = params.set_default("xform.align2d", (Transform*) 0);
	if ( t != 0 ) {
		//Transform* t = this_img->get_attr("xform.align2d");
		Dict params = t->get_params("2d");
		saz = params["alpha"];
		sdx = params["tx"];
		sdy = params["ty"];
		mirror = params["mirror"];
	}

	int np = 3;
	Dict gsl_params;
	gsl_params["this"] = this_img;
	gsl_params["with"] = to;
	gsl_params["snr"]  = params["snr"];
	gsl_params["mirror"] = mirror;

	const gsl_multimin_fminimizer_type *T = gsl_multimin_fminimizer_nmsimplex;
	gsl_vector *ss = gsl_vector_alloc(np);

	float stepx = params.set_default("stepx",1.0f);
	float stepy = params.set_default("stepy",1.0f);
	// Default step is 5 degree - note in EMAN1 it was 0.1 radians
	float stepaz = params.set_default("stepaz",5.0f);

	gsl_vector_set(ss, 0, stepx);
	gsl_vector_set(ss, 1, stepy);
	gsl_vector_set(ss, 2, stepaz);

	gsl_vector *x = gsl_vector_alloc(np);
	gsl_vector_set(x, 0, sdx);
	gsl_vector_set(x, 1, sdy);
	gsl_vector_set(x, 2, saz);

	Cmp *c = 0;

	gsl_multimin_function minex_func;
	if (mode == 2) {
		minex_func.f = &refalifnfast;
	}
	else {
		c = Factory < Cmp >::get(cmp_name, cmp_params);
		gsl_params["cmp"] = (void *) c;
		minex_func.f = &refalifn;
	}

	minex_func.n = np;
	minex_func.params = (void *) &gsl_params;

	gsl_multimin_fminimizer *s = gsl_multimin_fminimizer_alloc(T, np);
	gsl_multimin_fminimizer_set(s, &minex_func, x, ss);

	int rval = GSL_CONTINUE;
	int status = GSL_SUCCESS;
	int iter = 1;

	float precision = params.set_default("precision",0.04f);
	int maxiter = params.set_default("maxiter",28);
	while (rval == GSL_CONTINUE && iter < maxiter) {
		iter++;
		status = gsl_multimin_fminimizer_iterate(s);
		if (status) {
			break;
		}
		rval = gsl_multimin_test_size(gsl_multimin_fminimizer_size(s), precision);
	}

	Transform * tsoln = new Transform(Dict("type","2d","alpha",(float)gsl_vector_get(s->x, 2)));
	tsoln->set_mirror(mirror);
	tsoln->set_trans((float)gsl_vector_get(s->x, 0),(float)gsl_vector_get(s->x, 1));
	result->set_attr("xform.align2d",tsoln);
	result->transform(*tsoln);

	gsl_vector_free(x);
	gsl_vector_free(ss);
	gsl_multimin_fminimizer_free(s);

	if ( c != 0 ) delete c;

	return result;
}

CUDA_Aligner::CUDA_Aligner() {
	image_stack = NULL;
	ccf = NULL;
}

CUDA_Aligner::~CUDA_Aligner() {
	if (image_stack) delete image_stack;
	if (ccf) delete ccf;
}

#ifdef EMAN2_USING_CUDA
void CUDA_Aligner::setup(int nima, int nx, int ny, int ring_length, int nring, float step, int kx, int ky) {

	NIMA = nima;
	NX = nx;
	NY = ny;
	RING_LENGTH = ring_length;
        NRING = nring;
	STEP = step;
	KX = kx;
	KY = ky;

	image_stack = (float *)malloc(NIMA*NX*NY*sizeof(float));
	ccf = (float *)malloc(2*(2*KX+1)*(2*KY+1)*NIMA*(RING_LENGTH+2)*sizeof(float));
}

void CUDA_Aligner::insert_image(EMData *image, int num) {
	int base_address = num*NX*NY;
	for (int x=0; x<NX; x++)
		for (int y=0; y<NY; y++)
			image_stack[base_address+x*NY+y] = (*image)(x, y);
}

vector<float> CUDA_Aligner::alignment_2d(EMData *ref_image_em) {

	float *ref_image, max_ccf;
	int base_address, ccf_offset;
	float ts, tm;
	float ang, sx, sy, mirror;
	vector<float> align_result;

        ref_image = (float *)malloc(NX*NY*sizeof(float));

	for (int x=0; x<NX; x++)
		for (int y=0; y<NY; y++)
			ref_image[x*NY+y] = (*ref_image_em)(x, y);

        calculate_ccf(image_stack, ref_image, ccf, NIMA, NX, NY, RING_LENGTH, NRING, STEP, KX, KY);

	ccf_offset = NIMA*(RING_LENGTH+2)*(2*KX+1)*(2*KY+1);

	for (int im=0; im<NIMA; im++) {
		max_ccf = -1.0e22;
		for (int kx=-KX; kx<=KX; kx++) {
			for (int ky=-KY; ky<=KY; ky++) {
				base_address = (((ky+KY)*(2*KX+1)+(kx+KX))*NIMA+im)*(RING_LENGTH+2);
				for (int l=0; l<RING_LENGTH; l++) {
					ts = ccf[base_address+l];
					tm = ccf[base_address+l+ccf_offset];
					if (ts > max_ccf) {
						ang = float(l)/RING_LENGTH*360.0;
						sx = kx*STEP;
						sy = ky*STEP;
						mirror = 0;
						max_ccf = ts;
					}
					if (tm > max_ccf) {
						ang = float(l)/RING_LENGTH*360.0;
						sx = kx*STEP;
						sy = ky*STEP;
						mirror = 1;
						max_ccf = tm;
					}
				}
			}
		}
		align_result.push_back(ang);
		align_result.push_back(sx);
		align_result.push_back(sy);
		align_result.push_back(mirror);
	}
	return align_result;
}
#endif

void EMAN::dump_aligners()
{
	dump_factory < Aligner > ();
}

map<string, vector<string> > EMAN::dump_aligners_list()
{
	return dump_factory_list < Aligner > ();
}
